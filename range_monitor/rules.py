"""
Analysis rules for the Range Monitoring Agent.

Each rule is a standalone function that accepts pre-loaded DataFrames and an
AnalysisConfig, and returns a list of Insight objects. Rules are pure pandas —
no ML, no optimisation solvers. Scores are set to 0.0 here; the engine applies
composite scoring after all rules have run.
"""

from __future__ import annotations

import pandas as pd

from range_monitor.config import AnalysisConfig
from range_monitor.models import Insight


# ---------------------------------------------------------------------------
# Rule 1: Online / In-Store Rank Mismatch  →  RANGE_GAP
# ---------------------------------------------------------------------------

def rank_mismatch(
    products: pd.DataFrame,
    online_sales: pd.DataFrame,
    store_sales: pd.DataFrame,
    config: AnalysisConfig,
) -> list[Insight]:
    """
    Flag products that rank strongly in the online channel but underperform
    in specific store locations. Online rank acts as an unconstrained demand
    signal; a large delta suggests the product is ranging- or stock-constrained
    in that store.
    """
    # --- Online: aggregate total units per product, rank within category ---
    online_agg = (
        online_sales
        .groupby("product_id", as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold": "online_units"})
    )
    online_agg = online_agg.merge(products[["product_id", "product_name", "category", "price"]], on="product_id", how="inner")

    # Noise filter
    online_agg = online_agg[online_agg["online_units"] >= config.min_units_threshold]

    # Percentile rank within category (0–100, higher = better)
    online_agg["online_pct_rank"] = (
        online_agg.groupby("category")["online_units"]
        .rank(pct=True) * 100
    )

    # --- Store: aggregate total units per product × location, rank within category × location ---
    store_agg = (
        store_sales
        .groupby(["product_id", "location_id"], as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold": "store_units"})
    )
    store_agg = store_agg.merge(products[["product_id", "category"]], on="product_id", how="inner")
    store_agg["store_pct_rank"] = (
        store_agg.groupby(["category", "location_id"])["store_units"]
        .rank(pct=True) * 100
    )

    # --- Join and compute rank delta ---
    merged = store_agg.merge(
        online_agg[["product_id", "product_name", "category", "online_units", "online_pct_rank", "price"]],
        on=["product_id", "category"],
        how="inner",
    )
    merged["rank_delta"] = merged["online_pct_rank"] - merged["store_pct_rank"]

    # --- Filter: delta above threshold ---
    flagged = merged[merged["rank_delta"] >= config.rank_mismatch_threshold].copy()

    # Peer rank: best store rank for same product (proxy for "peer location")
    peer_ranks = (
        store_agg.groupby("product_id")["store_pct_rank"]
        .max()
        .reset_index()
        .rename(columns={"store_pct_rank": "best_peer_pct_rank"})
    )
    flagged = flagged.merge(peer_ranks, on="product_id", how="left")

    insights = []
    for _, row in flagged.iterrows():
        insights.append(Insight(
            insight_type="RANGE_GAP",
            product_id=row["product_id"],
            product_name=row["product_name"],
            category=row["category"],
            location_id=row["location_id"],
            score=0.0,
            narrative="",  # filled by delivery layer
            recommended_action="Review current ranging and stock allocation at this location.",
            supporting_data={
                "online_units": int(row["online_units"]),
                "store_units": int(row["store_units"]),
                "online_pct_rank": round(row["online_pct_rank"], 1),
                "store_pct_rank": round(row["store_pct_rank"], 1),
                "rank_delta": round(row["rank_delta"], 1),
                "best_peer_pct_rank": round(row.get("best_peer_pct_rank", 0), 1),
                "price": float(row["price"]) if pd.notna(row.get("price")) else None,
            },
        ))
    return insights


# ---------------------------------------------------------------------------
# Rule 2: Slow Mover Detection  →  SLOW_MOVER
# ---------------------------------------------------------------------------

def slow_mover(
    products: pd.DataFrame,
    online_sales: pd.DataFrame,
    store_sales: pd.DataFrame,
    config: AnalysisConfig,
) -> list[Insight]:
    """
    Identify products with a low sell-through rate at specific locations over
    a rolling window. Cross-references online performance to distinguish a
    genuinely weak product from a location-specific underperformance.
    """
    # Only rows with stock_on_hand data are useful here
    store_with_soh = store_sales.dropna(subset=["stock_on_hand"]).copy()
    if store_with_soh.empty:
        return []

    # Restrict to rolling window
    max_period = store_with_soh["period"].max()
    cutoff = max_period - pd.Timedelta(weeks=config.slow_mover_window_weeks)
    window_sales = store_with_soh[store_with_soh["period"] > cutoff]

    if window_sales.empty:
        return []

    # Aggregate per product × location
    agg = (
        window_sales
        .groupby(["product_id", "location_id"], as_index=False)
        .agg(
            units_sold=("units_sold", "sum"),
            avg_soh=("stock_on_hand", "mean"),
        )
    )
    agg["sell_through"] = agg["units_sold"] / agg["avg_soh"].clip(lower=1)
    flagged = agg[agg["sell_through"] < config.slow_mover_sell_through].copy()

    # Online rank for cross-reference
    online_agg = (
        online_sales
        .groupby("product_id", as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold": "online_units"})
    )
    online_agg = online_agg.merge(products[["product_id", "category"]], on="product_id", how="left")
    online_agg["online_pct_rank"] = (
        online_agg.groupby("category")["online_units"]
        .rank(pct=True) * 100
    )

    flagged = flagged.merge(
        products[["product_id", "product_name", "category", "price"]],
        on="product_id",
        how="inner",
    )
    flagged = flagged.merge(
        online_agg[["product_id", "online_units", "online_pct_rank"]],
        on="product_id",
        how="left",
    )

    insights = []
    for _, row in flagged.iterrows():
        online_pct = row.get("online_pct_rank", 0) or 0
        is_location_specific = online_pct >= 50  # online is decent; problem is store-specific
        capital_at_risk = round(row["avg_soh"] * (row.get("price") or 0), 2)

        if is_location_specific:
            action = "Investigate merchandising placement or stock depth at this location. Consider reallocation to higher-velocity stores."
        else:
            action = "Review whether this product should remain in the range. Consider markdown to clear remaining stock."

        insights.append(Insight(
            insight_type="SLOW_MOVER",
            product_id=row["product_id"],
            product_name=row["product_name"],
            category=row["category"],
            location_id=row["location_id"],
            score=0.0,
            narrative="",
            recommended_action=action,
            supporting_data={
                "units_sold_in_window": int(row["units_sold"]),
                "avg_stock_on_hand": round(row["avg_soh"], 1),
                "sell_through_pct": round(row["sell_through"] * 100, 1),
                "online_pct_rank": round(online_pct, 1),
                "online_units": int(row.get("online_units", 0) or 0),
                "capital_at_risk_gbp": capital_at_risk,
                "window_weeks": config.slow_mover_window_weeks,
                "is_location_specific": is_location_specific,
                "price": float(row["price"]) if pd.notna(row.get("price")) else None,
            },
        ))
    return insights


# ---------------------------------------------------------------------------
# Rule 3: Seasonal Misclassification  →  SEASON_MISMATCH
# ---------------------------------------------------------------------------

def season_mismatch(
    products: pd.DataFrame,
    online_sales: pd.DataFrame,
    calendar: pd.DataFrame | None,
    config: AnalysisConfig,
) -> list[Insight]:
    """
    Detect products tagged as seasonal that have consistent online sales
    outside their designated season window — a strong signal that they
    should be reclassified as continuity.
    """
    if calendar is None or calendar.empty:
        return []

    # Only seasonal products with a defined window
    seasonal_cal = calendar.dropna(subset=["active_from", "active_to"])
    if seasonal_cal.empty:
        return []

    seasonal_products = products[products["range_tag"] == "seasonal"].copy()
    if seasonal_products.empty:
        return []

    # Join products → calendar on range_tag + season
    sp = seasonal_products.merge(
        seasonal_cal[["range_tag", "season", "active_from", "active_to"]],
        on=["range_tag", "season"],
        how="inner",
    )

    # Join online sales
    sales = online_sales.merge(sp[["product_id", "product_name", "category", "season", "active_from", "active_to"]], on="product_id", how="inner")

    # Flag sales weeks that fall outside [active_from, active_to]
    sales["out_of_season"] = ~(
        (sales["period"] >= sales["active_from"]) & (sales["period"] <= sales["active_to"])
    )
    sales_with_units = sales[sales["units_sold"] >= config.min_units_threshold]

    out_of_season_counts = (
        sales_with_units[sales_with_units["out_of_season"]]
        .groupby(["product_id", "product_name", "category", "season", "active_from", "active_to"])
        .size()
        .reset_index(name="out_of_season_weeks")
    )

    flagged = out_of_season_counts[
        out_of_season_counts["out_of_season_weeks"] >= config.seasonal_consistency_weeks
    ]

    insights = []
    for _, row in flagged.iterrows():
        insights.append(Insight(
            insight_type="SEASON_MISMATCH",
            product_id=row["product_id"],
            product_name=row["product_name"],
            category=row["category"],
            location_id=None,
            score=0.0,
            narrative="",
            recommended_action=f"Reclassify {row['product_name']} from seasonal ({row['season']}) to continuity range to avoid unnecessary stock drops at season end.",
            supporting_data={
                "season": row["season"],
                "season_window": f"{row['active_from'].date()} to {row['active_to'].date()}",
                "out_of_season_selling_weeks": int(row["out_of_season_weeks"]),
                "threshold_weeks": config.seasonal_consistency_weeks,
            },
        ))
    return insights


# ---------------------------------------------------------------------------
# Rule 4: Category Performance Divergence  →  CATEGORY_DIVERGENCE
# ---------------------------------------------------------------------------

def category_divergence(
    products: pd.DataFrame,
    online_sales: pd.DataFrame,
    store_sales: pd.DataFrame,
    config: AnalysisConfig,
) -> list[Insight]:
    """
    Surface categories that are trending strongly in the online channel but
    are underrepresented or declining across store locations. This is a
    strategic-level signal for range review at category/department level.
    """
    # Online category ranking
    online_cat = (
        online_sales
        .merge(products[["product_id", "category"]], on="product_id", how="inner")
        .groupby("category", as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold": "online_units"})
    )
    total_cats = len(online_cat)
    if total_cats < 2:
        return []

    online_cat["online_cat_pct_rank"] = online_cat["online_units"].rank(pct=True) * 100
    top_online_cats = online_cat[online_cat["online_cat_pct_rank"] >= 75]["category"].tolist()

    if not top_online_cats:
        return []

    # Store category ranking per location
    store_cat = (
        store_sales
        .merge(products[["product_id", "category"]], on="product_id", how="inner")
        .groupby(["category", "location_id"], as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold": "store_units"})
    )
    store_cat["store_cat_pct_rank"] = (
        store_cat.groupby("location_id")["store_units"]
        .rank(pct=True) * 100
    )

    locations = store_cat["location_id"].unique()
    n_locations = len(locations)

    insights = []
    for cat in top_online_cats:
        cat_store = store_cat[store_cat["category"] == cat]
        # Count locations where this category is in the bottom quartile in-store
        bottom_quartile_locs = cat_store[cat_store["store_cat_pct_rank"] <= 25]["location_id"].tolist()
        pct_underperforming = len(bottom_quartile_locs) / n_locations if n_locations > 0 else 0

        if pct_underperforming >= config.category_underperformance_pct:
            online_rank = float(online_cat.loc[online_cat["category"] == cat, "online_cat_pct_rank"].values[0])
            online_units = int(online_cat.loc[online_cat["category"] == cat, "online_units"].values[0])
            insights.append(Insight(
                insight_type="CATEGORY_DIVERGENCE",
                product_id="",
                product_name="",
                category=cat,
                location_id=", ".join(bottom_quartile_locs),
                score=0.0,
                narrative="",
                recommended_action=(
                    f"Review range depth and planogram allocation for {cat} across "
                    f"{len(bottom_quartile_locs)} underperforming store(s)."
                ),
                supporting_data={
                    "online_category_pct_rank": round(online_rank, 1),
                    "online_units_total": online_units,
                    "pct_stores_underperforming": round(pct_underperforming * 100, 1),
                    "underperforming_locations": bottom_quartile_locs,
                    "total_locations": n_locations,
                },
            ))
    return insights


# ---------------------------------------------------------------------------
# Rule 5: Stock Imbalance  →  STOCK_IMBALANCE
# ---------------------------------------------------------------------------

def stock_imbalance(
    products: pd.DataFrame,
    online_sales: pd.DataFrame,
    store_sales: pd.DataFrame,
    config: AnalysisConfig,
) -> list[Insight]:
    """
    Identify locations holding disproportionate stock relative to their
    sales velocity compared to peer locations for the same product.
    Cross-referenced with online demand to confirm the product has genuine
    appeal and the imbalance isn't just a market mismatch.
    """
    store_with_soh = store_sales.dropna(subset=["stock_on_hand"]).copy()
    if store_with_soh.empty:
        return []

    # Latest period only for SOH snapshot
    latest_period = store_with_soh["period"].max()
    latest_soh = store_with_soh[store_with_soh["period"] == latest_period][
        ["product_id", "location_id", "stock_on_hand"]
    ]

    # Weekly velocity: average units sold per week per product × location
    velocity = (
        store_with_soh
        .groupby(["product_id", "location_id"], as_index=False)["units_sold"]
        .mean()
        .rename(columns={"units_sold": "weekly_velocity"})
    )
    velocity["weekly_velocity"] = velocity["weekly_velocity"].clip(lower=0.01)  # avoid div-by-zero

    combined = latest_soh.merge(velocity, on=["product_id", "location_id"], how="inner")
    combined["weeks_of_cover"] = combined["stock_on_hand"] / combined["weekly_velocity"]

    # Median weeks of cover per product across all locations
    median_woc = (
        combined
        .groupby("product_id")["weeks_of_cover"]
        .median()
        .reset_index()
        .rename(columns={"weeks_of_cover": "median_woc"})
    )
    combined = combined.merge(median_woc, on="product_id", how="left")
    combined["woc_multiple"] = combined["weeks_of_cover"] / combined["median_woc"].clip(lower=0.01)

    flagged = combined[combined["woc_multiple"] >= config.stock_imbalance_multiple].copy()

    # Online demand check
    online_agg = (
        online_sales
        .groupby("product_id", as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold": "online_units"})
    )
    online_agg = online_agg.merge(products[["product_id", "category"]], on="product_id", how="left")
    online_agg["online_pct_rank"] = (
        online_agg.groupby("category")["online_units"]
        .rank(pct=True) * 100
    )

    flagged = flagged.merge(products[["product_id", "product_name", "category", "price"]], on="product_id", how="inner")
    flagged = flagged.merge(online_agg[["product_id", "online_units", "online_pct_rank"]], on="product_id", how="left")

    # Only flag where online demand is meaningful (product has real appeal)
    flagged = flagged[flagged["online_pct_rank"] >= 40]

    insights = []
    for _, row in flagged.iterrows():
        excess_units = max(0, int(row["stock_on_hand"] - row["median_woc"] * row["weekly_velocity"]))
        price = float(row["price"]) if pd.notna(row.get("price")) else 0.0
        excess_value = round(excess_units * price, 2)

        insights.append(Insight(
            insight_type="STOCK_IMBALANCE",
            product_id=row["product_id"],
            product_name=row["product_name"],
            category=row["category"],
            location_id=row["location_id"],
            score=0.0,
            narrative="",
            recommended_action=(
                "Consider inter-store transfer to locations with lower weeks-of-cover "
                "and stronger sales velocity."
            ),
            supporting_data={
                "stock_on_hand": int(row["stock_on_hand"]),
                "weekly_velocity": round(row["weekly_velocity"], 1),
                "weeks_of_cover": round(row["weeks_of_cover"], 1),
                "median_woc_peers": round(row["median_woc"], 1),
                "woc_multiple": round(row["woc_multiple"], 1),
                "excess_units": excess_units,
                "excess_value_gbp": excess_value,
                "online_pct_rank": round(row.get("online_pct_rank", 0) or 0, 1),
                "price": price,
            },
        ))
    return insights

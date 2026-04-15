"""
Analysis Engine: orchestrates all rules, applies composite scoring, and returns
ranked insights.
"""

from __future__ import annotations

import pandas as pd

from range_monitor.config import AnalysisConfig
from range_monitor.models import Insight
from range_monitor.rules import (
    category_divergence,
    rank_mismatch,
    season_mismatch,
    slow_mover,
    stock_imbalance,
)

RULE_REGISTRY = {
    "rank_mismatch": rank_mismatch,
    "slow_mover": slow_mover,
    "season_mismatch": season_mismatch,
    "category_divergence": category_divergence,
    "stock_imbalance": stock_imbalance,
}


def _score_insight(insight: Insight) -> float:
    """
    Composite score combining three components:
      - Magnitude (0–1): how large is the mismatch?
      - Revenue opportunity (0–1): estimated £ value at stake (normalised later)
      - Recency: constant 1.0 for now (all data treated equally)

    Weights: 50% magnitude, 30% revenue, 20% recency.
    """
    d = insight.supporting_data
    magnitude = 0.0
    revenue_opp = 0.0

    if insight.insight_type == "RANGE_GAP":
        # rank_delta is 0–100; normalise to 0–1
        magnitude = min(d.get("rank_delta", 0) / 100.0, 1.0)
        # Revenue opportunity: difference in units × price
        online_rate = d.get("online_units", 0)
        store_units = d.get("store_units", 0)
        price = d.get("price") or 0
        revenue_opp = max(0, (online_rate - store_units)) * price

    elif insight.insight_type == "SLOW_MOVER":
        # Magnitude: how far below threshold is the sell-through?
        threshold = 10.0  # %
        sell_through = d.get("sell_through_pct", threshold)
        magnitude = min(max(threshold - sell_through, 0) / threshold, 1.0)
        revenue_opp = d.get("capital_at_risk_gbp", 0)

    elif insight.insight_type == "SEASON_MISMATCH":
        # Magnitude: weeks over-season vs threshold
        oos_weeks = d.get("out_of_season_selling_weeks", 0)
        threshold = d.get("threshold_weeks", 6)
        magnitude = min(oos_weeks / max(threshold * 2, 1), 1.0)
        revenue_opp = 0  # hard to quantify without reclassification model

    elif insight.insight_type == "CATEGORY_DIVERGENCE":
        magnitude = min(d.get("pct_stores_underperforming", 0) / 100.0, 1.0)
        revenue_opp = d.get("online_units_total", 0) * 0.1  # rough proxy

    elif insight.insight_type == "STOCK_IMBALANCE":
        multiple = d.get("woc_multiple", 1.0)
        magnitude = min((multiple - 1.0) / 5.0, 1.0)  # cap at 5× multiple
        revenue_opp = d.get("excess_value_gbp", 0)

    return magnitude, revenue_opp


def _normalise(values: list[float]) -> list[float]:
    """Min-max normalise a list of floats to [0, 1]."""
    if not values:
        return values
    min_v, max_v = min(values), max(values)
    if max_v == min_v:
        return [0.5] * len(values)
    return [(v - min_v) / (max_v - min_v) for v in values]


def score_and_rank(insights: list[Insight]) -> list[Insight]:
    """Apply composite scoring and return insights sorted descending by score."""
    if not insights:
        return []

    magnitudes = []
    rev_opps = []
    for ins in insights:
        m, r = _score_insight(ins)
        magnitudes.append(m)
        rev_opps.append(r)

    norm_rev = _normalise(rev_opps)

    for i, ins in enumerate(insights):
        ins.score = round(
            0.50 * magnitudes[i]
            + 0.30 * norm_rev[i]
            + 0.20 * 1.0,  # recency = 1.0 (current period data)
            4,
        )

    return sorted(insights, key=lambda x: x.score, reverse=True)


def run_analysis(
    products: pd.DataFrame,
    online_sales: pd.DataFrame,
    store_sales: pd.DataFrame,
    calendar: pd.DataFrame | None,
    config: AnalysisConfig,
) -> list[Insight]:
    """
    Orchestrate all enabled rules, score, rank, and return the top N insights.
    """
    all_insights: list[Insight] = []

    for rule_name in config.enabled_rules:
        fn = RULE_REGISTRY.get(rule_name)
        if fn is None:
            print(f"  Warning: unknown rule '{rule_name}' — skipping.")
            continue
        try:
            if rule_name == "season_mismatch":
                new = fn(products, online_sales, calendar, config)
            elif rule_name in {"stock_imbalance"}:
                new = fn(products, online_sales, store_sales, config)
            elif rule_name == "slow_mover":
                new = fn(products, online_sales, store_sales, config)
            else:
                new = fn(products, online_sales, store_sales, config)
            all_insights.extend(new)
        except Exception as exc:
            print(f"  Warning: rule '{rule_name}' failed with error: {exc} — skipping.")

    ranked = score_and_rank(all_insights)
    return ranked[:config.top_insights_count]

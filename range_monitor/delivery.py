"""
Delivery layer for the Range Monitoring Agent.

Two-layer report design:
  1. Decision Dashboard — one scannable table of all actions with £ impact.
     Designed for the Monday trade meeting. Open it, scan it, assign it.
  2. Detail Cards — compact cards with a 1-2 sentence explanation, key numbers,
     and a specific action (with quantities where the data supports it).
     For investigation and follow-up, not first-pass reading.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from range_monitor.config import AnalysisConfig
from range_monitor.models import Insight

# ---------------------------------------------------------------------------
# Priority labelling
# ---------------------------------------------------------------------------

def _assign_priorities(insights: list[Insight]) -> list[Insight]:
    if not insights:
        return insights
    scores = sorted({i.score for i in insights}, reverse=True)
    n = len(scores)
    high_cutoff = scores[max(0, n // 3 - 1)]
    low_cutoff = scores[min(n - 1, (2 * n) // 3)]
    for ins in insights:
        if ins.score >= high_cutoff:
            ins.supporting_data["_priority"] = "HIGH"
        elif ins.score >= low_cutoff:
            ins.supporting_data["_priority"] = "MEDIUM"
        else:
            ins.supporting_data["_priority"] = "LOW"
    return insights


PRIORITY_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
PRIORITY_BADGE = {"HIGH": "🔴 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "🟢 LOW"}

ACTION_LABEL = {
    "RANGE_GAP":           "Add / Increase",
    "SLOW_MOVER":          "Review / Clear",
    "SEASON_MISMATCH":     "Reclassify",
    "CATEGORY_DIVERGENCE": "Category Review",
    "STOCK_IMBALANCE":     "Move / Rebalance",
}

ACTION_SECTIONS = [
    {
        "title": "Products to Add or Increase at Specific Stores",
        "subtitle": "High online demand, low in-store performance. Most likely cause: ranging gap, poor placement, or insufficient stock depth.",
        "types": ["RANGE_GAP"],
        "emoji": "📦",
    },
    {
        "title": "Stock to Move or Rebalance Between Stores",
        "subtitle": "These locations are heavily overstocked relative to peer stores. Moving excess stock to higher-velocity stores turns idle capital into live revenue.",
        "types": ["STOCK_IMBALANCE"],
        "emoji": "🔄",
    },
    {
        "title": "Slow Movers to Review",
        "subtitle": "Low sell-through at specific locations. Each is labelled as a location-specific issue or a broader product problem to help you decide the right action.",
        "types": ["SLOW_MOVER"],
        "emoji": "🐢",
    },
    {
        "title": "Range Classifications to Review",
        "subtitle": "Tagged seasonal, but selling consistently outside the season window online. Worth reclassifying to continuity before the next range drop.",
        "types": ["SEASON_MISMATCH"],
        "emoji": "📅",
    },
    {
        "title": "Category Gaps Across Stores",
        "subtitle": "Top online categories underrepresented in-store at multiple locations. Strategic signal for the next range review.",
        "types": ["CATEGORY_DIVERGENCE"],
        "emoji": "📊",
    },
]

# ---------------------------------------------------------------------------
# One-liners for the decision dashboard
# ---------------------------------------------------------------------------

def _one_liner(ins: Insight) -> str:
    d = ins.supporting_data
    if ins.insight_type == "RANGE_GAP":
        online = d.get("online_units", 0)
        store = d.get("store_units", 0)
        return f"{online:,} units online vs {store:,} in-store — ranging or stock gap"
    if ins.insight_type == "SLOW_MOVER":
        st = d.get("sell_through_pct", 0)
        soh = d.get("avg_stock_on_hand", 0)
        loc_specific = d.get("is_location_specific", False)
        suffix = "location issue, not product" if loc_specific else "weak product — consider exit"
        return f"{st:.1f}% sell-through on {soh:.0f} units — {suffix}"
    if ins.insight_type == "SEASON_MISMATCH":
        oos = d.get("out_of_season_selling_weeks", 0)
        season = d.get("season", "")
        return f"{oos} weeks of sales outside {season} window — reclassify to continuity"
    if ins.insight_type == "STOCK_IMBALANCE":
        woc = d.get("weeks_of_cover", 0)
        median = d.get("median_woc_peers", 0)
        excess = d.get("excess_units", 0)
        return f"{woc:.0f} wks cover vs {median:.0f} wk peer avg — ~{excess:,} excess units"
    if ins.insight_type == "CATEGORY_DIVERGENCE":
        pct = d.get("pct_stores_underperforming", 0)
        n = d.get("total_locations", 0)
        return f"Top category online, bottom quartile in-store at {pct:.0f}% of {n} stores"
    return ""


def _impact_str(ins: Insight) -> str:
    d = ins.supporting_data
    if ins.insight_type == "RANGE_GAP":
        price = d.get("price") or 0
        gap = max(0, d.get("online_units", 0) - d.get("store_units", 0))
        opp = round(gap * price * 0.3)
        return f"~£{opp:,} opp." if opp > 0 else "—"
    if ins.insight_type == "SLOW_MOVER":
        cap = d.get("capital_at_risk_gbp", 0)
        return f"£{cap:,.0f} at risk" if cap > 0 else "—"
    if ins.insight_type == "STOCK_IMBALANCE":
        val = d.get("excess_value_gbp", 0)
        return f"~£{val:,.0f} excess" if val > 0 else "—"
    return "—"


# ---------------------------------------------------------------------------
# Specific action lines (with quantities where data supports it)
# ---------------------------------------------------------------------------

def _specific_action(ins: Insight) -> str:
    d = ins.supporting_data
    name = ins.product_name or ins.category
    loc = ins.location_id or "affected stores"

    if ins.insight_type == "RANGE_GAP":
        return f"Check ranging and increase stock allocation for {name} at {loc}."

    if ins.insight_type == "SLOW_MOVER":
        soh = d.get("avg_stock_on_hand", 0)
        if d.get("is_location_specific"):
            return f"Check floor placement and visibility of {name} at {loc} before taking markdown action."
        else:
            return f"Consider markdown to clear ~{soh:.0f} units of {name} at {loc}, or remove from range at next review."

    if ins.insight_type == "SEASON_MISMATCH":
        season = d.get("season", "current season")
        return f"Reclassify {name} from {season} seasonal to continuity in the product master."

    if ins.insight_type == "STOCK_IMBALANCE":
        excess = d.get("excess_units", 0)
        return f"Transfer ~{excess:,} units of {name} from {loc} to stores with lower cover and higher sell rate."

    if ins.insight_type == "CATEGORY_DIVERGENCE":
        locs = d.get("underperforming_locations", [])
        stores_str = ", ".join(locs[:3]) + (" and others" if len(locs) > 3 else "")
        return f"Review {name} range depth and planogram allocation at {stores_str} in the next range meeting."

    return ins.recommended_action


# ---------------------------------------------------------------------------
# Narrative builders — 1-2 sentences: killer fact + commercial consequence
# ---------------------------------------------------------------------------

def _narrative_range_gap(ins: Insight) -> str:
    d = ins.supporting_data
    online_units = d.get("online_units", 0)
    store_units = d.get("store_units", 0)
    price = d.get("price") or 0
    gap = max(0, online_units - store_units)
    opp = round(gap * price * 0.3)
    peer_pct = d.get("best_peer_pct_rank", 0)
    multiple = round(online_units / max(store_units, 1))

    peer_line = (
        f" Your best-performing store sells {multiple}× more of this product, confirming the demand is real."
        if peer_pct >= 70 and multiple >= 2 else ""
    )
    opp_line = f" Closing a third of this gap could recover ~£{opp:,}." if opp > 0 else ""

    return (
        f"Online, {ins.product_name} is selling {online_units:,} units — but {ins.location_id} "
        f"is only moving {store_units:,}.{peer_line}{opp_line}"
    )


def _narrative_slow_mover(ins: Insight) -> str:
    d = ins.supporting_data
    sell_through = d.get("sell_through_pct", 0)
    soh = d.get("avg_stock_on_hand", 0)
    units = d.get("units_sold_in_window", 0)
    window = d.get("window_weeks", 4)
    capital = d.get("capital_at_risk_gbp", 0)
    is_location_specific = d.get("is_location_specific", False)

    if is_location_specific:
        return (
            f"Only {units} units of {ins.product_name} sold at {ins.location_id} in {window} weeks "
            f"against a holding of {soh:.0f} units ({sell_through:.1f}% sell-through) — £{capital:,.0f} sitting idle. "
            f"This product is selling well online and at other stores, so this is a {ins.location_id} problem, not a product one."
        )
    else:
        return (
            f"{ins.product_name} has only sold {units} units in {window} weeks at {ins.location_id} "
            f"({sell_through:.1f}% sell-through on {soh:.0f} units, £{capital:,.0f} at risk). "
            f"Online demand is also soft — this may no longer belong in the range."
        )


def _narrative_season_mismatch(ins: Insight) -> str:
    d = ins.supporting_data
    season = d.get("season", "")
    window = d.get("season_window", "")
    oos_weeks = d.get("out_of_season_selling_weeks", 0)

    return (
        f"{ins.product_name} is tagged {season} seasonal (window: {window}), but has sold "
        f"online for {oos_weeks} weeks outside that window. "
        f"Keeping the seasonal tag means dropping it from the range while customers are still buying it."
    )


def _narrative_category_divergence(ins: Insight) -> str:
    d = ins.supporting_data
    online_units = d.get("online_units_total", 0)
    n_locs = d.get("total_locations", 0)
    underperforming = d.get("underperforming_locations", [])
    n_affected = len(underperforming)

    return (
        f"{ins.category} is one of your top-selling categories online ({online_units:,} units), "
        f"but ranks near the bottom in-store at {n_affected} of your {n_locs} stores "
        f"({', '.join(underperforming)}). "
        f"The demand is there — it is not being reflected on the shop floor."
    )


def _narrative_stock_imbalance(ins: Insight) -> str:
    d = ins.supporting_data
    woc = d.get("weeks_of_cover", 0)
    median_woc = d.get("median_woc_peers", 0)
    multiple = d.get("woc_multiple", 0)
    excess_units = d.get("excess_units", 0)
    excess_value = d.get("excess_value_gbp", 0)

    return (
        f"{ins.product_name} at {ins.location_id} has {woc:.0f} weeks of cover — "
        f"{multiple:.1f}× the {median_woc:.0f}-week average across peer stores. "
        f"~{excess_units:,} units (£{excess_value:,}) are held here that could be generating sales elsewhere."
    )


NARRATIVE_BUILDERS = {
    "RANGE_GAP": _narrative_range_gap,
    "SLOW_MOVER": _narrative_slow_mover,
    "SEASON_MISMATCH": _narrative_season_mismatch,
    "CATEGORY_DIVERGENCE": _narrative_category_divergence,
    "STOCK_IMBALANCE": _narrative_stock_imbalance,
}


def build_narratives(insights: list[Insight]) -> list[Insight]:
    insights = _assign_priorities(insights)
    for ins in insights:
        builder = NARRATIVE_BUILDERS.get(ins.insight_type)
        if builder:
            ins.narrative = builder(ins)
        ins.recommended_action = _specific_action(ins)
    return insights


# ---------------------------------------------------------------------------
# Context tables — numbers first, words second
# ---------------------------------------------------------------------------

def _context_table_range_gap(d: dict) -> list[tuple[str, str, str, str]]:
    price = d.get("price") or 0
    gap = max(0, d.get("online_units", 0) - d.get("store_units", 0))
    opp = round(gap * price * 0.3)
    return [
        ("Online units sold",    f"{d.get('online_units', 0):,}",          "Units at this store",  f"{d.get('store_units', 0):,}"),
        ("Gap",                  f"{gap:,} units",                          "Est. sales opportunity", f"~£{opp:,}"),
        ("Selling price",        f"£{price:,.2f}",                          "Best peer store rank", f"{d.get('best_peer_pct_rank', 0):.0f}th pctile"),
    ]


def _context_table_slow_mover(d: dict) -> list[tuple[str, str, str, str]]:
    loc_flag = "Yes — location issue" if d.get("is_location_specific") else "No — weak product"
    return [
        ("Units sold",           f"{d.get('units_sold_in_window', 0)}",           "Stock on hand (avg)",  f"{d.get('avg_stock_on_hand', 0):.0f}"),
        ("Sell-through",         f"{d.get('sell_through_pct', 0):.1f}%",           "Target",               ">10%"),
        ("Capital tied up",      f"£{d.get('capital_at_risk_gbp', 0):,.0f}",       "Location-specific?",   loc_flag),
        ("Rolling window",       f"{d.get('window_weeks', 4)} weeks",              "",                     ""),
    ]


def _context_table_season_mismatch(d: dict) -> list[tuple[str, str, str, str]]:
    return [
        ("Season tag",           d.get("season", "—"),                            "Season window",        d.get("season_window", "—")),
        ("Out-of-season weeks",  str(d.get("out_of_season_selling_weeks", 0)),     "Trigger threshold",    f"{d.get('threshold_weeks', 6)} weeks"),
    ]


def _context_table_category_divergence(d: dict) -> list[tuple[str, str, str, str]]:
    locs = ", ".join(d.get("underperforming_locations", []))
    return [
        ("Online units",         f"{d.get('online_units_total', 0):,}",            "Stores underperforming", f"{d.get('pct_stores_underperforming', 0):.0f}%"),
        ("Affected stores",      locs,                                              "Total stores",         str(d.get("total_locations", 0))),
    ]


def _context_table_stock_imbalance(d: dict) -> list[tuple[str, str, str, str]]:
    return [
        ("Stock on hand",        f"{d.get('stock_on_hand', 0):,} units",           "Weekly sell rate",     f"{d.get('weekly_velocity', 0):.1f} units/wk"),
        ("Weeks of cover",       f"{d.get('weeks_of_cover', 0):.0f} wks",          "Peer avg cover",       f"{d.get('median_woc_peers', 0):.0f} wks"),
        ("Excess units",         f"~{d.get('excess_units', 0):,}",                 "Excess value",         f"~£{d.get('excess_value_gbp', 0):,.0f}"),
    ]


CONTEXT_TABLE_BUILDERS = {
    "RANGE_GAP":           _context_table_range_gap,
    "SLOW_MOVER":          _context_table_slow_mover,
    "SEASON_MISMATCH":     _context_table_season_mismatch,
    "CATEGORY_DIVERGENCE": _context_table_category_divergence,
    "STOCK_IMBALANCE":     _context_table_stock_imbalance,
}


def _render_context_table_md(rows: list[tuple[str, str, str, str]]) -> str:
    lines = ["| | | | |", "|---|---|---|---|"]
    for label1, val1, label2, val2 in rows:
        if label1 or val1:
            lines.append(f"| **{label1}** | {val1} | **{label2}** | {val2} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Decision Dashboard — Layer 1
# ---------------------------------------------------------------------------

def _decision_dashboard(insights: list[Insight]) -> str:
    """
    One scannable table of all actions. Designed for the trade meeting.
    Columns: # | Priority | Action | Product / Category | Store | What's the issue | £ Impact
    """
    lines = [
        "| # | Priority | Action | Product / Category | Store | Issue | £ Impact |",
        "|---|----------|--------|--------------------|-------|-------|----------|",
    ]
    for i, ins in enumerate(insights, 1):
        priority = ins.supporting_data.get("_priority", "LOW")
        icon = PRIORITY_ICON.get(priority, "")
        action = ACTION_LABEL.get(ins.insight_type, ins.insight_type)
        name = (ins.product_name or ins.category)
        loc = ins.location_id or "Multiple stores"
        one_liner = _one_liner(ins)
        impact = _impact_str(ins)
        lines.append(f"| {i} | {icon} {priority} | {action} | {name} | {loc} | {one_liner} | {impact} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Executive summary — 3 bullets max
# ---------------------------------------------------------------------------

def _executive_summary(insights: list[Insight]) -> str:
    if not insights:
        return "_No range alerts this week. Check data coverage or review thresholds._"

    type_counts: dict[str, int] = {}
    for ins in insights:
        type_counts[ins.insight_type] = type_counts.get(ins.insight_type, 0) + 1

    high_count = sum(1 for i in insights if i.supporting_data.get("_priority") == "HIGH")

    total_exposure = sum(
        i.supporting_data.get("capital_at_risk_gbp", 0) + i.supporting_data.get("excess_value_gbp", 0)
        for i in insights
    )
    total_opp = sum(
        max(0, i.supporting_data.get("online_units", 0) - i.supporting_data.get("store_units", 0))
        * (i.supporting_data.get("price") or 0) * 0.3
        for i in insights if i.insight_type == "RANGE_GAP"
    )

    section_counts = []
    for s in ACTION_SECTIONS:
        count = sum(type_counts.get(t, 0) for t in s["types"])
        if count:
            section_counts.append(f"{count} {s['emoji']} {s['title'].lower()}")

    bullets = [
        f"**{len(insights)} alerts** this week, **{high_count} high priority**. "
        + (f"Breakdown: {'; '.join(section_counts)}." if section_counts else ""),
    ]
    if total_exposure > 0:
        bullets.append(f"**£{total_exposure:,.0f}** tied up in slow-moving or excess stock across flagged locations.")
    if total_opp > 0:
        bullets.append(f"**~£{total_opp:,.0f}** estimated in-store sales opportunity from range gap corrections (conservative, 30% capture rate).")

    return "\n".join(f"- {b}" for b in bullets)


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_markdown_report(
    insights: list[Insight],
    config: AnalysisConfig,
    run_date: str | None = None,
) -> str:
    if run_date is None:
        run_date = datetime.now().strftime("%d %B %Y")

    lines: list[str] = []

    # Header
    lines += [
        "# Range Monitoring — Weekly Alerts",
        f"**Week ending:** {run_date}",
        "",
        "---",
        "",
    ]

    # Layer 1: Summary + Decision Dashboard
    lines += [
        "## This Week at a Glance",
        "",
        _executive_summary(insights),
        "",
    ]

    if insights:
        lines += [
            "## Decision Dashboard",
            "",
            "_Use this table in your trade meeting. Full context for each item is in the sections below._",
            "",
            _decision_dashboard(insights),
            "",
            "---",
            "",
        ]

    # Layer 2: Detail cards, grouped by action
    lines += [
        "## Detail by Action",
        "",
        "_Each card: what's happening, the key numbers, and the specific action to take._",
        "",
    ]

    for section in ACTION_SECTIONS:
        section_insights = [i for i in insights if i.insight_type in section["types"]]
        if not section_insights:
            continue

        lines += [
            f"### {section['emoji']} {section['title']}",
            "",
            f"_{section['subtitle']}_",
            "",
        ]

        for rank_in_section, ins in enumerate(section_insights, 1):
            name = ins.product_name or ins.category
            loc_str = f" — {ins.location_id}" if ins.location_id else ""
            priority = ins.supporting_data.get("_priority", "LOW")
            badge = PRIORITY_BADGE.get(priority, priority)

            lines += [
                f"**{rank_in_section}. {name}{loc_str}** &nbsp; {badge}",
                "",
                ins.narrative or "",
                "",
            ]

            ctx_builder = CONTEXT_TABLE_BUILDERS.get(ins.insight_type)
            if ctx_builder:
                ctx_rows = ctx_builder(ins.supporting_data)
                if ctx_rows:
                    lines += [_render_context_table_md(ctx_rows), ""]

            lines += [f"**→ {ins.recommended_action}**", ""]

        lines += [""]

    # Appendix
    lines += [
        "---",
        "",
        "## Analysis Parameters",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Rank gap threshold | {config.rank_mismatch_threshold:.0f} percentile points |",
        f"| Slow mover threshold | <{config.slow_mover_sell_through * 100:.0f}% sell-through over {config.slow_mover_window_weeks} weeks |",
        f"| Season mismatch trigger | {config.seasonal_consistency_weeks} weeks of out-of-season online sales |",
        f"| Stock imbalance trigger | {config.stock_imbalance_multiple:.1f}× peer median weeks of cover |",
        f"| Minimum online units filter | {config.min_units_threshold} units |",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def render_console_summary(insights: list[Insight], top_n: int = 10) -> str:
    try:
        from tabulate import tabulate
    except ImportError:
        rows_plain = []
        for i, ins in enumerate(insights[:top_n], 1):
            name = ins.product_name or ins.category
            loc = ins.location_id or "—"
            priority = ins.supporting_data.get("_priority", "—")
            rows_plain.append(f"  {i:>2}. [{priority:<6}] {ACTION_LABEL.get(ins.insight_type, ins.insight_type):<18} {name} @ {loc}")
        return "\n".join(rows_plain)

    rows = []
    for i, ins in enumerate(insights[:top_n], 1):
        name = (ins.product_name or ins.category)[:32]
        loc = (ins.location_id or "—")[:22]
        action = ACTION_LABEL.get(ins.insight_type, ins.insight_type)
        priority = ins.supporting_data.get("_priority", "—")
        impact = _impact_str(ins)
        rows.append([i, priority, action, name, loc, impact])

    return tabulate(
        rows,
        headers=["#", "Priority", "Action", "Product / Category", "Location", "£ Impact"],
        tablefmt="rounded_outline",
    )


# ---------------------------------------------------------------------------
# Save outputs
# ---------------------------------------------------------------------------

def save_outputs(
    insights: list[Insight],
    config: AnalysisConfig,
    output_dir: str | Path = "output",
    run_date: str | None = None,
) -> None:
    from range_monitor.html_report import render_html_report

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "insights.json"
    payload = []
    for i, ins in enumerate(insights):
        d = {k: v for k, v in ins.supporting_data.items() if not k.startswith("_")}
        payload.append({
            "rank": i + 1,
            "priority": ins.supporting_data.get("_priority", "LOW"),
            "insight_type": ins.insight_type,
            "action": ACTION_LABEL.get(ins.insight_type, ins.insight_type),
            "product_id": ins.product_id,
            "product_name": ins.product_name,
            "category": ins.category,
            "location_id": ins.location_id,
            "one_liner": _one_liner(ins),
            "impact": _impact_str(ins),
            "narrative": ins.narrative,
            "recommended_action": ins.recommended_action,
            "data": d,
        })
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    md_path = out / "report.md"
    with open(md_path, "w") as f:
        f.write(render_markdown_report(insights, config, run_date))

    html_path = out / "report.html"
    with open(html_path, "w") as f:
        f.write(render_html_report(insights, config, run_date))

    print(f"\n  Saved: {json_path}")
    print(f"  Saved: {md_path}")
    print(f"  Saved: {html_path}")

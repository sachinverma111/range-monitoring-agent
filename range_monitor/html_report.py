"""
Interactive HTML report renderer for the Range Monitoring Agent.

Generates a self-contained single HTML file with:
  - KPI summary cards
  - Filterable decision dashboard (by priority + action type)
  - Expandable detail cards per action section
  - Click dashboard row → scroll to and expand detail card
  - Download as PDF via browser print (no server required)
"""

from __future__ import annotations

from range_monitor.config import AnalysisConfig
from range_monitor.delivery import (
    ACTION_LABEL,
    ACTION_SECTIONS,
    CONTEXT_TABLE_BUILDERS,
    PRIORITY_ICON,
    _impact_str,
    _one_liner,
)
from range_monitor.models import Insight

# ---------------------------------------------------------------------------
# Colour mappings
# ---------------------------------------------------------------------------

PRIORITY_COLORS = {
    "HIGH":   {"bg": "#FEF2F2", "border": "#FCA5A5", "text": "#DC2626", "badge_bg": "#DC2626", "badge_text": "#fff"},
    "MEDIUM": {"bg": "#FFFBEB", "border": "#FCD34D", "text": "#D97706", "badge_bg": "#D97706", "badge_text": "#fff"},
    "LOW":    {"bg": "#F0FDF4", "border": "#86EFAC", "text": "#16A34A", "badge_bg": "#16A34A", "badge_text": "#fff"},
}

TYPE_COLORS = {
    "RANGE_GAP":           "#2563EB",
    "STOCK_IMBALANCE":     "#7C3AED",
    "SLOW_MOVER":          "#EA580C",
    "SEASON_MISMATCH":     "#0D9488",
    "CATEGORY_DIVERGENCE": "#4338CA",
}

# What signal powers each insight type
SIGNAL_TAGS = {
    "RANGE_GAP":           "📡 Online demand vs in-store gap",
    "SLOW_MOVER":          "📡 Sell-through cross-referenced with online demand",
    "SEASON_MISMATCH":     "📡 Out-of-season online demand signal",
    "STOCK_IMBALANCE":     "📡 Cross-location stock vs demand comparison",
    "CATEGORY_DIVERGENCE": "📡 Online category signal vs in-store performance",
}

# Why this wouldn't appear in a standard trade pack
TRADE_PACK_MISS = {
    "RANGE_GAP": (
        "Your trade pack shows in-store sales in isolation. "
        "Without the online channel as a demand benchmark, this gap is invisible until a quarterly range review."
    ),
    "SLOW_MOVER": (
        "A trade pack flags slow movers but cannot tell you whether it is a weak product or a location-specific issue. "
        "Comparing against online demand gives us the answer."
    ),
    "SEASON_MISMATCH": (
        "Range classifications are maintained manually and reviewed infrequently. "
        "No standard report has a mechanism to flag when a product's actual selling pattern no longer matches its tag."
    ),
    "STOCK_IMBALANCE": (
        "A trade pack shows stock levels per store but does not benchmark one location against peers for the same product, "
        "nor cross-reference with online demand to confirm the product has genuine appeal elsewhere."
    ),
    "CATEGORY_DIVERGENCE": (
        "Category analysis in trade packs looks at in-store performance only. "
        "The divergence between online category demand and in-store representation is invisible without a cross-channel view."
    ),
}

INSIGHT_TYPE_BADGE_COLORS = {
    "RANGE_GAP":           {"bg": "#FEF2F2", "text": "#DC2626"},
    "SLOW_MOVER":          {"bg": "#FFF7ED", "text": "#EA580C"},
    "STOCK_IMBALANCE":     {"bg": "#EFF6FF", "text": "#2563EB"},
    "SEASON_MISMATCH":     {"bg": "#F0FDFA", "text": "#0D9488"},
    "CATEGORY_DIVERGENCE": {"bg": "#EEF2FF", "text": "#4338CA"},
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _type_badge_html(insight_type: str) -> str:
    """Coloured badge for insight type in analytics tables."""
    c = INSIGHT_TYPE_BADGE_COLORS.get(insight_type, {"bg": "#F3F4F6", "text": "#6B7280"})
    return (
        f'<span style="background:{c["bg"]};color:{c["text"]};'
        f'padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700;'
        f'letter-spacing:0.02em;white-space:nowrap;">{insight_type}</span>'
    )


def _esc(s: str) -> str:
    """HTML-escape a string."""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _priority_badge(priority: str) -> str:
    c = PRIORITY_COLORS.get(priority, PRIORITY_COLORS["LOW"])
    icon = PRIORITY_ICON.get(priority, "")
    return (
        f'<span style="background:{c["badge_bg"]};color:{c["badge_text"]};'
        f'padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;'
        f'letter-spacing:0.05em;">{icon} {priority}</span>'
    )


def _action_chip(insight_type: str) -> str:
    color = TYPE_COLORS.get(insight_type, "#6B7280")
    label = ACTION_LABEL.get(insight_type, insight_type)
    section = next((s for s in ACTION_SECTIONS if insight_type in s["types"]), None)
    emoji = section["emoji"] if section else ""
    return (
        f'<span style="background:{color}18;color:{color};border:1px solid {color}44;'
        f'padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;">'
        f'{emoji} {label}</span>'
    )


def _context_table_html(d: dict, insight_type: str) -> str:
    builder = CONTEXT_TABLE_BUILDERS.get(insight_type)
    if not builder:
        return ""
    rows = builder(d)
    cells = []
    for label1, val1, label2, val2 in rows:
        cells.append(
            f'<tr>'
            f'<td style="padding:6px 12px;font-weight:600;color:#374151;background:#F9FAFB;width:22%;">{_esc(label1)}</td>'
            f'<td style="padding:6px 12px;color:#111827;width:28%;">{_esc(str(val1))}</td>'
            f'<td style="padding:6px 12px;font-weight:600;color:#374151;background:#F9FAFB;width:22%;">{_esc(label2)}</td>'
            f'<td style="padding:6px 12px;color:#111827;width:28%;">{_esc(str(val2))}</td>'
            f'</tr>'
        )
    return (
        f'<table style="width:100%;border-collapse:collapse;border:1px solid #E5E7EB;'
        f'border-radius:6px;overflow:hidden;font-size:13px;">'
        + "".join(cells)
        + "</table>"
    )


# ---------------------------------------------------------------------------
# Online vs In-Store signal bar (RANGE_GAP only)
# ---------------------------------------------------------------------------

def _online_signal_bar(d: dict) -> str:
    """Visual bar showing online percentile rank vs in-store rank side by side."""
    online_pct = d.get("online_pct_rank", 0)
    store_pct = d.get("store_pct_rank", 0)
    n = d.get("category_product_count", 0)
    online_r = d.get("online_rank_num", 0)
    store_r = d.get("store_rank_num", 0)

    # Use absolute rank (#X of N) when available — avoids "Top 0%" for best sellers
    if n > 0 and online_r > 0:
        online_label = f"#{online_r:,} of {n:,}"
    else:
        top_pct = max(1, round(100 - online_pct))
        online_label = f"Top {top_pct}%"

    if d.get("is_missing_from_range"):
        store_label = "Not ranged"
    elif n > 0 and store_r > 0:
        store_label = f"#{store_r:,} of {n:,}"
    else:
        bottom_pct = round(100 - store_pct)
        store_label = f"Bottom {max(1, bottom_pct)}%"

    def bar(pct: float, color: str, label: str, channel: str) -> str:
        bar_w = max(4, round(pct))
        return (
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">'
            f'<span style="width:100px;font-size:12px;font-weight:600;color:#374151;flex-shrink:0;">{channel}</span>'
            f'<div style="flex:1;background:#F3F4F6;border-radius:4px;height:18px;position:relative;">'
            f'<div style="width:{bar_w}%;background:{color};border-radius:4px;height:100%;'
            f'transition:width 0.4s ease;"></div>'
            f'</div>'
            f'<span style="width:90px;font-size:12px;font-weight:700;color:{color};flex-shrink:0;">{label}</span>'
            f'</div>'
        )

    return (
        f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;padding:14px 16px;margin-bottom:16px;">'
        f'<p style="font-size:11px;font-weight:700;color:#1E40AF;text-transform:uppercase;'
        f'letter-spacing:0.08em;margin:0 0 10px 0;">Cross-Channel Demand Signal</p>'
        + bar(online_pct, "#2563EB", online_label, "🌐 Online")
        + bar(store_pct, "#DC2626", store_label, "🏪 In-store")
        + f'<p style="font-size:11px;color:#3B82F6;margin:8px 0 0 0;">'
        f'Online demand is the unconstrained signal — customers buying online choose the product freely, '
        f'with no stock or ranging constraints. A strong online rank paired with a weak in-store rank '
        f'points to a ranging or allocation gap, not a weak product.'
        f'</p>'
        f'</div>'
    )


def _trade_pack_miss_html(insight_type: str) -> str:
    msg = TRADE_PACK_MISS.get(insight_type, "")
    if not msg:
        return ""
    return (
        f'<div style="background:#FFF7ED;border-left:3px solid #FB923C;padding:10px 14px;'
        f'border-radius:0 6px 6px 0;margin-bottom:16px;">'
        f'<span style="font-size:11px;font-weight:700;color:#C2410C;text-transform:uppercase;'
        f'letter-spacing:0.06em;">Why your trade pack wouldn\'t flag this</span>'
        f'<p style="font-size:13px;color:#7C2D12;margin:4px 0 0 0;">{_esc(msg)}</p>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Unified insights table
# ---------------------------------------------------------------------------

def _insights_table_html(insights: list[Insight]) -> str:
    """Single paginated table of all insights — the main action view for merchandisers."""
    if not insights:
        return ""

    rows_html = []
    for idx, ins in enumerate(insights, 1):
        d = ins.supporting_data
        priority = d.get("_priority", "LOW")
        name = _esc(ins.product_name or ins.category)
        loc = _esc(ins.location_id or "Multiple stores")
        one_liner = _esc(_one_liner(ins))
        impact = _esc(_impact_str(ins))

        rows_html.append(
            f'<tr class="opp-row" data-priority="{priority}" data-type="{ins.insight_type}" '
            f'style="border-bottom:1px solid #F3F4F6;cursor:pointer;" '
            f'onclick="scrollToCard(\'card-{idx}\')" '
            f'onmouseover="this.style.background=\'#F9FAFB\'" onmouseout="this.style.background=\'\'">'
            f'<td style="padding:10px 14px;font-weight:600;color:#111827;max-width:200px;'
            f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{name}">{name}</td>'
            f'<td style="padding:10px 14px;color:#6B7280;font-size:13px;">{loc}</td>'
            f'<td style="padding:10px 14px;">{_type_badge_html(ins.insight_type)}</td>'
            f'<td style="padding:10px 14px;">{_priority_badge(priority)}</td>'
            f'<td style="padding:10px 14px;color:#374151;font-size:13px;max-width:320px;'
            f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{one_liner}">'
            f'{one_liner}</td>'
            f'<td style="padding:10px 14px;font-weight:700;color:#059669;white-space:nowrap;">'
            f'{impact}</td>'
            f'</tr>'
        )

    total = len(insights)
    header = (
        '<thead><tr style="background:#F9FAFB;border-bottom:2px solid #E5E7EB;">'
        + "".join(
            f'<th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:700;'
            f'color:#6B7280;text-transform:uppercase;letter-spacing:0.05em;white-space:nowrap;">{h}</th>'
            for h in ["Product / Category", "Store", "Type", "Priority", "Issue", "£ Impact"]
        )
        + "</tr></thead>"
    )

    return (
        f'<div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;'
        f'overflow:hidden;margin-bottom:24px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">'
        f'<div style="padding:16px 20px;border-bottom:1px solid #E5E7EB;display:flex;'
        f'align-items:center;justify-content:space-between;">'
        f'<div>'
        f'<h3 style="font-size:17px;font-weight:800;color:#111827;margin:0;">All Insights</h3>'
        f'<p style="font-size:12px;color:#9CA3AF;margin:2px 0 0 0;">'
        f'Click any row to jump to the detail card</p>'
        f'</div>'
        f'<span style="font-size:12px;color:#9CA3AF;">{total} items</span>'
        f'</div>'
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;" id="opp-table">'
        + header
        + '<tbody>' + "".join(rows_html) + '</tbody>'
        + '</table></div>'
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'padding:12px 20px;border-top:1px solid #E5E7EB;">'
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<span style="font-size:12px;color:#6B7280;">Rows per page:</span>'
        f'<select id="opp-page-size" onchange="oppChangePageSize()" '
        f'style="border:1px solid #D1D5DB;border-radius:6px;padding:4px 8px;font-size:12px;'
        f'color:#374151;">'
        f'<option value="10">10</option><option value="20" selected>20</option>'
        f'<option value="50">50</option>'
        f'</select></div>'
        f'<div style="display:flex;align-items:center;gap:6px;">'
        f'<span id="opp-range" style="font-size:12px;color:#6B7280;">'
        f'1–{min(20, total)} of {total}</span>'
        f'<button onclick="oppPrev()" id="opp-prev" style="background:#fff;border:1px solid #D1D5DB;'
        f'border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;" disabled>'
        f'&#8249; Prev</button>'
        f'<button onclick="oppNext()" id="opp-next" style="background:#fff;border:1px solid #D1D5DB;'
        f'border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;">'
        f'Next &#8250;</button>'
        f'</div></div></div>'
    )


# ---------------------------------------------------------------------------
# Charts section (Chart.js)
# ---------------------------------------------------------------------------

CHARTS_TEMPLATE = """
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:32px;">
  <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
    <h4 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 2px 0;">Opportunity scatter</h4>
    <p style="font-size:11px;color:#9CA3AF;margin:0 0 12px 0;">Online % vs Store % — below diagonal = opportunity (__SCATTER_COUNT__)</p>
    <div style="height:220px;"><canvas id="chart-scatter"></canvas></div>
  </div>
  <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
    <h4 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 2px 0;">Category impact</h4>
    <p style="font-size:11px;color:#9CA3AF;margin:0 0 12px 0;">Most affected categories (Top __CAT_COUNT__ by gap)</p>
    <div style="height:220px;"><canvas id="chart-category"></canvas></div>
  </div>
  <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
    <h4 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 2px 0;">Location impact</h4>
    <p style="font-size:11px;color:#9CA3AF;margin:0 0 12px 0;">Most affected locations (Top __LOC_COUNT__ by alert count)</p>
    <div style="height:220px;"><canvas id="chart-locations"></canvas></div>
  </div>
</div>

<script>
(function() {
  var cd = __CHART_DATA__;
  function initCharts() {
    if (typeof Chart === 'undefined') { setTimeout(initCharts, 200); return; }

    if (cd.scatter.length > 0) {
      new Chart(document.getElementById('chart-scatter'), {
        type: 'scatter',
        data: { datasets: [
          {
            label: 'Products',
            data: cd.scatter,
            backgroundColor: 'rgba(37,99,235,0.5)',
            borderColor: 'rgba(37,99,235,0.8)',
            pointRadius: 6, pointHoverRadius: 8
          },
          {
            label: 'Balanced (diagonal)',
            data: [{x:0,y:0},{x:100,y:100}],
            type: 'line',
            borderColor: 'rgba(209,213,219,0.7)',
            borderDash: [6,4],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false
          }
        ] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: function(ctx) {
              var d = cd.scatter[ctx.dataIndex];
              return d ? d.name + ' (Online ' + d.x + '%, Store ' + d.y + '%)' : '';
            } } }
          },
          scales: {
            x: { title: { display: true, text: 'Online Percentile %', font: { size: 10 } }, min: 0, max: 100, grid: { color: '#F3F4F6' } },
            y: { title: { display: true, text: 'Store Percentile %', font: { size: 10 } }, min: 0, max: 100, grid: { color: '#F3F4F6' } }
          }
        }
      });
    }

    if (cd.cat_labels.length > 0) {
      new Chart(document.getElementById('chart-category'), {
        type: 'bar',
        data: {
          labels: cd.cat_labels,
          datasets: [
            { label: '# Products', data: cd.cat_counts, backgroundColor: 'rgba(251,191,36,0.7)', borderRadius: 4, order: 2 },
            { label: 'Avg gap', data: cd.cat_avg_gaps, backgroundColor: 'rgba(59,130,246,0.8)', borderRadius: 4, order: 1 }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: true, position: 'bottom', labels: { font: { size: 11 } } } },
          scales: {
            x: { ticks: { font: { size: 10 }, maxRotation: 45 }, grid: { display: false } },
            y: { grid: { color: '#F3F4F6' } }
          }
        }
      });
    }

    if (cd.loc_labels.length > 0) {
      new Chart(document.getElementById('chart-locations'), {
        type: 'bar',
        data: {
          labels: cd.loc_labels,
          datasets: [{ label: '# Alerts', data: cd.loc_counts, backgroundColor: 'rgba(251,191,36,0.7)', borderRadius: 4 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { font: { size: 10 }, maxRotation: 45 }, grid: { display: false } },
            y: { grid: { color: '#F3F4F6' } }
          }
        }
      });
    }
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', initCharts); }
  else { initCharts(); }
})();
</script>
"""


def _charts_section_html(insights: list[Insight]) -> str:
    """3-chart analytics row: scatter, category impact, location impact."""
    import json

    scatter_data = []
    for ins in insights:
        if ins.insight_type == "RANGE_GAP":
            d = ins.supporting_data
            scatter_data.append({
                "x": round(d.get("online_pct_rank", 0), 1),
                "y": round(d.get("store_pct_rank", 0), 1),
                "name": (ins.product_name or "")[:20],
            })
    scatter_data = scatter_data[:50]

    cat_counts: dict[str, int] = {}
    cat_gap_sum: dict[str, float] = {}
    for ins in insights:
        cat = ins.category
        if not cat:
            continue
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        cat_gap_sum[cat] = cat_gap_sum.get(cat, 0) + ins.supporting_data.get("rank_delta", 0)
    top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    loc_counts: dict[str, int] = {}
    for ins in insights:
        loc = ins.location_id
        if not loc:
            continue
        for part in loc.split(", ")[:3]:
            part = part.strip()
            if part:
                loc_counts[part] = loc_counts.get(part, 0) + 1
    top_locs = sorted(loc_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    chart_data_json = json.dumps({
        "scatter": scatter_data,
        "cat_labels": [c[0][:25] for c in top_cats],
        "cat_counts": [c[1] for c in top_cats],
        "cat_avg_gaps": [round(cat_gap_sum.get(c[0], 0) / max(c[1], 1), 1) for c in top_cats],
        "loc_labels": [l[0][:25] for l in top_locs],
        "loc_counts": [l[1] for l in top_locs],
    })

    html = CHARTS_TEMPLATE
    html = html.replace("__CHART_DATA__", chart_data_json)
    html = html.replace("__SCATTER_COUNT__", str(len(scatter_data)))
    html = html.replace("__CAT_COUNT__", str(len(top_cats)))
    html = html.replace("__LOC_COUNT__", str(len(top_locs)))
    return html


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

def _kpi_cards_html(insights: list[Insight], total_seasonal_products: int = 0) -> str:
    high = sum(1 for i in insights if i.supporting_data.get("_priority") == "HIGH")
    exposure = sum(
        i.supporting_data.get("capital_at_risk_gbp", 0) + i.supporting_data.get("excess_value_gbp", 0)
        for i in insights
    )
    opp = sum(
        i.supporting_data.get("revenue_opportunity_gbp", 0)
        for i in insights if i.insight_type == "RANGE_GAP"
    )
    season_count = sum(1 for i in insights if i.insight_type == "SEASON_MISMATCH")

    def card(value, label, color, sub=""):
        sub_html = f'<div style="font-size:11px;color:#9CA3AF;margin-top:2px;">{sub}</div>' if sub else ""
        return (
            f'<div style="background:#fff;border:1px solid #E5E7EB;border-top:4px solid {color};'
            f'border-radius:8px;padding:20px 24px;flex:1;min-width:160px;">'
            f'<div style="font-size:28px;font-weight:800;color:{color};line-height:1;">{value}</div>'
            f'<div style="font-size:13px;color:#374151;font-weight:600;margin-top:4px;">{label}</div>'
            f'{sub_html}'
            f'</div>'
        )

    cards_html = (
        f'<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px;">'
        + card(len(insights), "Total Alerts", "#6366F1")
        + card(high, "High Priority", "#DC2626")
        + card(f"£{exposure:,.0f}", "Stock at Risk", "#D97706", "slow movers + excess stock")
        + card(f"~£{opp:,.0f}", "Sales Opportunity", "#059669", "from range gap corrections")
    )
    if season_count > 0 or total_seasonal_products > 0:
        if total_seasonal_products > 0:
            rate = round(season_count / total_seasonal_products * 100)
            season_val = f"{season_count}/{total_seasonal_products}"
            season_sub = f"{rate}% misclassification rate"
        else:
            season_val = str(season_count)
            season_sub = "seasonal flags"
        cards_html += card(season_val, "Seasonal Mismatches", "#0D9488", season_sub)
    cards_html += "</div>"
    return cards_html


# ---------------------------------------------------------------------------
# Filter bar
# ---------------------------------------------------------------------------

def _filter_bar_html(insights: list[Insight]) -> str:
    priorities = ["HIGH", "MEDIUM", "LOW"]
    present_types = list(dict.fromkeys(i.insight_type for i in insights))

    priority_btns = "".join(
        f'<button onclick="filterPriority(\'{p}\')" id="pf-{p}" class="filter-btn" '
        f'style="background:#fff;border:1px solid #E5E7EB;padding:6px 14px;border-radius:20px;'
        f'font-size:12px;font-weight:600;cursor:pointer;color:#374151;">'
        f'{PRIORITY_ICON.get(p,"")} {p}</button>'
        for p in priorities if any(i.supporting_data.get("_priority") == p for i in insights)
    )

    type_btns = "".join(
        f'<button onclick="filterType(\'{t}\')" id="tf-{t}" class="filter-btn" '
        f'style="background:#fff;border:1px solid #E5E7EB;padding:6px 14px;border-radius:20px;'
        f'font-size:12px;font-weight:600;cursor:pointer;color:{TYPE_COLORS.get(t,"#374151")};">'
        f'{next((s["emoji"] for s in ACTION_SECTIONS if t in s["types"]), "")} '
        f'{ACTION_LABEL.get(t, t)}</button>'
        for t in present_types
    )

    return (
        f'<div id="filter-bar" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;'
        f'background:#fff;border:1px solid #E5E7EB;border-radius:8px;padding:12px 16px;margin-bottom:24px;">'
        f'<span style="font-size:12px;font-weight:700;color:#9CA3AF;text-transform:uppercase;letter-spacing:0.05em;margin-right:4px;">Filter</span>'
        f'<button onclick="clearFilters()" id="pf-ALL" class="filter-btn active-filter" '
        f'style="background:#6366F1;color:#fff;border:1px solid #6366F1;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;">All</button>'
        + priority_btns
        + f'<span style="color:#D1D5DB;margin:0 4px;">|</span>'
        + type_btns
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Decision dashboard table
# ---------------------------------------------------------------------------

def _dashboard_html(insights: list[Insight]) -> str:
    rows = []
    for i, ins in enumerate(insights, 1):
        priority = ins.supporting_data.get("_priority", "LOW")
        c = PRIORITY_COLORS.get(priority, PRIORITY_COLORS["LOW"])
        type_color = TYPE_COLORS.get(ins.insight_type, "#6B7280")
        name = _esc(ins.product_name or ins.category)
        loc = _esc(ins.location_id or "Multiple stores")
        one_liner = _esc(_one_liner(ins))
        impact = _esc(_impact_str(ins))
        action = _esc(ACTION_LABEL.get(ins.insight_type, ins.insight_type))
        section = next((s for s in ACTION_SECTIONS if ins.insight_type in s["types"]), None)
        emoji = section["emoji"] if section else ""

        rows.append(
            f'<tr class="dash-row" data-priority="{priority}" data-type="{ins.insight_type}" '
            f'onclick="scrollToCard(\'card-{i}\')" '
            f'style="cursor:pointer;border-bottom:1px solid #F3F4F6;transition:background 0.15s;" '
            f'onmouseover="this.style.background=\'#F9FAFB\'" onmouseout="this.style.background=\'\'">'
            f'<td style="padding:10px 12px;font-weight:700;color:#6B7280;text-align:center;width:40px;">{i}</td>'
            f'<td style="padding:10px 12px;white-space:nowrap;min-width:110px;">{_priority_badge(priority)}</td>'
            f'<td style="padding:10px 12px;color:{type_color};font-weight:600;font-size:13px;">{emoji} {action}</td>'
            f'<td style="padding:10px 12px;font-weight:600;color:#111827;">{name}</td>'
            f'<td style="padding:10px 12px;color:#6B7280;font-size:13px;">{loc}</td>'
            f'<td style="padding:10px 12px;color:#374151;font-size:13px;">{one_liner}</td>'
            f'<td style="padding:10px 12px;font-weight:700;color:#059669;white-space:nowrap;">{impact}</td>'
            f'</tr>'
        )

    header = (
        '<thead><tr style="background:#F9FAFB;border-bottom:2px solid #E5E7EB;">'
        + "".join(
            f'<th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:700;'
            f'color:#6B7280;text-transform:uppercase;letter-spacing:0.05em;'
            f'{"min-width:110px;white-space:nowrap;" if h == "Priority" else ""}">{h}</th>'
            for h in ["#", "Priority", "Action", "Product / Category", "Store", "Issue", "£ Impact"]
        )
        + "</tr></thead>"
    )

    return (
        f'<div style="background:#fff;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden;margin-bottom:32px;">'
        f'<div style="padding:16px 20px;border-bottom:1px solid #E5E7EB;display:flex;align-items:center;justify-content:space-between;">'
        f'<h2 style="font-size:16px;font-weight:700;color:#111827;margin:0;">Decision Dashboard</h2>'
        f'<span style="font-size:12px;color:#9CA3AF;">Click any row to jump to the detail card</span>'
        f'</div>'
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;" id="dashboard-table">'
        + header
        + "<tbody>" + "".join(rows) + "</tbody>"
        + "</table></div></div>"
    )


# ---------------------------------------------------------------------------
# Detail cards
# ---------------------------------------------------------------------------

def _insight_card_html(ins: Insight, rank: int) -> str:
    priority = ins.supporting_data.get("_priority", "LOW")
    c = PRIORITY_COLORS.get(priority, PRIORITY_COLORS["LOW"])
    type_color = TYPE_COLORS.get(ins.insight_type, "#6B7280")
    name = _esc(ins.product_name or ins.category)
    loc_str = f" — {_esc(ins.location_id)}" if ins.location_id else ""
    narrative = _esc(ins.narrative or "")
    action = _esc(ins.recommended_action or "")
    impact = _impact_str(ins)
    ctx_table = _context_table_html(ins.supporting_data, ins.insight_type)

    is_expanded = priority == "HIGH"
    body_display = "block" if is_expanded else "none"
    chevron_transform = "rotate(180deg)" if is_expanded else "rotate(0deg)"
    impact_span = f'<span style="font-size:13px;font-weight:700;color:#059669;">{_esc(impact)}</span>' if "£" in impact else ""
    ctx_html = f'<div style="margin-bottom:16px;">{ctx_table}</div>' if ctx_table else ""
    signal_tag = SIGNAL_TAGS.get(ins.insight_type, "")
    signal_bar = _online_signal_bar(ins.supporting_data) if ins.insight_type == "RANGE_GAP" else ""
    trade_pack_html = _trade_pack_miss_html(ins.insight_type)

    # Rank chip for RANGE_GAP; weeks chip for SEASON_MISMATCH
    extra_chip = ""
    if ins.insight_type == "RANGE_GAP":
        d_data = ins.supporting_data
        n = d_data.get("category_product_count", 0)
        if n > 0:
            online_r = d_data.get("online_rank_num", "—")
            store_r = d_data.get("store_rank_num", "—")
            if d_data.get("is_missing_from_range"):
                extra_chip = (
                    f'<span style="font-size:11px;color:#DC2626;font-weight:700;'
                    f'background:#FEF2F2;border:1px solid #FCA5A5;padding:2px 10px;border-radius:8px;">'
                    f'Not ranged · #{online_r:,}/{n:,} online</span>'
                )
            else:
                extra_chip = (
                    f'<span style="font-size:11px;color:#1E40AF;font-weight:700;'
                    f'background:#EFF6FF;border:1px solid #BFDBFE;padding:2px 10px;border-radius:8px;">'
                    f'#{online_r:,}/{n:,} → #{store_r:,}/{n:,}</span>'
                )
    elif ins.insight_type == "SEASON_MISMATCH":
        direction = ins.supporting_data.get("direction", "seasonal_to_continuity")
        if direction == "continuity_to_seasonal":
            peak_pct = ins.supporting_data.get("peak_window_pct", 0)
            extra_chip = (
                f'<span style="font-size:11px;color:#0D9488;font-weight:700;'
                f'background:#F0FDFA;border:1px solid #99F6E4;padding:2px 10px;border-radius:8px;">'
                f'{peak_pct:.0f}% in peak season</span>'
            )
        else:
            oos = ins.supporting_data.get("out_of_season_selling_weeks", 0)
            extra_chip = (
                f'<span style="font-size:11px;color:#0D9488;font-weight:700;'
                f'background:#F0FDFA;border:1px solid #99F6E4;padding:2px 10px;border-radius:8px;">'
                f'{oos} wks out-of-season</span>'
            )

    header_div = (
        f'<div onclick="toggleCard(\'card-{rank}\')" '
        f'style="display:flex;align-items:center;justify-content:space-between;'
        f'padding:14px 18px;background:{c["bg"]};cursor:pointer;">'
        f'<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
        f'<span style="font-size:14px;font-weight:700;color:{type_color};">{rank}.</span>'
        f'<span style="font-size:14px;font-weight:700;color:#111827;">{name}{loc_str}</span>'
        f'{_priority_badge(priority)}'
        f'{extra_chip}'
        f'{"" if extra_chip else f"""<span style="font-size:11px;color:#6B7280;font-style:italic;">{_esc(signal_tag)}</span>"""}'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:12px;flex-shrink:0;">'
        f'{impact_span}'
        f'<svg id="chevron-{rank}" style="width:18px;height:18px;color:#9CA3AF;transition:transform 0.2s;transform:{chevron_transform};" fill="none" viewBox="0 0 24 24" stroke="currentColor">'
        f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>'
        f'</div></div>'
    )

    body_div = (
        f'<div id="body-{rank}" style="display:{body_display};padding:18px;background:#fff;border-top:1px solid {c["border"]};">'
        f'<p style="font-size:14px;color:#374151;line-height:1.6;margin:0 0 16px 0;">{narrative}</p>'
        f'{signal_bar}'
        f'{ctx_html}'
            f'<div style="background:#F0FDF4;border-left:3px solid #16A34A;padding:10px 14px;border-radius:0 6px 6px 0;">'
        f'<span style="font-size:12px;font-weight:700;color:#16A34A;text-transform:uppercase;letter-spacing:0.05em;">Action</span>'
        f'<p style="font-size:13px;color:#111827;font-weight:600;margin:4px 0 0 0;">{action}</p>'
        f'</div></div>'
    )

    return (
        f'<div id="card-{rank}" class="insight-card" data-priority="{priority}" data-type="{ins.insight_type}" '
        f'style="border:1px solid {c["border"]};border-radius:8px;overflow:hidden;margin-bottom:12px;">'
        + header_div + body_div +
        f'</div>'
    )


def _detail_sections_html(insights: list[Insight]) -> str:
    sections_html = []
    for section in ACTION_SECTIONS:
        section_insights = [i for i in insights if i.insight_type in section["types"]]
        if not section_insights:
            continue

        type_key = section["types"][0]
        type_color = TYPE_COLORS.get(type_key, "#6B7280")

        cards = "".join(
            _insight_card_html(ins, insights.index(ins) + 1)
            for ins in section_insights
        )

        types_attr = " ".join(section["types"])
        sections_html.append(
            f'<div class="action-section" data-types="{types_attr}" style="margin-bottom:32px;">'
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">'
            f'<span style="font-size:22px;">{section["emoji"]}</span>'
            f'<div>'
            f'<h2 style="font-size:17px;font-weight:700;color:#111827;margin:0;">{section["title"]}</h2>'
            f'<p style="font-size:13px;color:#6B7280;margin:2px 0 0 0;">{section["subtitle"]}</p>'
            f'</div>'
            f'<span style="margin-left:auto;background:{type_color}18;color:{type_color};'
            f'border:1px solid {type_color}44;padding:2px 10px;border-radius:12px;'
            f'font-size:12px;font-weight:700;">{len(section_insights)}</span>'
            f'</div>'
            + cards
            + "</div>"
        )

    return "\n".join(sections_html)


# ---------------------------------------------------------------------------
# JS
# ---------------------------------------------------------------------------

JS = """
let activePriority = null;
let activeType = null;

function applyFilters() {
  /* Filter insights table rows */
  document.querySelectorAll('.opp-row').forEach(row => {
    const mp = !activePriority || row.dataset.priority === activePriority;
    const mt = !activeType || row.dataset.type === activeType;
    row.dataset.filtered = (mp && mt) ? '' : 'hidden';
  });
  oppPage = 0;
  oppPaginate();

  /* Filter detail cards */
  document.querySelectorAll('.insight-card').forEach(card => {
    const mp = !activePriority || card.dataset.priority === activePriority;
    const mt = !activeType || card.dataset.type === activeType;
    card.style.display = (mp && mt) ? '' : 'none';
  });
  document.querySelectorAll('.action-section').forEach(section => {
    const types = section.dataset.types.split(' ');
    const typeMatch = !activeType || types.includes(activeType);
    const visibleCards = section.querySelectorAll('.insight-card:not([style*="display: none"])');
    section.style.display = (typeMatch && visibleCards.length > 0) ? '' : 'none';
  });
}

function filterPriority(p) {
  activePriority = (activePriority === p) ? null : p;
  updateFilterButtons();
  applyFilters();
}

function filterType(t) {
  activeType = (activeType === t) ? null : t;
  updateFilterButtons();
  applyFilters();
}

function clearFilters() {
  activePriority = null;
  activeType = null;
  updateFilterButtons();
  applyFilters();
}

function updateFilterButtons() {
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.classList.remove('active-filter');
    btn.style.background = '#fff';
    btn.style.color = btn.dataset.color || '#374151';
    btn.style.borderColor = '#E5E7EB';
  });
  const allBtn = document.getElementById('pf-ALL');
  if (!activePriority && !activeType) {
    allBtn.style.background = '#6366F1';
    allBtn.style.color = '#fff';
    allBtn.style.borderColor = '#6366F1';
    allBtn.classList.add('active-filter');
  }
  if (activePriority) {
    const btn = document.getElementById('pf-' + activePriority);
    if (btn) { btn.style.background = '#374151'; btn.style.color = '#fff'; btn.style.borderColor = '#374151'; }
  }
  if (activeType) {
    const btn = document.getElementById('tf-' + activeType);
    if (btn) { btn.style.background = '#374151'; btn.style.color = '#fff'; btn.style.borderColor = '#374151'; }
  }
}

function toggleCard(id) {
  const body = document.getElementById('body-' + id.replace('card-', ''));
  const chevron = document.getElementById('chevron-' + id.replace('card-', ''));
  if (!body) return;
  const isOpen = body.style.display !== 'none';
  body.style.display = isOpen ? 'none' : 'block';
  if (chevron) chevron.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(180deg)';
}

function scrollToCard(id) {
  const card = document.getElementById(id);
  if (!card) return;
  const rank = id.replace('card-', '');
  const body = document.getElementById('body-' + rank);
  const chevron = document.getElementById('chevron-' + rank);
  if (body && body.style.display === 'none') {
    body.style.display = 'block';
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }
  setTimeout(() => card.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
}

function expandAll() {
  document.querySelectorAll('[id^="body-"]').forEach(b => b.style.display = 'block');
  document.querySelectorAll('[id^="chevron-"]').forEach(c => c.style.transform = 'rotate(180deg)');
}

function collapseAll() {
  document.querySelectorAll('[id^="body-"]').forEach(b => b.style.display = 'none');
  document.querySelectorAll('[id^="chevron-"]').forEach(c => c.style.transform = 'rotate(0deg)');
}

/* --- Opportunity table pagination --- */
var oppPage = 0;
var oppPageSize = 20;

function oppPaginate() {
  var allRows = document.querySelectorAll('.opp-row');
  var visible = [];
  allRows.forEach(function(r) { if (r.dataset.filtered !== 'hidden') visible.push(r); });
  var total = visible.length;
  allRows.forEach(function(r) { r.style.display = 'none'; });
  visible.forEach(function(r, i) {
    r.style.display = (i >= oppPage * oppPageSize && i < (oppPage + 1) * oppPageSize) ? '' : 'none';
  });
  var rangeEl = document.getElementById('opp-range');
  if (rangeEl) rangeEl.textContent = total === 0 ? '0 of 0' : (oppPage * oppPageSize + 1) + '\u2013' + Math.min((oppPage + 1) * oppPageSize, total) + ' of ' + total;
  var prevBtn = document.getElementById('opp-prev');
  var nextBtn = document.getElementById('opp-next');
  if (prevBtn) prevBtn.disabled = oppPage === 0;
  if (nextBtn) nextBtn.disabled = (oppPage + 1) * oppPageSize >= total;
}

function oppPrev() { if (oppPage > 0) { oppPage--; oppPaginate(); } }
function oppNext() { var total = document.querySelectorAll('.opp-row').length; if ((oppPage + 1) * oppPageSize < total) { oppPage++; oppPaginate(); } }
function oppChangePageSize() { oppPageSize = parseInt(document.getElementById('opp-page-size').value); oppPage = 0; oppPaginate(); }

document.addEventListener('DOMContentLoaded', function() { oppPaginate(); });
"""

PRINT_CSS = """
@media print {
  #top-bar .no-print, #filter-bar, #expand-controls { display: none !important; }
  #top-bar { position: static !important; box-shadow: none !important; }
  .dash-row { display: table-row !important; }
  .insight-card { display: block !important; break-inside: avoid; }
  [id^="body-"] { display: block !important; }
  .action-section { break-before: auto; }
  body { padding-top: 0 !important; }
  @page { margin: 20mm; }
}
"""


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_html_report(
    insights: list[Insight],
    config: AnalysisConfig,
    run_date: str | None = None,
    total_seasonal_products: int = 0,
) -> str:
    from datetime import datetime
    if run_date is None:
        run_date = datetime.now().strftime("%d %B %Y")

    high = sum(1 for i in insights if i.supporting_data.get("_priority") == "HIGH")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Range Monitoring — Weekly Alerts — {_esc(run_date)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', system-ui, sans-serif; background: #F3F4F6; color: #111827; padding-top: 72px; }}
    {PRINT_CSS}
  </style>
</head>
<body>

<!-- Sticky top bar -->
<div id="top-bar" style="position:fixed;top:0;left:0;right:0;z-index:100;background:#1E1B4B;
  box-shadow:0 2px 8px rgba(0,0,0,0.18);display:flex;align-items:center;
  justify-content:space-between;padding:0 32px;height:60px;">
  <div style="display:flex;align-items:center;gap:16px;">
    <span style="font-size:16px;font-weight:800;color:#fff;letter-spacing:-0.02em;">
      Range Monitoring Agent
    </span>
    <span style="color:#818CF8;font-size:12px;">Cross-channel range intelligence</span>
    <span style="background:#374151;color:#D1D5DB;padding:2px 8px;border-radius:4px;font-size:11px;">
      w/e {_esc(run_date)}
    </span>
    <span style="background:#DC2626;color:#fff;padding:2px 10px;border-radius:12px;
      font-size:12px;font-weight:700;">{high} HIGH</span>
  </div>
  <div class="no-print" style="display:flex;gap:10px;align-items:center;">
    <button onclick="expandAll()" style="background:#312E81;color:#C7D2FE;border:none;
      padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">
      Expand All
    </button>
    <button onclick="collapseAll()" style="background:#312E81;color:#C7D2FE;border:none;
      padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">
      Collapse All
    </button>
  </div>
</div>

<!-- Main content -->
<div style="max-width:1280px;margin:0 auto;padding:28px 32px;">

  <!-- KPI cards -->
  {_kpi_cards_html(insights, total_seasonal_products)}

  <!-- Filter bar (filters table + detail cards) -->
  {_filter_bar_html(insights)}

  <!-- Main insights table -->
  {_insights_table_html(insights)}

  <!-- Charts -->
  {_charts_section_html(insights)}

  <!-- Detail section -->
  <div style="border-top:2px solid #E5E7EB;padding-top:24px;margin-top:8px;">
    <div id="expand-controls" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
      <div>
        <h2 style="font-size:20px;font-weight:800;color:#111827;margin:0;">Range Alerts — Detail</h2>
        <p style="font-size:13px;color:#6B7280;margin:2px 0 0 0;">Click any card to expand the full cross-channel signal and recommended action</p>
      </div>
      <div style="display:flex;gap:8px;">
        <button onclick="expandAll()" style="background:#fff;border:1px solid #E5E7EB;
          padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;color:#374151;">
          Expand All
        </button>
        <button onclick="collapseAll()" style="background:#fff;border:1px solid #E5E7EB;
          padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;color:#374151;">
          Collapse All
        </button>
      </div>
    </div>
    {_detail_sections_html(insights)}
  </div>

  <!-- Footer -->
  <div style="border-top:1px solid #E5E7EB;margin-top:32px;padding-top:20px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <span style="font-size:12px;color:#9CA3AF;">
        Range Monitoring Agent — generated {_esc(run_date)}
      </span>
      <span style="font-size:12px;color:#9CA3AF;">
        Rank gap ≥{config.rank_mismatch_threshold:.0f} pts &nbsp;|&nbsp;
        Sell-through &lt;{config.slow_mover_sell_through*100:.0f}% &nbsp;|&nbsp;
        Season mismatch ≥{config.seasonal_consistency_weeks} wks &nbsp;|&nbsp;
        Stock imbalance ≥{config.stock_imbalance_multiple:.1f}× peer
      </span>
    </div>
  </div>

</div>

<script>{JS}</script>
</body>
</html>"""

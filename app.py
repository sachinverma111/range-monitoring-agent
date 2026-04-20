"""
Range Monitoring Agent — Streamlit interface.

Run with:
    streamlit run app.py
"""

import json
import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Range Monitoring Agent",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS — dark sidebar, custom fonts, card polish
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Sidebar ────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: #0F1117;
    border-right: 1px solid #1E2130;
}
section[data-testid="stSidebar"] * {
    color: #CBD5E1 !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #F1F5F9 !important;
}
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] .stCheckbox label {
    color: #94A3B8 !important;
    font-size: 12px !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid #1E2130 !important;
    background: #161B27 !important;
    border-radius: 8px !important;
}
section[data-testid="stSidebar"] details {
    background: #161B27 !important;
    border-radius: 8px !important;
}
section[data-testid="stSidebar"] details summary {
    background: #161B27 !important;
    color: #CBD5E1 !important;
}
section[data-testid="stSidebar"] details summary:hover {
    background: #1E2130 !important;
}
section[data-testid="stSidebar"] details summary p,
section[data-testid="stSidebar"] details summary span {
    color: #CBD5E1 !important;
}
section[data-testid="stSidebar"] hr {
    border-color: #1E2130 !important;
}

/* ── Main background ────────────────────────────────── */
.main .block-container {
    background: #F8FAFF;
    padding-top: 0 !important;
}

/* ── File uploader cards ────────────────────────────── */
[data-testid="stFileUploader"] {
    background: #fff;
    border: 1.5px dashed #C7D2FE;
    border-radius: 12px;
    padding: 4px 12px;
}
[data-testid="stFileUploader"]:hover {
    border-color: #6366F1;
}

/* ── Primary button ─────────────────────────────────── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%);
    border: none;
    border-radius: 10px;
    color: #fff;
    font-weight: 700;
    font-size: 15px;
    padding: 12px 32px;
    letter-spacing: 0.02em;
    box-shadow: 0 4px 15px rgba(99, 102, 241, 0.35);
    transition: transform 0.15s, box-shadow 0.15s;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45);
}

/* ── Metric cards ────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #fff;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
[data-testid="stMetricLabel"] { color: #6B7280 !important; font-size: 12px !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.05em; }
[data-testid="stMetricValue"] { color: #111827 !important; font-size: 28px !important; font-weight: 800 !important; }

/* ── Download buttons ────────────────────────────────── */
.stDownloadButton > button {
    background: #fff;
    border: 1.5px solid #E5E7EB;
    border-radius: 8px;
    color: #374151;
    font-weight: 600;
    font-size: 13px;
    width: 100%;
    padding: 10px 0;
    transition: border-color 0.15s, background 0.15s;
}
.stDownloadButton > button:hover {
    border-color: #6366F1;
    color: #6366F1;
    background: #F5F3FF;
}

/* ── Dividers ───────────────────────────────────────── */
hr { border-color: #E5E7EB !important; }

/* ── Spinner ────────────────────────────────────────── */
.stSpinner > div { border-top-color: #6366F1 !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Hero header
# ---------------------------------------------------------------------------
st.markdown("""
<div style="
    background: linear-gradient(135deg, #0F1117 0%, #1E1B4B 60%, #312E81 100%);
    border-radius: 0 0 20px 20px;
    padding: 36px 40px 32px 40px;
    margin: -1rem -1rem 32px -1rem;
    position: relative;
    overflow: hidden;
">
  <!-- Decorative orb -->
  <div style="
    position:absolute;right:-60px;top:-60px;
    width:260px;height:260px;
    background:radial-gradient(circle, rgba(99,102,241,0.25) 0%, transparent 70%);
    border-radius:50%;pointer-events:none;
  "></div>

  <h1 style="
    font-family:'Inter',sans-serif;
    font-size:32px;font-weight:800;
    color:#F8FAFF;margin:0 0 8px 0;
    letter-spacing:-0.02em;line-height:1.2;
  ">
    📡 Range Monitoring Agent
  </h1>
  <p style="
    font-size:15px;color:#A5B4FC;margin:0;
    font-weight:500;letter-spacing:0.01em;
  ">
    Catch ranging gaps, slow movers, and stock imbalances before the next review cycle.
  </p>

  <!-- Capability chips -->
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:20px;">
    <span style="background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.4);
      color:#C7D2FE;font-size:11px;font-weight:600;border-radius:20px;padding:4px 12px;">
      📦 Range Gaps
    </span>
    <span style="background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.4);
      color:#C7D2FE;font-size:11px;font-weight:600;border-radius:20px;padding:4px 12px;">
      📉 Slow Movers
    </span>
    <span style="background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.4);
      color:#C7D2FE;font-size:11px;font-weight:600;border-radius:20px;padding:4px 12px;">
      🔄 Stock Imbalances
    </span>
    <span style="background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.4);
      color:#C7D2FE;font-size:11px;font-weight:600;border-radius:20px;padding:4px 12px;">
      🌡 Season Mismatches
    </span>
    <span style="background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.4);
      color:#C7D2FE;font-size:11px;font-weight:600;border-radius:20px;padding:4px 12px;">
      🗂 Category Divergence
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("""
    <div style="padding:4px 0 16px 0;">
      <div style="font-size:11px;color:#475569;font-weight:700;letter-spacing:0.1em;
        text-transform:uppercase;margin-bottom:4px;">Configuration</div>
      <div style="font-size:13px;color:#94A3B8;">Adjust thresholds, then run.</div>
    </div>
    """, unsafe_allow_html=True)

    top_n = st.slider("Max insights to surface", min_value=5, max_value=50, value=20, step=5)

    with st.expander("Rule thresholds", expanded=False):
        rank_threshold = st.slider(
            "Range gap: rank delta (percentile pts)",
            min_value=10, max_value=60, value=30,
            help="How many percentile points below online rank a store must be to generate a RANGE_GAP alert.",
        )
        slow_mover_st = st.slider(
            "Slow mover: max sell-through %",
            min_value=1, max_value=30, value=10,
        )
        slow_mover_weeks = st.slider(
            "Slow mover: rolling window (weeks)",
            min_value=2, max_value=12, value=4,
        )
        stock_multiple = st.slider(
            "Stock imbalance: WOC multiple vs peers",
            min_value=1.5, max_value=5.0, value=2.0, step=0.5,
        )
        min_units = st.slider(
            "Min online units per product",
            min_value=1, max_value=20, value=5,
        )

    st.divider()

# ---------------------------------------------------------------------------
# Step 1 — Data input
# ---------------------------------------------------------------------------
st.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
  <div style="background:#EEF2FF;border-radius:8px;width:28px;height:28px;
    display:flex;align-items:center;justify-content:center;
    font-size:13px;font-weight:800;color:#6366F1;">1</div>
  <div style="font-size:17px;font-weight:700;color:#111827;">Load data files</div>
</div>
""", unsafe_allow_html=True)

products_file = online_file = stores_file = calendar_file = None
products_path = online_path = stores_path = calendar_path = None

col1, col2 = st.columns(2)
with col1:
    products_file = st.file_uploader(
        "Product master (required)", type=["csv", "xlsx"],
        help="Required columns: product_id · product_name · category\nOptional: brand · range_tag · season · price",
    )
    online_file = st.file_uploader(
        "Online sales (required)", type=["csv", "xlsx"],
        help="Required columns: product_id · period · units_sold\nOptional: revenue",
    )
with col2:
    stores_file = st.file_uploader(
        "Store sales (required)", type=["csv", "xlsx"],
        help="Required columns: product_id · location_id · period · units_sold\nOptional: stock_on_hand · revenue",
    )
    calendar_file = st.file_uploader(
        "Business calendar (optional)", type=["csv", "xlsx"],
        help="Required for season mismatch detection.\nColumns: range_tag · season · active_from · active_to",
    )

# Demo mode
sample_dir = Path(__file__).parent / "sample_data"
has_sample = all(
    (sample_dir / f).exists()
    for f in ["products.csv", "online_sales.csv", "store_sales.csv", "calendar.csv"]
)
use_sample = False
if has_sample:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    use_sample = st.checkbox(
        "Use built-in sample data (demo mode)",
        help="Loads the synthetic dataset included with the agent.",
    )

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Step 2 — Run
# ---------------------------------------------------------------------------
st.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
  <div style="background:#EEF2FF;border-radius:8px;width:28px;height:28px;
    display:flex;align-items:center;justify-content:center;
    font-size:13px;font-weight:800;color:#6366F1;">2</div>
  <div style="font-size:17px;font-weight:700;color:#111827;">Run the analysis</div>
</div>
""", unsafe_allow_html=True)

run_clicked = st.button("▶  Run Analysis", type="primary")

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
if run_clicked:
    # Resolve which input mode is active
    using_paths = any([products_path, online_path, stores_path])
    using_uploads = any([products_file, online_file, stores_file])

    if not use_sample and not using_paths and not using_uploads:
        st.error("Provide files via Upload or Local file paths, or enable demo mode.")
        st.stop()

    if using_paths and not all([products_path, online_path, stores_path]):
        st.error("Please fill in all three required local paths (products, online sales, store sales).")
        st.stop()

    if using_uploads and not all([products_file, online_file, stores_file]):
        st.error("Please upload all three required files (products, online sales, store sales).")
        st.stop()

    from range_monitor.config import AnalysisConfig
    from range_monitor.delivery import build_narratives, render_markdown_report
    from range_monitor.engine import run_analysis
    from range_monitor.html_report import render_html_report
    from range_monitor.ingestion import load_calendar, load_online_sales, load_products, load_store_sales

    config = AnalysisConfig(
        rank_mismatch_threshold=float(rank_threshold),
        slow_mover_sell_through=slow_mover_st / 100.0,
        slow_mover_window_weeks=slow_mover_weeks,
        stock_imbalance_multiple=stock_multiple,
        min_units_threshold=min_units,
        top_insights_count=top_n,
    )

    def _save_upload(uploaded) -> Path:
        suffix = Path(uploaded.name).suffix
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(uploaded.read())
        tmp.flush()
        return Path(tmp.name)

    def _resolve(uploaded, path_str: str) -> Path | None:
        """Return a Path from either an uploaded file or a typed path string."""
        if path_str and path_str.strip():
            p = Path(path_str.strip())
            if not p.exists():
                st.error(f"File not found: {p}")
                st.stop()
            return p
        if uploaded:
            return _save_upload(uploaded)
        return None

    total_seasonal_products = 0
    with st.spinner("Agent is scanning your range data…"):
        try:
            if use_sample:
                products     = load_products(sample_dir / "products.csv")
                online_sales = load_online_sales(sample_dir / "online_sales.csv")
                store_sales  = load_store_sales(sample_dir / "store_sales.csv")
                calendar     = load_calendar(sample_dir / "calendar.csv")
            else:
                products     = load_products(_resolve(products_file, products_path))
                online_sales = load_online_sales(_resolve(online_file, online_path))
                store_sales  = load_store_sales(_resolve(stores_file, stores_path))
                cal_path     = _resolve(calendar_file, calendar_path)
                calendar     = load_calendar(cal_path) if cal_path else None

            insights = run_analysis(products, online_sales, store_sales, calendar, config)
            insights = build_narratives(insights)

            # Count seasonal products for misclassification rate KPI
            if "range_tag" in products.columns:
                total_seasonal_products = int((products["range_tag"] == "seasonal").sum())

        except (FileNotFoundError, ValueError) as exc:
            st.error(f"Data error: {exc}")
            st.stop()

    if not insights:
        st.warning("No insights generated. Try lowering thresholds in the sidebar.")
        st.stop()

    # ── Report ───────────────────────────────────────────────────────────
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    html_report = render_html_report(insights, config, total_seasonal_products=total_seasonal_products)

    import streamlit.components.v1 as components
    components.html(html_report, height=1800, scrolling=True)

    # ── Downloads ────────────────────────────────────────────────────────
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
      <div style="background:#EEF2FF;border-radius:8px;width:28px;height:28px;
        display:flex;align-items:center;justify-content:center;
        font-size:13px;font-weight:800;color:#6366F1;">3</div>
      <div style="font-size:17px;font-weight:700;color:#111827;">Export</div>
    </div>
    """, unsafe_allow_html=True)

    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button(
            "⬇  HTML Report",
            data=html_report,
            file_name="range_monitoring_report.html",
            mime="text/html",
            use_container_width=True,
        )
    with dl2:
        insights_json = json.dumps([
            {
                "insight_type":      i.insight_type,
                "product_id":        i.product_id,
                "product_name":      i.product_name,
                "category":          i.category,
                "location_id":       i.location_id,
                "score":             round(i.score, 4),
                "narrative":         i.narrative,
                "recommended_action": i.recommended_action,
                "supporting_data":   {k: v for k, v in i.supporting_data.items() if not k.startswith("_")},
            }
            for i in insights
        ], indent=2)
        st.download_button(
            "⬇  JSON",
            data=insights_json,
            file_name="range_monitoring_insights.json",
            mime="application/json",
            use_container_width=True,
        )
    with dl3:
        md_report = render_markdown_report(insights, config)
        st.download_button(
            "⬇  Markdown",
            data=md_report,
            file_name="range_monitoring_report.md",
            mime="text/markdown",
            use_container_width=True,
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="border-top:1px solid #E5E7EB;padding-top:16px;
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
  <span style="font-size:12px;color:#9CA3AF;">
    Range Monitoring Agent &nbsp;·&nbsp; Rules-based cross-channel intelligence
  </span>
  <span style="font-size:12px;color:#9CA3AF;">
    Connects to: Markdown &nbsp;·&nbsp; Replenish &nbsp;·&nbsp; Rebuy
  </span>
</div>
""", unsafe_allow_html=True)

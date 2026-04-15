# Range Monitoring Agent — TODO

## Q1: Elevate Beyond BI ("Did You Know?" Insights)

- [ ] **Brand-level divergence rule** — detect brands trending strongly online but underperforming in specific store clusters or regions. The spec explicitly calls this out as a target insight type. Similar structure to category divergence but at brand level, with regional grouping of stores.

- [ ] **Peer sell-through comparison rule** — surface when a store's sell-through for a product is dramatically lower than peer stores carrying the same product (e.g. 4× below the peer average). Currently slow mover detection flags absolute sell-through but doesn't make the peer contrast the centrepiece. This is the dramatic, specific signal that feels revelatory.

- [ ] **Reframe narratives with "did you know?" energy** — narratives currently describe a situation. They should open with the surprise. Lead with the unexpected finding ("One of your stores is selling virtually no Smart Watches while your online channel ranks it a top 5 Electronics product") rather than the analytical setup.

- [ ] **Trending / emerging product detection** — identify products that are newly climbing the online rankings (week-on-week momentum) before the pattern shows up in store data. Early signal for range decisions before the next review cycle.

---

## Q2: Natural Upsell Path to Deeper Modules

- [ ] **REORDER_SIGNAL rule** — detect products with high online demand + low weeks of cover across multiple stores simultaneously. This is the Rebuy signal: genuine demand exists but stock is running thin. Currently no rule covers this.

- [ ] **Module callout chips on insight cards** — add a small labelled tag to each card in the HTML report pointing to the relevant downstream module:
  - SLOW_MOVER → `Markdown`
  - STOCK_IMBALANCE → `Replenish`
  - RANGE_GAP → `Replenish`
  - REORDER_SIGNAL → `Rebuy`
  - SEASON_MISMATCH → `Rebuy` (continuity products need forward buying)
  This makes the upsell path visible without being pushy — it's just context.

- [ ] **Module summary in the report header** — group insights by which module they point toward in the "This Week at a Glance" section. One line per module: "3 slow movers flagged → candidate list for Markdown review".

---

## Optional: Infrastructure & Privacy

- [ ] **Temp file cleanup after analysis** — uploaded CSV/Excel files are written to `/tmp/` via `tempfile.NamedTemporaryFile(delete=False)` in `app.py` and are not removed after the run. For a deployed instance handling real trading data, add a `finally` block in the analysis section to delete temp files once ingestion is complete. Low priority for local/demo use; important before any multi-user deployment.

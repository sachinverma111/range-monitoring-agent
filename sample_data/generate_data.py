"""
Script to generate synthetic online and store sales data.
Run once: python sample_data/generate_data.py
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta

rng = np.random.default_rng(42)

# Week ending dates (12 weeks ending 2025-03-30)
weeks = [date(2025, 1, 5) + timedelta(weeks=i) for i in range(13)]

products = pd.read_csv("sample_data/products.csv")
pids = products["product_id"].tolist()
locations = ["LOC_MANCHESTER", "LOC_LONDON_OXFORD", "LOC_BIRMINGHAM", "LOC_EDINBURGH", "LOC_BRISTOL"]

# --- Base online demand (higher = more popular online) ---
# Deliberately make some products strong online but weak in certain stores
online_base = {pid: int(rng.integers(5, 150)) for pid in pids}
# Boost specific products to create RANGE_GAP triggers
for pid in ["P003", "P008", "P026", "P046", "P047"]:
    online_base[pid] = rng.integers(120, 200)
# Keep some products weak online (genuine slow movers)
for pid in ["P038", "P041", "P013", "P014"]:
    online_base[pid] = rng.integers(2, 8)

# --- Online sales ---
online_rows = []
for pid in pids:
    base = online_base[pid]
    for week in weeks:
        units = max(0, int(rng.normal(base, base * 0.2)))
        revenue = round(units * float(products.loc[products.product_id == pid, "price"].values[0]), 2)
        online_rows.append({
            "product_id": pid,
            "period": week.isoformat(),
            "units_sold": units,
            "revenue": revenue,
        })

online_df = pd.DataFrame(online_rows)
online_df.to_csv("sample_data/online_sales.csv", index=False)
print(f"Online sales: {len(online_df)} rows")

# --- Store sales ---
# Each product has a store-level multiplier; some products deliberately underperform in certain stores
store_rows = []
loc_multipliers = {loc: rng.uniform(0.4, 1.2) for loc in locations}

# Products that should trigger RANGE_GAP: strong online but weak at specific stores
range_gap_pairs = {
    "P003": "LOC_MANCHESTER",      # White Trainer Low — strong online, weak Manchester
    "P008": "LOC_EDINBURGH",       # Platform Sneaker — strong online, weak Edinburgh
    "P026": "LOC_BIRMINGHAM",      # Yoga Leggings — strong online, weak Birmingham
    "P046": "LOC_BRISTOL",         # Smart Watch — strong online, weak Bristol
    "P047": "LOC_LONDON_OXFORD",   # Wireless Earbuds — strong online, weak London
}

for pid in pids:
    product_price = float(products.loc[products.product_id == pid, "price"].values[0])
    base_online = online_base[pid]
    for loc in locations:
        multiplier = loc_multipliers[loc]
        # Apply deliberate underperformance for RANGE_GAP targets
        if pid in range_gap_pairs and range_gap_pairs[pid] == loc:
            multiplier *= 0.08  # very low in-store vs online
        for week in weeks:
            store_base = max(0, base_online * multiplier * rng.uniform(0.5, 1.5))
            units = max(0, int(rng.normal(store_base, store_base * 0.25 + 0.1)))
            # Stock on hand: simulate replenishment
            soh = max(units, int(rng.normal(units * 4, units * 1.5 + 2)))
            # Create deliberate STOCK_IMBALANCE at one location for some products
            if pid in ["P036", "P044"] and loc == "LOC_MANCHESTER":
                soh = units * 12  # massively overstocked
            revenue = round(units * product_price, 2)
            store_rows.append({
                "product_id": pid,
                "location_id": loc,
                "period": week.isoformat(),
                "units_sold": units,
                "stock_on_hand": soh,
                "revenue": revenue,
            })

store_df = pd.DataFrame(store_rows)
store_df.to_csv("sample_data/store_sales.csv", index=False)
print(f"Store sales: {len(store_df)} rows")

# --- Business calendar ---
# Include some "seasonal" products that sell consistently out-of-season (SEASON_MISMATCH triggers)
calendar_rows = [
    # Normal seasonal windows
    {"range_tag": "seasonal", "season": "AW25", "active_from": "2024-09-01", "active_to": "2025-02-28"},
    {"range_tag": "seasonal", "season": "SS25", "active_from": "2025-03-01", "active_to": "2025-08-31"},
    # Continuity has no dates
    {"range_tag": "continuity", "season": "", "active_from": "", "active_to": ""},
]
calendar_df = pd.DataFrame(calendar_rows)
calendar_df.to_csv("sample_data/calendar.csv", index=False)
print(f"Calendar: {len(calendar_df)} rows")

print("\nDone. Files written to sample_data/")

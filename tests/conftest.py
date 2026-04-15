"""Shared fixtures for Range Monitoring Agent tests."""

import pandas as pd
import pytest

from range_monitor.config import AnalysisConfig


@pytest.fixture
def config() -> AnalysisConfig:
    return AnalysisConfig(
        rank_mismatch_threshold=30.0,
        slow_mover_sell_through=0.10,
        slow_mover_window_weeks=4,
        seasonal_consistency_weeks=3,
        min_units_threshold=2,
        top_insights_count=20,
    )


@pytest.fixture
def products() -> pd.DataFrame:
    return pd.DataFrame([
        {"product_id": "P001", "product_name": "Classic Trainer", "category": "Footwear", "brand": "Nike", "range_tag": "continuity", "season": None, "price": 80.0},
        {"product_id": "P002", "product_name": "Running Shoe", "category": "Footwear", "brand": "Adidas", "range_tag": "continuity", "season": None, "price": 100.0},
        {"product_id": "P003", "product_name": "Summer Sandal", "category": "Footwear", "brand": "Birkenstock", "range_tag": "seasonal", "season": "SS25", "price": 60.0},
        {"product_id": "P004", "product_name": "Yoga Legging", "category": "Sportswear", "brand": "Lululemon", "range_tag": "continuity", "season": None, "price": 85.0},
        {"product_id": "P005", "product_name": "Leather Bag", "category": "Accessories", "brand": "Coach", "range_tag": "continuity", "season": None, "price": 200.0},
    ])


@pytest.fixture
def online_sales() -> pd.DataFrame:
    """P001 is high-demand online (triggers rank_mismatch), P002 moderate, P003 sells out-of-season."""
    rows = []
    periods = pd.date_range("2024-10-06", periods=13, freq="7D")
    units_map = {"P001": 120, "P002": 40, "P003": 50, "P004": 90, "P005": 15}
    for pid, base_units in units_map.items():
        for period in periods:
            rows.append({"product_id": pid, "period": period, "units_sold": base_units, "revenue": base_units * 10.0})
    return pd.DataFrame(rows)


@pytest.fixture
def store_sales() -> pd.DataFrame:
    """
    LOC_A: P001 sells very low (triggers rank_mismatch).
    LOC_B: P001 sells normally.
    P004 at LOC_A has low sell-through (triggers slow_mover).
    P005 at LOC_A is overstocked vs peers (triggers stock_imbalance).
    """
    rows = []
    periods = pd.date_range("2024-10-06", periods=13, freq="7D")
    locations = ["LOC_A", "LOC_B", "LOC_C"]

    store_units = {
        ("P001", "LOC_A"): 3,    # very low vs online — triggers RANGE_GAP
        ("P001", "LOC_B"): 40,
        ("P001", "LOC_C"): 35,
        ("P002", "LOC_A"): 15,
        ("P002", "LOC_B"): 14,
        ("P002", "LOC_C"): 16,
        ("P003", "LOC_A"): 10,
        ("P003", "LOC_B"): 12,
        ("P003", "LOC_C"): 9,
        ("P004", "LOC_A"): 1,    # slow mover: 1 unit / 50 SOH
        ("P004", "LOC_B"): 20,
        ("P004", "LOC_C"): 18,
        ("P005", "LOC_A"): 5,    # stock imbalance: high SOH vs peers
        ("P005", "LOC_B"): 5,
        ("P005", "LOC_C"): 5,
    }
    soh_map = {
        ("P004", "LOC_A"): 50,   # large SOH, few sales = slow mover
        ("P005", "LOC_A"): 200,  # very overstocked vs peers
        ("P005", "LOC_B"): 10,
        ("P005", "LOC_C"): 12,
    }

    for (pid, loc), base_units in store_units.items():
        soh = soh_map.get((pid, loc), base_units * 3)
        for period in periods:
            rows.append({
                "product_id": pid,
                "location_id": loc,
                "period": period,
                "units_sold": base_units,
                "stock_on_hand": soh,
                "revenue": base_units * 10.0,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def calendar() -> pd.DataFrame:
    return pd.DataFrame([
        {"range_tag": "seasonal", "season": "SS25", "active_from": pd.Timestamp("2025-03-01"), "active_to": pd.Timestamp("2025-08-31")},
        {"range_tag": "continuity", "season": None, "active_from": None, "active_to": None},
    ])

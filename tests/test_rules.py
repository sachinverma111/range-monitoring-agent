"""Unit tests for each analysis rule."""

import pandas as pd
import pytest

from range_monitor.rules import (
    category_divergence,
    rank_mismatch,
    season_mismatch,
    slow_mover,
    stock_imbalance,
)


class TestRankMismatch:
    def test_flags_underperforming_location(self, products, online_sales, store_sales, config):
        """P001 is high-demand online but very low at LOC_A → should produce a RANGE_GAP insight."""
        insights = rank_mismatch(products, online_sales, store_sales, config)
        assert len(insights) > 0
        types = {i.insight_type for i in insights}
        assert types == {"RANGE_GAP"}

    def test_range_gap_at_expected_location(self, products, online_sales, store_sales, config):
        """The RANGE_GAP for P001 should specifically flag LOC_A."""
        insights = rank_mismatch(products, online_sales, store_sales, config)
        p001_loca = [i for i in insights if i.product_id == "P001" and i.location_id == "LOC_A"]
        assert len(p001_loca) >= 1

    def test_supporting_data_populated(self, products, online_sales, store_sales, config):
        insights = rank_mismatch(products, online_sales, store_sales, config)
        for ins in insights:
            assert "online_pct_rank" in ins.supporting_data
            assert "store_pct_rank" in ins.supporting_data
            assert "rank_delta" in ins.supporting_data
            assert ins.supporting_data["rank_delta"] >= config.rank_mismatch_threshold

    def test_no_insights_when_threshold_very_high(self, products, online_sales, store_sales, config):
        """Setting threshold to 100 should produce zero insights."""
        config.rank_mismatch_threshold = 100.0
        insights = rank_mismatch(products, online_sales, store_sales, config)
        assert len(insights) == 0

    def test_all_insights_when_threshold_zero(self, products, online_sales, store_sales, config):
        """Setting threshold to 0 should flag every product×location combo with any delta."""
        config.rank_mismatch_threshold = 0.0
        insights = rank_mismatch(products, online_sales, store_sales, config)
        assert len(insights) > 0


class TestSlowMover:
    def test_flags_low_sell_through(self, products, online_sales, store_sales, config):
        """P004 at LOC_A has 1 unit sold against 50 SOH → slow mover."""
        insights = slow_mover(products, online_sales, store_sales, config)
        types = {i.insight_type for i in insights}
        assert types == {"SLOW_MOVER"}

    def test_p004_loca_is_flagged(self, products, online_sales, store_sales, config):
        insights = slow_mover(products, online_sales, store_sales, config)
        flagged_ids = [(i.product_id, i.location_id) for i in insights]
        assert ("P004", "LOC_A") in flagged_ids

    def test_supporting_data_has_capital_at_risk(self, products, online_sales, store_sales, config):
        insights = slow_mover(products, online_sales, store_sales, config)
        for ins in insights:
            assert "capital_at_risk_gbp" in ins.supporting_data
            assert "sell_through_pct" in ins.supporting_data

    def test_no_insights_without_soh_data(self, products, online_sales, store_sales, config):
        """If stock_on_hand is all null, slow_mover should return empty."""
        store_no_soh = store_sales.copy()
        store_no_soh["stock_on_hand"] = None
        insights = slow_mover(products, online_sales, store_no_soh, config)
        assert insights == []


class TestSeasonMismatch:
    def test_flags_seasonal_product_selling_out_of_season(self, products, online_sales, calendar, config):
        """P003 (SS25 seasonal) has sales in Oct–Dec which is outside SS25 window."""
        insights = season_mismatch(products, online_sales, calendar, config)
        types = {i.insight_type for i in insights}
        assert types == {"SEASON_MISMATCH"}

    def test_p003_is_flagged(self, products, online_sales, calendar, config):
        insights = season_mismatch(products, online_sales, calendar, config)
        flagged_ids = [i.product_id for i in insights]
        assert "P003" in flagged_ids

    def test_no_insights_when_calendar_is_none(self, products, online_sales, config):
        insights = season_mismatch(products, online_sales, None, config)
        assert insights == []

    def test_supporting_data_has_season_info(self, products, online_sales, calendar, config):
        insights = season_mismatch(products, online_sales, calendar, config)
        for ins in insights:
            assert "season" in ins.supporting_data
            assert "out_of_season_selling_weeks" in ins.supporting_data


class TestCategoryDivergence:
    def test_returns_category_insights(self, products, online_sales, store_sales, config):
        insights = category_divergence(products, online_sales, store_sales, config)
        for ins in insights:
            assert ins.insight_type == "CATEGORY_DIVERGENCE"
            assert ins.product_id == ""  # category-level, no specific product

    def test_supporting_data_structure(self, products, online_sales, store_sales, config):
        insights = category_divergence(products, online_sales, store_sales, config)
        for ins in insights:
            assert "online_category_pct_rank" in ins.supporting_data
            assert "pct_stores_underperforming" in ins.supporting_data
            assert "underperforming_locations" in ins.supporting_data


class TestStockImbalance:
    def test_flags_overstocked_location(self, products, online_sales, store_sales, config):
        """P005 at LOC_A has 200 SOH vs 10 at peers → stock imbalance."""
        insights = stock_imbalance(products, online_sales, store_sales, config)
        types = {i.insight_type for i in insights}
        assert types == {"STOCK_IMBALANCE"}

    def test_p005_loca_is_flagged(self, products, online_sales, store_sales, config):
        insights = stock_imbalance(products, online_sales, store_sales, config)
        flagged = [(i.product_id, i.location_id) for i in insights]
        assert ("P005", "LOC_A") in flagged

    def test_no_insights_without_soh(self, products, online_sales, store_sales, config):
        store_no_soh = store_sales.copy()
        store_no_soh["stock_on_hand"] = None
        insights = stock_imbalance(products, online_sales, store_no_soh, config)
        assert insights == []

    def test_supporting_data_has_excess_value(self, products, online_sales, store_sales, config):
        insights = stock_imbalance(products, online_sales, store_sales, config)
        for ins in insights:
            assert "excess_units" in ins.supporting_data
            assert "woc_multiple" in ins.supporting_data
            assert ins.supporting_data["woc_multiple"] >= config.stock_imbalance_multiple

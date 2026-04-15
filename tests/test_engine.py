"""Integration tests for the analysis engine."""

import pytest

from range_monitor.delivery import ACTION_SECTIONS, build_narratives, render_console_summary, render_markdown_report
from range_monitor.engine import run_analysis, score_and_rank
from range_monitor.models import Insight


class TestRunAnalysis:
    def test_returns_insights(self, products, online_sales, store_sales, calendar, config):
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        assert len(insights) > 0

    def test_respects_top_insights_count(self, products, online_sales, store_sales, calendar, config):
        config.top_insights_count = 3
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        assert len(insights) <= 3

    def test_insights_sorted_descending_by_score(self, products, online_sales, store_sales, calendar, config):
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        scores = [i.score for i in insights]
        assert scores == sorted(scores, reverse=True)

    def test_all_enabled_rule_types_present(self, products, online_sales, store_sales, calendar, config):
        """Ensure at least RANGE_GAP, SLOW_MOVER, and SEASON_MISMATCH are triggered by fixture data."""
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        types_found = {i.insight_type for i in insights}
        assert "RANGE_GAP" in types_found
        assert "SLOW_MOVER" in types_found
        assert "SEASON_MISMATCH" in types_found

    def test_unknown_rule_gracefully_skipped(self, products, online_sales, store_sales, calendar, config):
        config.enabled_rules = ["rank_mismatch", "nonexistent_rule"]
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        # Should still return RANGE_GAP insights from rank_mismatch
        assert len(insights) > 0

    def test_all_insights_have_positive_score(self, products, online_sales, store_sales, calendar, config):
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        assert all(i.score >= 0 for i in insights)


class TestScoreAndRank:
    def test_sorts_by_score(self):
        i1 = Insight("RANGE_GAP", "P1", "Prod A", "Footwear", "LOC_A", 0.0, "", "", {"rank_delta": 50, "online_units": 100, "store_units": 10, "price": 80})
        i2 = Insight("RANGE_GAP", "P2", "Prod B", "Footwear", "LOC_B", 0.0, "", "", {"rank_delta": 10, "online_units": 20, "store_units": 5, "price": 80})
        ranked = score_and_rank([i1, i2])
        assert ranked[0].product_id == "P1"  # higher delta → higher score

    def test_empty_list_returns_empty(self):
        assert score_and_rank([]) == []


class TestDelivery:
    def test_narratives_populated(self, products, online_sales, store_sales, calendar, config):
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        insights = build_narratives(insights)
        for ins in insights:
            assert ins.narrative, f"Empty narrative for {ins.insight_type} — {ins.product_id}"

    def test_markdown_report_contains_key_sections(self, products, online_sales, store_sales, calendar, config):
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        insights = build_narratives(insights)
        report = render_markdown_report(insights, config)
        assert "## This Week at a Glance" in report
        assert "## Analysis Parameters" in report
        # At least one action section should be present
        assert any(s["title"] in report for s in ACTION_SECTIONS)

    def test_console_summary_renders(self, products, online_sales, store_sales, calendar, config):
        insights = run_analysis(products, online_sales, store_sales, calendar, config)
        insights = build_narratives(insights)
        summary = render_console_summary(insights, top_n=5)
        assert len(summary) > 0

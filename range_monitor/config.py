from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class AnalysisConfig:
    # Rule 1: Online/In-Store Rank Mismatch
    rank_mismatch_threshold: float = 30.0  # percentile points delta to trigger RANGE_GAP

    # Rule 2: Slow Mover
    slow_mover_sell_through: float = 0.10  # sell-through rate below which a product is flagged
    slow_mover_window_weeks: int = 4  # rolling window for sell-through calculation

    # Rule 3: Seasonal Misclassification
    seasonal_consistency_weeks: int = 6  # out-of-season selling weeks to trigger SEASON_MISMATCH

    # Rule 4 & 5: General
    category_underperformance_pct: float = 0.30  # fraction of stores needed to flag CATEGORY_DIVERGENCE
    stock_imbalance_multiple: float = 2.0  # weeks-of-cover multiple vs median to trigger STOCK_IMBALANCE

    # Noise filters & output
    min_units_threshold: int = 5  # minimum online units to include a product in analysis
    top_insights_count: int = 20  # max insights returned per run

    enabled_rules: list[str] = field(default_factory=lambda: [
        "rank_mismatch",
        "slow_mover",
        "season_mismatch",
        "category_divergence",
        "stock_imbalance",
    ])


def load_config(path: str | Path = "configs/default.yaml") -> AnalysisConfig:
    """Load config from YAML, falling back to defaults for any missing keys."""
    config_path = Path(path)
    if not config_path.exists():
        return AnalysisConfig()
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
    # Filter to only known fields to avoid dataclass errors on unknown keys
    valid_fields = AnalysisConfig.__dataclass_fields__.keys()
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return AnalysisConfig(**filtered)

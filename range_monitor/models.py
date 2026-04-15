from dataclasses import dataclass, field
from typing import Literal

InsightType = Literal[
    "RANGE_GAP",
    "SLOW_MOVER",
    "SEASON_MISMATCH",
    "CATEGORY_DIVERGENCE",
    "STOCK_IMBALANCE",
]


@dataclass
class Insight:
    """A single actionable insight produced by the analysis engine."""

    insight_type: InsightType
    product_id: str
    product_name: str
    category: str
    location_id: str | None  # None for category-level insights (CATEGORY_DIVERGENCE)
    score: float
    narrative: str
    recommended_action: str
    supporting_data: dict = field(default_factory=dict)

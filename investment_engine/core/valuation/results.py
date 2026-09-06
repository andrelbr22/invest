"""Transport models for scenario-based valuation calculations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ValuationStatus = Literal["valid", "insufficient_data", "invalid_input", "not_applicable"]


class ValuationScenario(BaseModel):
    value: float
    upside_pct: float | None = None
    assumptions: dict = Field(default_factory=dict)


class ValuationQuality(BaseModel):
    score: float = 0.0
    coverage_pct: float = 0.0
    sample_size: int = 0
    metric_sample_sizes: dict[str, int] = Field(default_factory=dict)
    metrics_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ScenarioValuationResult(BaseModel):
    family_id: str
    method: str
    label: str
    status: ValuationStatus
    asset_type: str
    asset_class: str = "default"
    market_price: float | None = None
    scenarios: dict[str, ValuationScenario] = Field(default_factory=dict)
    quality: ValuationQuality = Field(default_factory=ValuationQuality)
    reason: str | None = None
    metadata: dict = Field(default_factory=dict)


def upside_pct(value: float, market_price: float | None) -> float | None:
    if market_price is None or market_price <= 0:
        return None
    return (value / market_price - 1.0) * 100.0

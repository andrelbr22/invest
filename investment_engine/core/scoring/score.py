from __future__ import annotations
from pydantic import BaseModel
from ..models.strategy import StrategyWeights


class ScoreBreakdown(BaseModel):
    quality: float | None = None
    value: float | None = None
    growth: float | None = None
    technical: float | None = None
    risk: float | None = None
    liquidity: float | None = None
    total: float | None = None
    coverage_pct: float = 0.0


def weighted_score(parts: dict[str, float | None], weights: StrategyWeights) -> ScoreBreakdown:
    w = weights.normalized().model_dump()
    valid = {k: v for k, v in parts.items() if k in w and v is not None}
    if not valid:
        return ScoreBreakdown(**parts, total=None, coverage_pct=0.0)
    used_weight = sum(w[k] for k in valid)
    total = sum(valid[k] * w[k] for k in valid) / used_weight
    coverage = used_weight * 100.0
    return ScoreBreakdown(**parts, total=round(total, 2), coverage_pct=round(coverage, 2))

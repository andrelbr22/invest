from pydantic import BaseModel


class ValuationResult(BaseModel):
    method: str
    value: float | None
    upside_pct: float | None = None
    valid: bool = True
    reason: str | None = None
    version: str = "1.0"


class PivotLevels(BaseModel):
    pp: float
    r1: float
    s1: float
    r2: float
    s2: float
    r3: float
    s3: float

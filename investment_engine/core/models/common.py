from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class DataStatus(str, Enum):
    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"


class AssetType(str, Enum):
    STOCK = "stock"
    FII = "fii"
    ETF = "etf"
    BDR = "bdr"
    FUTURE = "future"
    OTHER = "other"


class Signal(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    NO_DATA = "no_data"


class Trend(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    NO_DATA = "no_data"


class SourcedValue(BaseModel, Generic[T]):
    value: T | None = None
    source: str | None = None
    reference_date: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: DataStatus = DataStatus.VALID

    @classmethod
    def missing(cls, source: str | None = None) -> "SourcedValue":
        return cls(value=None, source=source, status=DataStatus.MISSING)

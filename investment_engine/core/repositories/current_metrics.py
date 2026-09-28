from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from typing import Any

from sqlalchemy.orm import Session

from ...infrastructure.db.models import (
    AssetCurrentMetricsORM,
    FundamentalSnapshotORM,
    PriceBarORM,
    ScoreSnapshotORM,
    TechnicalSnapshotORM,
    utcnow,
)


SCHEMA_VERSION = "1"

FUNDAMENTAL_FIELDS = (
    "price", "pe", "pbv", "dividend_yield_pct", "ev_ebitda",
    "ebit_margin_pct", "net_margin_pct", "current_ratio", "roe_pct", "roic_pct",
    "gross_debt_to_equity", "net_debt_to_ebitda", "revenue_cagr_5y_pct",
    "earnings_cagr_5y_pct", "ffo_yield_pct", "cap_rate_pct", "vacancy_pct",
    "financial_vacancy_pct", "ltv_pct", "wale_years", "daily_liquidity",
)
TECHNICAL_FIELDS = (
    "score_tv", "signal_tv", "market_cap", "daily_liquidity", "sma20", "sma50",
    "sma200", "sma20_1w", "sma50_1w", "sma20_1m", "sma50_1m", "high", "low",
    "close", "rsi14", "bb_lower", "bb_upper", "bb_middle", "macd", "atr14",
    "volatility_annual_pct", "max_drawdown_1y_pct", "return_1m_pct", "return_3m_pct",
    "return_12m_pct",
)
SCORE_FIELDS = (
    "quality_score", "value_score", "growth_score", "technical_score", "risk_score",
    "liquidity_score", "alb_score", "coverage_pct", "data_quality_score",
)


def _json_safe(value: Any):
    if isinstance(value, (datetime, date)):
        current = value
        if isinstance(current, datetime) and current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _payload(row, fields: tuple[str, ...], extra: dict | None = None) -> dict:
    result = {field: _json_safe(getattr(row, field, None)) for field in fields}
    if extra:
        result.update(_json_safe(extra))
    return result


def _hash(payload: dict) -> str:
    encoded = json.dumps(
        _json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _instant(value: datetime | None) -> str:
    if value is None:
        return ""
    current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def _source_order(as_of, observed_at, source_id) -> tuple[str, str, str]:
    return (_instant(as_of), _instant(observed_at), str(source_id or ""))


class AssetCurrentMetricsRepository:
    """Idempotent dual-write target for the latest materialized asset values."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, asset_id) -> AssetCurrentMetricsORM | None:
        return self.session.get(AssetCurrentMetricsORM, asset_id)

    def ensure(self, asset_id) -> tuple[AssetCurrentMetricsORM, bool]:
        row = self.get(asset_id)
        if row is not None:
            return row, False
        row = AssetCurrentMetricsORM(asset_id=asset_id, schema_version=SCHEMA_VERSION)
        self.session.add(row)
        self.session.flush()
        return row, True

    @staticmethod
    def _current_ref(row: AssetCurrentMetricsORM, component: str) -> dict:
        return dict((row.source_refs_json or {}).get(component) or {})

    @staticmethod
    def _should_apply(
        row: AssetCurrentMetricsORM,
        component: str,
        *,
        as_of: datetime | None,
        observed_at: datetime | None,
        source_id,
        content_hash: str,
    ) -> bool:
        existing = AssetCurrentMetricsRepository._current_ref(row, component)
        if not existing:
            return True
        incoming = _source_order(as_of, observed_at, source_id)
        current = (
            str(existing.get("as_of") or ""),
            str(existing.get("observed_at") or ""),
            str(existing.get("id") or ""),
        )
        return incoming > current or (incoming == current and existing.get("content_hash") != content_hash)

    @staticmethod
    def _set_ref(
        row: AssetCurrentMetricsORM,
        component: str,
        *,
        source_id,
        as_of: datetime | None,
        observed_at: datetime | None,
        source: str,
        content_hash: str,
        extra: dict | None = None,
    ) -> None:
        refs = dict(row.source_refs_json or {})
        refs[component] = {
            "id": str(source_id) if source_id is not None else None,
            "as_of": _instant(as_of) or None,
            "observed_at": _instant(observed_at) or None,
            "source": source,
            "content_hash": content_hash,
            **_json_safe(extra or {}),
        }
        row.source_refs_json = refs

    @staticmethod
    def _touch(row: AssetCurrentMetricsORM) -> None:
        row.schema_version = SCHEMA_VERSION
        row.updated_at = utcnow()

    @staticmethod
    def _refresh_fallbacks(row: AssetCurrentMetricsORM) -> None:
        refs = dict(row.source_refs_json or {})
        price_ref = dict(refs.get("price") or {})
        fundamental_price = (row.fundamental_json or {}).get("price")
        price_bar_value = price_ref.get("price")
        if price_bar_value is not None:
            row.price = Decimal(str(price_bar_value))
            price_source = "local_price_bar"
        elif fundamental_price is not None:
            row.price = Decimal(str(fundamental_price))
            price_source = "fundamental_snapshot"
        else:
            row.price = None
            price_source = "missing"

        row.daily_liquidity = (
            row.technical_daily_liquidity
            if row.technical_daily_liquidity is not None
            else row.fundamental_daily_liquidity
        )
        row.fallback_json = {
            "price": price_source,
            "daily_liquidity": (
                "technical_snapshot" if row.technical_daily_liquidity is not None
                else "fundamental_snapshot" if row.fundamental_daily_liquidity is not None
                else "missing"
            ),
            "technical_features": (
                "local_price_bars" if row.technical_features_json else "missing"
            ),
            "historical_tables_preserved": True,
        }

    def sync_fundamental(self, snapshot: FundamentalSnapshotORM) -> bool:
        row, _ = self.ensure(snapshot.asset_id)
        payload = _payload(snapshot, FUNDAMENTAL_FIELDS, {
            "status": snapshot.status,
            "quality_score": snapshot.quality_score,
            "source": snapshot.source,
            "raw_payload": snapshot.raw_payload or {},
        })
        content_hash = _hash(payload)
        if not self._should_apply(
            row, "fundamental", as_of=snapshot.reference_date,
            observed_at=snapshot.retrieved_at, source_id=snapshot.id, content_hash=content_hash,
        ):
            return False
        row.fundamental_snapshot_id = snapshot.id
        row.fundamental_as_of = snapshot.reference_date
        row.fundamental_retrieved_at = snapshot.retrieved_at
        row.fundamental_json = payload
        for field in FUNDAMENTAL_FIELDS:
            if field == "price":
                continue
            if field == "daily_liquidity":
                row.fundamental_daily_liquidity = snapshot.daily_liquidity
            else:
                setattr(row, field, getattr(snapshot, field))
        self._set_ref(
            row, "fundamental", source_id=snapshot.id, as_of=snapshot.reference_date,
            observed_at=snapshot.retrieved_at, source=snapshot.source, content_hash=content_hash,
        )
        self._refresh_fallbacks(row)
        self._touch(row)
        return True

    def sync_technical(self, snapshot: TechnicalSnapshotORM) -> bool:
        if str(snapshot.timeframe or "").upper() != "1D":
            return False
        row, _ = self.ensure(snapshot.asset_id)
        payload = _payload(snapshot, TECHNICAL_FIELDS, {
            "timeframe": snapshot.timeframe,
            "status": snapshot.status,
            "quality_score": snapshot.quality_score,
            "source": snapshot.source,
            "raw_payload": snapshot.raw_payload or {},
        })
        content_hash = _hash(payload)
        if not self._should_apply(
            row, "technical", as_of=snapshot.as_of,
            observed_at=snapshot.retrieved_at, source_id=snapshot.id, content_hash=content_hash,
        ):
            return False
        row.technical_snapshot_id = snapshot.id
        row.technical_as_of = snapshot.as_of
        row.technical_retrieved_at = snapshot.retrieved_at
        row.technical_json = payload
        for field in TECHNICAL_FIELDS:
            if field in {"daily_liquidity", "high", "low", "close", "bb_lower", "bb_upper", "bb_middle"}:
                continue
            setattr(row, field, getattr(snapshot, field))
        row.technical_daily_liquidity = snapshot.daily_liquidity
        self._set_ref(
            row, "technical", source_id=snapshot.id, as_of=snapshot.as_of,
            observed_at=snapshot.retrieved_at, source=snapshot.source, content_hash=content_hash,
            extra={"timeframe": snapshot.timeframe},
        )
        self._refresh_fallbacks(row)
        self._touch(row)
        return True

    def sync_score(self, snapshot: ScoreSnapshotORM) -> bool:
        row, _ = self.ensure(snapshot.asset_id)
        payload = _payload(snapshot, SCORE_FIELDS, {
            "model_version": snapshot.model_version,
            "details": snapshot.details_json or {},
        })
        content_hash = _hash(payload)
        if not self._should_apply(
            row, "score", as_of=snapshot.as_of,
            observed_at=snapshot.calculated_at, source_id=snapshot.id, content_hash=content_hash,
        ):
            return False
        row.score_snapshot_id = snapshot.id
        row.score_as_of = snapshot.as_of
        row.score_calculated_at = snapshot.calculated_at
        row.score_json = payload
        for field in SCORE_FIELDS:
            setattr(row, field, getattr(snapshot, field))
        self._set_ref(
            row, "score", source_id=snapshot.id, as_of=snapshot.as_of,
            observed_at=snapshot.calculated_at, source=snapshot.model_version,
            content_hash=content_hash,
        )
        self._touch(row)
        return True

    def sync_price(self, bar: PriceBarORM) -> bool:
        if str(bar.timeframe or "").upper() != "1D":
            return False
        row, _ = self.ensure(bar.asset_id)
        price = bar.adjusted_close if bar.adjusted_close is not None else bar.close
        payload = _payload(bar, ("open", "high", "low", "close", "adjusted_close", "volume"), {
            "timeframe": bar.timeframe, "status": bar.status, "source": bar.source,
        })
        content_hash = _hash(payload)
        if not self._should_apply(
            row, "price", as_of=bar.timestamp,
            observed_at=bar.retrieved_at, source_id=bar.id, content_hash=content_hash,
        ):
            return False
        row.price_bar_id = bar.id
        row.price_as_of = bar.timestamp
        row.price_retrieved_at = bar.retrieved_at
        self._set_ref(
            row, "price", source_id=bar.id, as_of=bar.timestamp,
            observed_at=bar.retrieved_at, source=bar.source, content_hash=content_hash,
            extra={"timeframe": bar.timeframe, "price": price},
        )
        self._refresh_fallbacks(row)
        self._touch(row)
        return True

    def sync_features(
        self,
        asset_id,
        features: dict,
        *,
        latest_bar: PriceBarORM | None,
        history_rows: int,
        algorithm: str,
    ) -> bool:
        row, _ = self.ensure(asset_id)
        payload = _json_safe(features or {})
        content_hash = _hash(payload)
        as_of = latest_bar.timestamp if latest_bar is not None else None
        observed_at = latest_bar.retrieved_at if latest_bar is not None else None
        source_id = latest_bar.id if latest_bar is not None else None
        if not self._should_apply(
            row, "features", as_of=as_of, observed_at=observed_at,
            source_id=source_id, content_hash=content_hash,
        ):
            return False
        row.technical_features_json = payload
        row.calculated_at = utcnow()
        self._set_ref(
            row, "features", source_id=source_id, as_of=as_of,
            observed_at=observed_at, source="local_price_bars", content_hash=content_hash,
            extra={"history_rows": int(history_rows), "algorithm": algorithm},
        )
        self._refresh_fallbacks(row)
        self._touch(row)
        return True

    def set_parity(self, asset_id, components: dict[str, str], *, checked_at=None) -> bool:
        row, _ = self.ensure(asset_id)
        clean = {str(key): str(value) for key, value in components.items()}
        states = set(clean.values())
        state = "stale" if "stale" in states else "exact" if "exact" in states else "no_sources"
        existing = dict(row.parity_json or {})
        if existing.get("state") == state and existing.get("components") == clean:
            return False
        payload = {
            "state": state,
            "components": clean,
            "checked_at": _instant(checked_at or utcnow()),
            "historical_tables_preserved": True,
        }
        row.parity_json = payload
        self._touch(row)
        return True

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .repositories.assets import AssetRepository
from .repositories.current_metrics import AssetCurrentMetricsRepository
from .screening.advanced import technical_features
from ..infrastructure.db.models import AssetORM, utcnow


FEATURE_ALGORITHM = "local-price-bars-v1"
_CURRENT_ROW_NOT_PRELOADED = object()


def _bar_timestamp(bar) -> str | None:
    value = getattr(bar, "timestamp", None)
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def precompute_technical_features(bars) -> dict:
    """Calculate every screener combination once from persisted local bars."""
    rows = list(bars or [])
    trend20 = technical_features(rows, trend_period=20, pivot_timeframe="daily")
    trend21 = technical_features(rows, trend_period=21, pivot_timeframe="daily")
    weekly = technical_features(rows, trend_period=21, pivot_timeframe="weekly")
    monthly = technical_features(rows, trend_period=21, pivot_timeframe="monthly")

    trend_fields = (
        "sma_daily", "sma_weekly", "sma_monthly",
        "trend_daily", "trend_weekly", "trend_monthly",
    )
    pivot_fields = ("pivot_reference", "pp", "r1", "s1", "r2", "s2", "r3", "s3")
    return {
        "schema_version": "1",
        "algorithm": FEATURE_ALGORITHM,
        "bar_count": len(rows),
        "latest_bar_at": _bar_timestamp(rows[-1]) if rows else None,
        "current_price": trend21.get("current_price"),
        "trend_periods": {
            "20": {field: trend20.get(field) for field in trend_fields},
            "21": {field: trend21.get(field) for field in trend_fields},
        },
        "rsi14": trend21.get("rsi14"),
        "volume": {
            key: trend21.get(key)
            for key in (
                "volume_daily", "volume_daily_ma9", "volume_daily_ratio",
                "volume_monthly", "volume_monthly_ma9", "volume_monthly_ratio",
            )
        },
        "pivots": {
            "daily": {field: trend21.get(field) for field in pivot_fields},
            "weekly": {field: weekly.get(field) for field in pivot_fields},
            "monthly": {field: monthly.get(field) for field in pivot_fields},
        },
    }


class AssetCurrentMetricsService:
    """Backfill/current-value service; all source history remains authoritative."""

    def __init__(self, session: Session):
        self.session = session
        self.assets = AssetRepository(session)
        self.current = AssetCurrentMetricsRepository(session)

    @staticmethod
    def _component_state(source, current_id) -> str:
        if source is None:
            return "missing"
        return "exact" if str(source.id) == str(current_id or "") else "stale"

    @staticmethod
    def _instant(value: datetime | None) -> str:
        if value is None:
            return ""
        current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc).isoformat()

    @classmethod
    def _source_ref_matches(
        cls,
        source_ref: dict,
        source,
        *,
        as_of_field: str,
        observed_at_field: str,
    ) -> bool:
        if source is None:
            return False
        return (
            str(source_ref.get("id") or "") == str(source.id or "")
            and str(source_ref.get("as_of") or "")
            == cls._instant(getattr(source, as_of_field, None))
            and str(source_ref.get("observed_at") or "")
            == cls._instant(getattr(source, observed_at_field, None))
        )

    @classmethod
    def _component_is_current(
        cls,
        row,
        component: str,
        source,
        *,
        current_id_field: str,
        as_of_field: str,
        observed_at_field: str,
    ) -> bool:
        if source is None or str(getattr(row, current_id_field, None) or "") != str(source.id or ""):
            return False
        return cls._source_ref_matches(
            dict((row.source_refs_json or {}).get(component) or {}),
            source,
            as_of_field=as_of_field,
            observed_at_field=observed_at_field,
        )

    @classmethod
    def _features_are_current(cls, row, latest_bar) -> bool:
        if not isinstance(row.technical_features_json, dict) or not row.technical_features_json:
            return False
        source_ref = dict((row.source_refs_json or {}).get("features") or {})
        if source_ref.get("algorithm") != FEATURE_ALGORITHM:
            return False
        if latest_bar is None:
            return not any(
                str(source_ref.get(field) or "")
                for field in ("id", "as_of", "observed_at")
            )
        return cls._source_ref_matches(
            source_ref,
            latest_bar,
            as_of_field="timestamp",
            observed_at_field="retrieved_at",
        )

    def sync_asset(
        self,
        asset: AssetORM,
        *,
        latest_sources: dict | None = None,
        current_row=_CURRENT_ROW_NOT_PRELOADED,
    ) -> dict:
        if current_row is _CURRENT_ROW_NOT_PRELOADED:
            row, created = self.current.ensure(asset.id)
        else:
            row, created = self.current.ensure(asset.id, known_row=current_row)
        if latest_sources is None:
            fundamental = self.assets.latest_fundamentals(asset.id)
            technical = self.assets.latest_technical(asset.id, timeframe="1D")
            score = self.assets.latest_scores(asset.id)
            latest_bar = self.assets.latest_price_bar(asset.id, timeframe="1D")
        else:
            fundamental = latest_sources.get("fundamental")
            technical = latest_sources.get("technical")
            score = latest_sources.get("score")
            latest_bar = latest_sources.get("price")

        changed = 0
        if fundamental is not None and not self._component_is_current(
            row, "fundamental", fundamental,
            current_id_field="fundamental_snapshot_id",
            as_of_field="reference_date", observed_at_field="retrieved_at",
        ):
            changed += int(self.current.sync_fundamental(fundamental, row=row))
        if technical is not None and not self._component_is_current(
            row, "technical", technical,
            current_id_field="technical_snapshot_id",
            as_of_field="as_of", observed_at_field="retrieved_at",
        ):
            changed += int(self.current.sync_technical(technical, row=row))
        if score is not None and not self._component_is_current(
            row, "score", score,
            current_id_field="score_snapshot_id",
            as_of_field="as_of", observed_at_field="calculated_at",
        ):
            changed += int(self.current.sync_score(score, row=row))
        if latest_bar is not None and not self._component_is_current(
            row, "price", latest_bar,
            current_id_field="price_bar_id",
            as_of_field="timestamp", observed_at_field="retrieved_at",
        ):
            changed += int(self.current.sync_price(latest_bar, row=row))
        if not self._features_are_current(row, latest_bar):
            history = self.assets.price_history(asset.id, timeframe="1D", limit=600)
            features = precompute_technical_features(history)
            changed += int(self.current.sync_features(
                asset.id, features, latest_bar=latest_bar,
                history_rows=len(history), algorithm=FEATURE_ALGORITHM, row=row,
            ))

        refs = dict(row.source_refs_json or {})
        components = {
            "fundamental": self._component_state(
                fundamental, (refs.get("fundamental") or {}).get("id"),
            ),
            "technical": self._component_state(
                technical, (refs.get("technical") or {}).get("id"),
            ),
            "score": self._component_state(score, (refs.get("score") or {}).get("id")),
            "price": self._component_state(latest_bar, (refs.get("price") or {}).get("id")),
            "features": (
                "exact" if latest_bar is not None
                and str((refs.get("features") or {}).get("id") or "") == str(latest_bar.id)
                else "missing" if latest_bar is None else "stale"
            ),
        }
        changed += int(self.current.set_parity(
            asset.id, components, checked_at=utcnow(), row=row,
        ))
        self.session.flush()
        return {
            "asset_id": str(asset.id),
            "ticker": asset.ticker,
            "created": created,
            "changed_components": changed,
            "parity": dict(row.parity_json or {}),
        }

    def sync_batch(self, *, after_ticker: str = "", limit: int = 250) -> dict:
        clean_cursor = str(after_ticker or "").strip().upper()
        batch_limit = max(1, min(1000, int(limit)))
        statement = (
            select(AssetORM)
            .where(AssetORM.is_active.is_(True))
            .order_by(AssetORM.ticker, AssetORM.id)
            .limit(batch_limit)
        )
        if clean_cursor:
            statement = statement.where(AssetORM.ticker > clean_cursor)
        assets = list(self.session.scalars(statement))
        latest_sources = self.assets.latest_current_sources_batch(
            [asset.id for asset in assets], timeframe="1D",
        )
        current_rows = self.current.get_many([asset.id for asset in assets])
        created = updated = unchanged = 0
        errors: list[dict] = []
        for asset in assets:
            try:
                with self.session.begin_nested():
                    result = self.sync_asset(
                        asset,
                        latest_sources=latest_sources.get(asset.id, {}),
                        current_row=current_rows.get(asset.id),
                    )
                created += int(result["created"])
                if result["changed_components"]:
                    updated += int(not result["created"])
                else:
                    unchanged += 1
            except Exception as exc:
                errors.append({"ticker": asset.ticker, "error": type(exc).__name__})

        next_cursor = assets[-1].ticker if assets else clean_cursor
        remaining = int(self.session.scalar(
            select(func.count()).select_from(AssetORM).where(
                AssetORM.is_active.is_(True),
                AssetORM.ticker > next_cursor,
            )
        ) or 0)
        return {
            "requested": len(assets),
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "errors": errors,
            "after_ticker": clean_cursor,
            "next_cursor": next_cursor if remaining else "",
            "remaining": remaining,
            "cycle_completed": remaining == 0,
            "algorithm": FEATURE_ALGORITHM,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }

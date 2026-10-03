from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .repositories.assets import AssetRepository
from .repositories.backtests import BacktestRepository, run_summary
from .repositories.current_metrics import AssetCurrentMetricsRepository
from .screening.advanced import (
    MATERIALIZED_VALUATION_FIELDS,
    VALUATION_FAMILIES,
    _enrich_valuation_rows,
    row_from_orm,
    technical_features,
)
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
        self.backtests = BacktestRepository(session)

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

    @staticmethod
    def _valuation_payload(fundamentals: dict) -> dict:
        payload = {
            key: value
            for key, value in dict(fundamentals or {}).items()
            if key in MATERIALIZED_VALUATION_FIELDS
            or key in {f"{family_id}_status" for family_id in VALUATION_FAMILIES}
        }
        payload["_meta"] = {
            "schema_version": "1",
            "assumptions": "default",
            "source": "worker-local-current-metrics",
        }
        return payload

    @staticmethod
    def _valuation_payload_is_covered(payload: dict | None) -> bool:
        """Accept valid values and explicit N/D, but reject metadata-only rows."""
        current = dict(payload or {})
        methods = current.get("valuation_methods")
        if isinstance(methods, dict) and methods:
            return True
        return any(
            key in current
            for key in MATERIALIZED_VALUATION_FIELDS
            if key != "valuation_methods"
        )

    def sync_navigation_metrics(
        self,
        assets: list[AssetORM],
        *,
        include_valuation: bool = True,
        include_backtests: bool = True,
    ) -> dict:
        """Build expensive default navigation projections outside requests.

        The worker is allowed to read the complete local peer/backtest history;
        web routes only consume the compact JSON produced here.  Failures are
        isolated by asset class and never erase the last known valid payload.
        """
        selected = list({asset.id: asset for asset in (assets or [])}.values())
        rows = self.current.get_many([asset.id for asset in selected])
        result = {
            "requested": len(selected),
            "valuations_updated": 0,
            "backtest_podiums_updated": 0,
            "errors": [],
        }
        if not selected:
            return result

        if include_valuation:
            selected_by_type: dict[str, list[AssetORM]] = {}
            for asset in selected:
                selected_by_type.setdefault(str(asset.asset_type), []).append(asset)
            for asset_type, targets in selected_by_type.items():
                try:
                    universe = list(self.assets.latest_universe(
                        asset_type=asset_type,
                        limit=5000,
                    ))
                    peer_entries = []
                    entries_by_id = {}
                    for asset, fundamental, technical, score in universe:
                        entry = (asset, row_from_orm(asset, fundamental, technical, score))
                        peer_entries.append(entry)
                        entries_by_id[asset.id] = entry
                    # Assets without a usable provider snapshot still receive
                    # an explicit N/D projection.  This marks the read model as
                    # covered and prevents an expensive historical fallback on
                    # every page view while keeping every value fail-closed.
                    entries = []
                    for target in targets:
                        entry = entries_by_id.get(target.id)
                        if entry is None:
                            entry = (target, row_from_orm(target, None, None, None))
                        entries.append(entry)
                    _enrich_valuation_rows(
                        entries,
                        peer_entries=peer_entries,
                        valuation_assumptions=None,
                    )
                    calculated_at = datetime.now(timezone.utc)
                    payload_by_id = {
                        asset.id: self._valuation_payload(row["fundamentals"])
                        for asset, row in entries
                    }
                    for target in targets:
                        payload = payload_by_id.get(target.id)
                        if not self._valuation_payload_is_covered(payload):
                            # Preserve last-known-good valuation when the
                            # current provider cohort is temporarily incomplete.
                            result["errors"].append({
                                "component": "valuation",
                                "ticker": target.ticker,
                                "error": "valuation_inputs_unavailable",
                            })
                            continue
                        current_row = rows.get(target.id)
                        if current_row is None:
                            current_row, _created = self.current.ensure(target.id)
                            rows[target.id] = current_row
                        changed = self.current.sync_valuation(
                            target.id,
                            payload,
                            calculated_at=calculated_at,
                            row=current_row,
                        )
                        result["valuations_updated"] += int(changed)
                except Exception as exc:
                    result["errors"].append({
                        "component": "valuation",
                        "asset_type": asset_type,
                        "error": type(exc).__name__,
                    })

        if include_backtests:
            try:
                tickers = [asset.ticker for asset in selected]
                grouped = self.backtests.leaderboard(
                    tickers=tickers,
                    per_asset=3,
                    limit=max(3, len(tickers) * 3),
                )
                calculated_at = datetime.now(timezone.utc)
                for asset in selected:
                    current_row = rows.get(asset.id)
                    if current_row is None:
                        current_row, _created = self.current.ensure(asset.id)
                        rows[asset.id] = current_row
                    leaders = [
                        run_summary(run, leader_asset)
                        for run, leader_asset in grouped.get(asset.ticker, [])
                    ]
                    if not leaders and list(current_row.backtest_leaders_json or []):
                        # A successfully materialized podium cannot disappear
                        # because of a transient read problem.  Preserve it and
                        # let the next worker pass retry from authoritative
                        # history.
                        result["errors"].append({
                            "component": "backtest_leaders",
                            "ticker": asset.ticker,
                            "error": "empty_result_preserved_last_known_good",
                        })
                        continue
                    changed = self.current.sync_backtest_leaders(
                        asset.id,
                        leaders,
                        calculated_at=calculated_at,
                        row=current_row,
                    )
                    result["backtest_podiums_updated"] += int(changed)
            except Exception as exc:
                result["errors"].append({
                    "component": "backtest_leaders",
                    "error": type(exc).__name__,
                })
        self.session.flush()
        return result

    def sync_navigation_tickers(
        self,
        tickers: list[str],
        *,
        include_valuation: bool = True,
        include_backtests: bool = True,
    ) -> dict:
        clean = sorted({
            str(ticker or "").strip().upper()
            for ticker in (tickers or [])
            if str(ticker or "").strip()
        })
        if not clean:
            return self.sync_navigation_metrics(
                [],
                include_valuation=include_valuation,
                include_backtests=include_backtests,
            )
        assets = list(self.session.scalars(
            select(AssetORM).where(
                AssetORM.ticker.in_(clean),
                AssetORM.is_active.is_(True),
            ).order_by(AssetORM.ticker)
        ))
        return self.sync_navigation_metrics(
            assets,
            include_valuation=include_valuation,
            include_backtests=include_backtests,
        )

    def sync_batch(
        self,
        *,
        after_ticker: str = "",
        limit: int = 250,
        materialize_navigation: bool = False,
    ) -> dict:
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
        navigation = (
            self.sync_navigation_metrics(assets)
            if materialize_navigation
            else {
                "requested": 0,
                "valuations_updated": 0,
                "backtest_podiums_updated": 0,
                "errors": [],
            }
        )
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
            "navigation": navigation,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }

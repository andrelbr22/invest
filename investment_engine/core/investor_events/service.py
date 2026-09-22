from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from ..jobs.schedules import REFRESH_SCHEDULES, refresh_status
from ..repositories.assets import AssetRepository
from ..repositories.analysis_settings import AnalysisSettingsRepository
from ..repositories.economic_series import SharedSnapshotRepository
from ..repositories.investor_events import InvestorEventsRepository, alb_observation_dict
from ..repositories.operations import OperationsRepository
from ..strategies.presets import STOCK_STRATEGIES
from ..screening.advanced import advanced_screen
from ...infrastructure.db.models import (
    AssetORM,
    EconomicSeriesORM,
    EconomicSeriesPointORM,
    FundamentalSnapshotORM,
    ScoreSnapshotORM,
    TechnicalSnapshotORM,
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _aware(value)
    return normalized.isoformat() if normalized else None


class DataQualityService:
    """Build one transparent coverage/freshness report without live HTTP calls."""

    COVERAGE_RULES = {
        "fundamentals": (FundamentalSnapshotORM, FundamentalSnapshotORM.reference_date, timedelta(days=8)),
        "technicals_daily": (TechnicalSnapshotORM, TechnicalSnapshotORM.as_of, timedelta(days=4)),
        "scores": (ScoreSnapshotORM, ScoreSnapshotORM.as_of, timedelta(days=8)),
    }

    def __init__(self, session: Session):
        self.session = session

    def _snapshot_sources(self, now: datetime) -> list[dict]:
        rows = []
        for key, spec in REFRESH_SCHEDULES.items():
            if key == "data_quality":
                continue
            state = refresh_status(self.session, key, now)
            snapshot = SharedSnapshotRepository(self.session).get(spec.snapshot_key)
            payload = dict(snapshot.payload_json or {}) if snapshot is not None else {}
            effective_status = state["status"]
            payload_status = str(payload.get("status") or "").strip().lower()
            if effective_status == "updated" and payload_status in {"partial", "stale", "unavailable", "failed"}:
                effective_status = payload_status
            count = None
            for candidate in ("item_count", "total", "requested", "received", "available_series"):
                if isinstance(payload.get(candidate), (int, float)):
                    count = int(payload[candidate])
                    break
            rows.append({
                "key": f"snapshot:{key}", "label": spec.label, "category": "shared_snapshot",
                "source": spec.source, "status": effective_status,
                "last_updated_at": _iso(state["last_updated_at"]),
                "next_update_at": _iso(state["next_update_at"]),
                "max_age_seconds": int(spec.stale_after.total_seconds()),
                "item_count": count, "coverage_pct": None,
                "last_error_code": state["last_error_code"] or payload.get("reason") or payload.get("error_code"),
                "last_error_at": _iso(state["last_error_at"]),
                "warnings": list(state.get("warnings") or []),
            })
        return rows

    def _asset_coverage(self, now: datetime) -> list[dict]:
        rows = []
        for asset_type in ("stock", "fii", "etf", "bdr", "future"):
            total = self.session.scalar(select(func.count(AssetORM.id)).where(
                AssetORM.asset_type == asset_type, AssetORM.is_active.is_(True),
            )) or 0
            for key, (model, timestamp, max_age) in self.COVERAGE_RULES.items():
                conditions = [
                    AssetORM.asset_type == asset_type, AssetORM.is_active.is_(True),
                    timestamp >= now - max_age,
                ]
                if model is TechnicalSnapshotORM:
                    conditions.append(TechnicalSnapshotORM.timeframe == "1D")
                covered = self.session.scalar(
                    select(func.count(distinct(AssetORM.id))).select_from(AssetORM).join(
                        model, model.asset_id == AssetORM.id,
                    ).where(*conditions)
                ) or 0
                coverage = round(covered * 100.0 / total, 2) if total else None
                status = "unavailable" if not total else "updated" if coverage >= 80 else "partial" if coverage >= 40 else "stale"
                rows.append({
                    "key": f"assets:{asset_type}:{key}",
                    "label": f"{key.replace('_', ' ').title()} • {asset_type.upper()}",
                    "category": "asset_coverage", "source": "Banco de dados consolidado",
                    "status": status, "last_updated_at": None, "next_update_at": None,
                    "max_age_seconds": int(max_age.total_seconds()), "item_count": int(covered),
                    "total_items": int(total), "coverage_pct": coverage,
                    "last_error_code": None, "last_error_at": None, "warnings": [],
                })
        return rows

    def _economic_series(self, now: datetime) -> list[dict]:
        rows = []
        for series in self.session.scalars(select(EconomicSeriesORM).where(EconomicSeriesORM.is_active.is_(True)).order_by(EconomicSeriesORM.code)):
            latest, count = self.session.execute(select(
                func.max(EconomicSeriesPointORM.observed_at), func.count(EconomicSeriesPointORM.id),
            ).where(EconomicSeriesPointORM.series_id == series.id)).one()
            latest = _aware(latest)
            age_days = (now - latest).total_seconds() / 86400 if latest else None
            expected_days = {"daily": 4, "weekly": 14, "monthly": 62, "annual": 400}.get(series.frequency, 62)
            status = "unavailable" if latest is None else "updated" if age_days <= expected_days else "stale"
            rows.append({
                "key": f"series:{series.code.lower()}", "label": series.name,
                "category": "economic_series", "source": series.source, "source_url": series.source_url,
                "status": status, "last_updated_at": _iso(latest), "next_update_at": None,
                "max_age_seconds": expected_days * 86400, "item_count": int(count),
                "coverage_pct": None, "last_error_code": None, "last_error_at": None,
                "warnings": [],
            })
        return rows

    def report(self, *, now: datetime | None = None, sync_incidents: bool = True) -> dict:
        current = _aware(now or datetime.now(timezone.utc))
        sources = self._snapshot_sources(current) + self._asset_coverage(current) + self._economic_series(current)
        alerts = []
        for row in sources:
            if row["status"] not in {"stale", "unavailable", "failed"}:
                continue
            severity = "critical" if row["status"] in {"unavailable", "failed"} else "warning"
            alerts.append({
                "code": f"data_quality:{row['key']}", "severity": severity,
                "title": f"Fonte de dados {row['status']}",
                "message": f"{row['label']} requer atualização ou verificação da fonte.",
                "details": {"source": row["source"], "status": row["status"], "coverage_pct": row.get("coverage_pct")},
            })
        if sync_incidents:
            OperationsRepository(self.session).sync_incidents(
                alerts, now=current, managed_prefixes={"data_quality:"},
            )
        status = "critical" if any(item["severity"] == "critical" for item in alerts) else "warning" if alerts else "ok"
        return {
            "status": status, "generated_at": current.isoformat(), "sources": sources,
            "summary": {
                "total": len(sources),
                "updated": sum(row["status"] == "updated" for row in sources),
                "partial": sum(row["status"] == "partial" for row in sources),
                "stale": sum(row["status"] == "stale" for row in sources),
                "unavailable_or_failed": sum(row["status"] in {"unavailable", "failed"} for row in sources),
            },
        }


class AlbUniverseMonitor:
    TARGET_MIN = 5
    TARGET_MAX = 20

    def __init__(self, session: Session):
        self.session = session

    def run(self, *, now: datetime | None = None) -> dict:
        current = _aware(now or datetime.now(timezone.utc))
        strategy = STOCK_STRATEGIES["alb"]
        setting = AnalysisSettingsRepository(self.session).get_preset("stock", "alb")
        owner_configuration = (
            dict(setting.owner_configuration_json or {})
            if setting is not None and setting.owner_enabled and setting.owner_configuration_json
            else None
        )
        preset_version = strategy.version
        recorded_filters: dict = strategy.filters.model_dump(mode="json")
        tickers: list[str]
        if owner_configuration and owner_configuration.get("ibov_membership", "any") == "any":
            # Owner alternatives use the full advanced schema. The monitor can
            # reflect every locally evaluable criterion, while deliberately
            # avoiding the UI's relaxed ALB fallback tiers.
            arguments = {
                key: owner_configuration.get(key)
                for key in (
                    "fundamental_filters", "score_filters", "valuation_flags", "valuation_assumptions",
                    "technical_filters", "trend_period", "pivot_timeframe", "include_technical_columns",
                    "allowed_tickers", "company_sizes", "ibov_membership",
                )
                if key in owner_configuration
            }
            result = advanced_screen(
                AssetRepository(self.session), asset_type="stock", limit=1000, **arguments,
            )
            tickers = [str(row.get("ticker") or "").strip().upper() for row in result.get("rows", [])]
            tickers = [ticker for ticker in tickers if ticker]
            preset_version = f"alb-owner-r{int(setting.revision)}"
            recorded_filters = owner_configuration
        else:
            # Factory R7 remains the safe fallback when no owner alternative is
            # active, or when it requires a live IBOV membership lookup that is
            # intentionally unavailable in this background monitor.
            rows = AssetRepository(self.session).screen_latest_stocks(strategy.filters, limit=1000)
            tickers = [row[0].ticker for row in rows]
        observation = InvestorEventsRepository(self.session).save_alb_observation(
            reference_date=current.date(), preset_version=preset_version,
            filters=recorded_filters, tickers=tickers,
            target_min=self.TARGET_MIN, target_max=self.TARGET_MAX,
        )
        alerts = []
        if observation.status == "outside_range":
            alerts.append({
                "code": "alb_result_count_out_of_range", "severity": "warning",
                "title": "Quantidade do filtro ALB fora da faixa",
                "message": (
                    f"O preset ALB estrito retornou {observation.asset_count} ativo(s); "
                    f"a faixa esperada é {self.TARGET_MIN} a {self.TARGET_MAX}. Os critérios não foram alterados."
                ),
                "details": {"count": observation.asset_count, "minimum": self.TARGET_MIN, "maximum": self.TARGET_MAX},
            })
        OperationsRepository(self.session).sync_incidents(
            alerts, now=current, managed_codes={"alb_result_count_out_of_range"},
        )
        return alb_observation_dict(observation)

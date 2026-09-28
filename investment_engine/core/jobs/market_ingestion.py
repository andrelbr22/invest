from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from ...data.ingestion.pipeline import MarketIngestionPipeline
from ...data.ingestion.prices import PriceIngestionService
from ...data.providers.b3_indices import B3IndexProvider
from ...infrastructure.db.session import get_session_factory
from ..current_metrics import AssetCurrentMetricsService
from ..repositories.assets import AssetRepository
from ..repositories.background_jobs import BackgroundJobRepository
from ..repositories.economic_series import SharedSnapshotRepository, utcnow
from ..services_v14 import calculate_asset_intelligence


def _report(payload: dict, session, *, current: int, total: int, message: str) -> None:
    job_id = payload.get("_background_job_id")
    if not job_id:
        return
    BackgroundJobRepository(session).report_progress(
        UUID(str(job_id)), current=current, total=total, message=message,
    )
    session.commit()


def refresh_intelligence_scores(session, asset_type: str) -> int:
    """Recalculate persisted score snapshots after a background market import."""
    repository = AssetRepository(session)
    processed = 0
    for asset in repository.list_assets(asset_type=asset_type, limit=5000):
        fundamental = repository.latest_fundamentals(asset.id)
        if fundamental is None:
            continue
        technical = (
            repository.latest_technical(asset.id, source="internal")
            or repository.latest_technical(asset.id)
        )
        result = calculate_asset_intelligence(asset, fundamental, technical)
        scores = {
            "quality_score": result["quality"].score,
            "value_score": result["value"].score,
            "growth_score": result["growth"].score if result["growth"] else None,
            "technical_score": result["technical"].score,
            "risk_score": result["risk"].score,
            "liquidity_score": result["liquidity"].score,
            "alb_score": result["alb_score"],
        }
        details = {
            "profile": {
                "key": result["profile"].key,
                "label": result["profile"].label,
                "notes": result["profile"].notes,
                "weights": result["profile"].alb_weights,
            },
            "quality": result["quality"].as_dict(),
            "value": result["value"].as_dict(),
            "growth": result["growth"].as_dict() if result["growth"] else None,
            "technical": result["technical"].as_dict(),
            "risk": result["risk"].as_dict(),
            "liquidity": result["liquidity"].as_dict(),
            "explanation": result["explanation"],
        }
        repository.upsert_scores(
            asset,
            as_of=fundamental.reference_date,
            model_version=result["model_version"],
            scores=scores,
            coverage_pct=result["coverage"],
            data_quality_score=result["data_quality"].score,
            details=details,
        )
        processed += 1
    return processed


def run_market_full_sync(payload: dict) -> dict:
    """Run the legacy full synchronization entirely inside the worker."""
    asset_type = str(payload.get("asset_type") or "").strip().lower()
    if asset_type not in {"stock", "fii", "other_b3"}:
        raise ValueError("invalid_market_sync_asset_type")
    include_technicals = bool(payload.get("include_technicals", True))
    session = get_session_factory()()
    steps: dict[str, dict] = {}
    try:
        pipeline = MarketIngestionPipeline(session)
        deactivated = pipeline.repo.deactivate_unsupported_assets()
        session.commit()
        steps["catalog_cleanup"] = {"status": "ok", "deactivated": len(deactivated)}
        _report(payload, session, current=1, total=4, message="Catálogo preparado.")

        def run_step(name, operation):
            try:
                result = operation()
                session.commit()
                steps[name] = {
                    "status": "ok",
                    "received": result.rows_received,
                    "saved": result.rows_valid,
                    "rejected": result.rows_rejected,
                    "filtered": max(
                        0,
                        result.rows_received - result.rows_valid - result.rows_rejected,
                    ),
                    "warnings": result.warnings,
                }
            except Exception as exc:
                session.rollback()
                steps[name] = {
                    "status": "error",
                    "error_code": type(exc).__name__,
                    "message": str(exc)[:500],
                }

        if asset_type == "stock":
            run_step("fundamentals", pipeline.ingest_stocks)
            if include_technicals:
                run_step("catalog_and_technicals", lambda: pipeline.ingest_technicals("stock"))
        elif asset_type == "fii":
            run_step("fundamentals", pipeline.ingest_fiis)
            if include_technicals:
                run_step("catalog_and_technicals", lambda: pipeline.ingest_technicals("fii"))
        else:
            run_step("catalog_and_technicals", pipeline.ingest_other_b3)
        _report(payload, session, current=2, total=4, message="Dados de mercado importados.")

        if asset_type in {"stock", "fii"}:
            try:
                score_count = refresh_intelligence_scores(session, asset_type)
                session.commit()
                steps["scores"] = {"status": "ok", "saved": score_count}
            except Exception as exc:
                session.rollback()
                steps["scores"] = {
                    "status": "error",
                    "error_code": type(exc).__name__,
                    "message": str(exc)[:500],
                }
        else:
            steps["scores"] = {
                "status": "ok", "saved": 0, "note": "not_applicable_to_other_b3",
            }
        _report(payload, session, current=3, total=4, message="Notas atualizadas.")

        repository = AssetRepository(session)
        if asset_type == "other_b3":
            catalog_count = sum(
                len(repository.list_assets(asset_type=value, limit=5000))
                for value in ("etf", "bdr", "future")
            )
        else:
            catalog_count = len(repository.list_assets(asset_type=asset_type, limit=5000))
        if catalog_count == 0:
            raise ValueError("market_sync_empty_catalog")
        token = utcnow().strftime("%Y%m%dT%H%M")
        BackgroundJobRepository(session).enqueue(
            "current_metrics_refresh",
            {
                "snapshot_key": "market:current-metrics",
                "trigger": "market-full-sync",
                "cycle": token,
            },
            requested_by=str(payload.get("requested_by") or "system:market-sync"),
            priority=146,
            max_attempts=3,
            deduplication_key="refresh:current_metrics",
            idempotency_key=f"market-full-sync:current-metrics:{token}",
        )
        session.commit()
        failed_steps = sorted(
            name
            for name, result in steps.items()
            if str(result.get("status") or "").lower() == "error"
        )
        if failed_steps:
            _report(
                payload,
                session,
                current=4,
                total=4,
                message="Sincronização parcial; uma ou mais etapas serão repetidas.",
            )
            raise RuntimeError(
                "market_sync_failed_steps:" + ",".join(failed_steps)
            )
        _report(payload, session, current=4, total=4, message="Sincronização concluída.")
        return {
            "asset_type": asset_type,
            "catalog_count": catalog_count,
            "steps": steps,
        }
    finally:
        session.close()


def run_asset_price_ingest(payload: dict) -> dict:
    ticker = str(payload.get("ticker") or "").strip().upper()
    asset_type = str(payload.get("asset_type") or "stock").strip().lower()
    if not ticker:
        raise ValueError("ticker_required")
    session = get_session_factory()()
    try:
        result = PriceIngestionService(session).ingest_asset(ticker, asset_type=asset_type)
        asset = AssetRepository(session).get_by_ticker(ticker)
        if asset is not None:
            result["current_metrics"] = AssetCurrentMetricsService(session).sync_asset(asset)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def refresh_b3_index_portfolio(payload: dict) -> dict:
    index_code = str(payload.get("index_code") or "IBOV").strip().upper()
    snapshot_key = str(payload.get("snapshot_key") or "market:index:ibov").strip().lower()
    result = B3IndexProvider().fetch(index_code)
    now = utcnow()
    session = get_session_factory()()
    try:
        SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key,
            snapshot_kind="b3_index_portfolio",
            payload=result,
            source=result.get("source") or "B3",
            source_url=result.get("source_url"),
            as_of=now,
            valid_until=now + timedelta(hours=30),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return {
        "index": index_code,
        "member_count": len(result.get("members") or []),
        "snapshot_key": snapshot_key,
        "as_of": now.isoformat(),
    }

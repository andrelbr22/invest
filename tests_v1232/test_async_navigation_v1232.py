from __future__ import annotations
from frontend_test_support import browser_source

from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.api.app import MarketSyncRequest, _index_portfolio, sync_market
from investment_engine.core.jobs.handlers import DEFAULT_JOB_HANDLERS
from investment_engine.core.repositories.background_jobs import BackgroundJobRepository
from investment_engine.core.repositories.economic_series import SharedSnapshotRepository
from investment_engine.infrastructure.db.base import Base


ROOT = Path(__file__).resolve().parents[1]
api_module = import_module("investment_engine.api.app")


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def test_full_market_sync_returns_immediately_and_deduplicates_active_work():
    engine = _engine()
    with Session(engine) as session:
        first = sync_market(
            MarketSyncRequest(asset_type="stock", include_technicals=True),
            access={"email": "owner@example.com", "can_sync_market": True},
            db=session,
        )
        second = sync_market(
            MarketSyncRequest(asset_type="stock", include_technicals=True),
            access={"email": "owner@example.com", "can_sync_market": True},
            db=session,
        )

        assert first["accepted"] is True
        assert first["scheduled"] is True
        assert first["job"]["job_type"] == "market_full_sync"
        assert first["job"]["status"] == "queued"
        assert second["scheduled"] is False
        assert second["job"]["id"] == first["job"]["id"]
        assert len(BackgroundJobRepository(session).list_recent(10)) == 1


def test_ibov_navigation_reads_persisted_snapshot_without_provider(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        SharedSnapshotRepository(session).save_valid(
            snapshot_key="market:index:ibov",
            snapshot_kind="b3_index_portfolio",
            payload={
                "index": "IBOV",
                "source": "B3",
                "members": [{"ticker": "PETR4", "weight_pct": "8.0"}],
            },
            as_of=datetime.now(timezone.utc),
        )
        session.commit()

    monkeypatch.setattr(api_module, "get_session_factory", lambda: lambda: Session(engine))
    result = _index_portfolio("IBOV")

    assert result["members"] == [{"ticker": "PETR4", "weight_pct": "8.0"}]
    assert result["stale"] is False
    assert result["unavailable"] is False
    assert result["refreshing"] is False


def test_navigation_module_has_no_live_b3_news_or_ingestion_provider_calls():
    application = (ROOT / "investment_engine/api/app.py").read_text(encoding="utf-8")
    assert "B3IndexProvider" not in application
    assert "MarketNewsService" not in application
    assert "MarketIngestionPipeline" not in application
    assert "PriceIngestionService" not in application
    assert "_MARKET_NEWS" not in application
    assert "NewsCacheRepository" in application
    assert '"market_full_sync"' in application
    assert '"asset_price_ingest"' in application


def test_worker_owns_all_formerly_synchronous_network_work():
    expected = {
        "market_full_sync",
        "asset_price_ingest",
        "b3_index_portfolio_refresh",
    }
    assert expected <= set(DEFAULT_JOB_HANDLERS)


def test_admin_frontend_tracks_async_market_sync_instead_of_waiting_on_provider():
    script = browser_source(Path(__file__).resolve().parents[1])
    assert "/data/sync-market" in script
    assert "/data/jobs/" in script
    assert "job.status===\"succeeded\"" in script
    assert "A atualização continua em segundo plano" in script
    assert 'current_metrics_refresh:"Métricas atuais pré-calculadas"' in script


def test_full_market_sync_does_not_report_success_when_an_ingestion_step_failed():
    worker = (ROOT / "investment_engine/core/jobs/market_ingestion.py").read_text(
        encoding="utf-8"
    )
    failure_check = worker.index("failed_steps = sorted(")
    completion = worker.index('message="Sincronização concluída."')

    assert failure_check < completion
    assert "market_sync_failed_steps:" in worker
    assert "Sincronização parcial; uma ou mais etapas serão repetidas." in worker

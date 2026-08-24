from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from investment_engine.core.backtesting.batch import BacktestBatchService
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import BacktestRunORM
from investment_engine.integrations.backtest_delivery import (
    BacktestDeliveryClient,
    BacktestDeliveryError,
    delivery_checksum,
)


ROOT = Path(__file__).resolve().parents[1]


class Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class Http:
    def __init__(self, *, response=None, error=None):
        self.response = response or Response(200, {"accepted": True})
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_delivery_checksum_is_stable_and_client_never_places_token_in_payload():
    assert delivery_checksum({"b": 2, "a": 1}) == delivery_checksum({"a": 1, "b": 2})
    http = Http()
    client = BacktestDeliveryClient(
        base_url="https://formacaodoinvestidor.com.br",
        token="x" * 48,
        http=http,
        attempts=1,
    )
    payload = {"ticker": "PETR4", "completed_runs": 1, "failed_runs": 0, "errors": [], "results": []}
    client.deliver_asset("00000000-0000-0000-0000-000000000001", payload)
    url, request = http.calls[0]
    assert url.endswith("/automation/backtests/jobs/00000000-0000-0000-0000-000000000001/assets")
    assert request["headers"]["Authorization"] == f"Bearer {'x' * 48}"
    assert "token" not in request["json"]
    assert request["json"]["checksum"] == delivery_checksum(payload)


def test_delivery_network_error_is_safe_and_does_not_leak_token():
    secret = "s" * 48
    client = BacktestDeliveryClient(
        base_url="https://formacaodoinvestidor.com.br",
        token=secret,
        http=Http(error=requests.ConnectionError("offline")),
        attempts=1,
    )
    with pytest.raises(BacktestDeliveryError) as error:
        client.finish_job("00000000-0000-0000-0000-000000000001")
    assert secret not in str(error.value)


def test_asset_delivery_is_imported_once_and_updates_progress():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    package = {
        "asset": {"ticker": "PETR4", "asset_type": "stock", "name": "Petrobras"},
        "run": {
            "config_hash": "a" * 64,
            "market_date": now.date().isoformat(),
            "engine_version": "0.13.0",
            "strategy_id": "buy_hold",
            "strategy_name": "Comprar e manter",
            "requested_start": now.isoformat(),
            "requested_end": now.isoformat(),
            "actual_start": now.isoformat(),
            "actual_end": now.isoformat(),
            "initial_capital": 10000.0,
            "fee_pct": 0.03,
            "slippage_pct": 0.05,
            "risk_free_rate_pct": 0.0,
            "parameters": {},
            "metrics": {"total_return_pct": 10.0},
            "equity_curve": [],
            "snapshot": {},
            "ranking_score": 1.0,
            "sample_status": "valid",
            "current_signal": {"status": "neutral", "as_of": now.isoformat()},
            "data_source": "yahoo",
            "status": "valid",
            "created_at": now.isoformat(),
            "trades": [],
        },
    }
    with Session(engine) as session:
        service = BacktestBatchService(session)
        job = service.create_job(
            requested_by="owner@example.com",
            source="site",
            tickers=["PETR4"],
            max_combinations=1,
        )
        service.start_existing_job(job)
        delivery, created = service.receive_asset_delivery(
            job,
            ticker="PETR4",
            checksum="b" * 64,
            completed_runs=1,
            failed_runs=0,
            results=[package],
            errors=[],
        )
        assert created is True
        repeated, created_again = service.receive_asset_delivery(
            job,
            ticker="PETR4",
            checksum="b" * 64,
            completed_runs=1,
            failed_runs=0,
            results=[package],
            errors=[],
        )
        assert created_again is False
        assert repeated.id == delivery.id
        assert len(list(session.scalars(select(BacktestRunORM)))) == 1
        progress = service.job_dict(job)
        assert progress["processed_assets"] == 1
        assert progress["progress_pct"] == 100.0
        service.finalize_job(job)
        assert job.status == "completed"


def test_cancelled_job_preserves_received_assets_and_rejects_new_delivery():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = BacktestBatchService(session)
        job = service.create_job(
            requested_by="owner@example.com",source="site",
            tickers=["PETR4","VALE3"],max_combinations=1,
        )
        service.start_existing_job(job)
        delivery,created=service.receive_asset_delivery(
            job,ticker="PETR4",checksum="c" * 64,
            completed_runs=0,failed_runs=1,results=[],errors=[{"error":"falha controlada"}],
        )
        assert created is True
        service.mark_cancelled(job,requested_by="owner@example.com")
        assert job.status == "cancelled"
        repeated,created_again=service.receive_asset_delivery(
            job,ticker="PETR4",checksum="c" * 64,
            completed_runs=0,failed_runs=1,results=[],errors=[{"error":"falha controlada"}],
        )
        assert repeated.id == delivery.id
        assert created_again is False
        with pytest.raises(ValueError,match="batch_job_cancelled"):
            service.receive_asset_delivery(
                job,ticker="VALE3",checksum="d" * 64,
                completed_runs=0,failed_runs=1,results=[],errors=[],
            )
        service.mark_failed(job,code="late_failure",message="retorno tardio")
        assert job.status == "cancelled"


def test_retry_job_contains_only_failed_and_pending_assets_in_original_order():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = BacktestBatchService(session)
        source = service.create_job(
            requested_by="owner@example.com",source="site",
            tickers=["PETR4","VALE3","BBAS3"],max_combinations=1,
        )
        service.start_existing_job(source)
        service.receive_asset_delivery(
            source,ticker="PETR4",checksum="e" * 64,
            completed_runs=1,failed_runs=0,results=[],errors=[],
        )
        service.receive_asset_delivery(
            source,ticker="VALE3",checksum="f" * 64,
            completed_runs=0,failed_runs=1,results=[],errors=[{"error":"falha"}],
        )
        service.mark_failed(source,code="worker_stopped",message="interrompido")
        summary=service.job_dict(source)
        assert summary["failed_tickers"] == ["VALE3"]
        assert summary["pending_tickers"] == ["BBAS3"]
        assert summary["retry_tickers"] == ["VALE3","BBAS3"]
        retry,dispatch_required=service.create_retry_job(source,requested_by="owner@example.com")
        assert dispatch_required is True
        assert retry.source == "retry"
        assert retry.requested_tickers_json == ["VALE3","BBAS3"]


def test_workflow_uses_disposable_postgres_and_not_the_oracle_database_secret():
    workflow = (ROOT / ".github" / "workflows" / "backtests-semanais.yml").read_text(encoding="utf-8")
    assert "postgres:16-alpine" in workflow
    assert "BACKTEST_CALLBACK_TOKEN: ${{ secrets.BACKTEST_CALLBACK_TOKEN }}" in workflow
    assert "secrets.DATABASE_URL" not in workflow
    assert "secrets.DATABASE_ADMIN_URL" not in workflow
    assert "/automation/backtests" not in workflow  # URL routing remains inside application code.


def test_public_api_exposes_only_authenticated_delivery_routes_in_caddy():
    api_source = (ROOT / "investment_engine" / "api" / "app.py").read_text(encoding="utf-8")
    caddy = (ROOT / "deployment" / "Caddyfile.oracle-micro.example").read_text(encoding="utf-8")
    assert "require_backtest_callback" in api_source
    assert "compare_digest" in api_source
    assert '@app.post("/automation/backtests/jobs/{job_id}/assets")' in api_source
    assert "path /automation/backtests/*" in caddy
    assert "reverse_proxy app:8765" in caddy


def test_owner_api_and_admin_ui_expose_safe_cancel_retry_and_live_refresh():
    api_source = (ROOT / "investment_engine" / "api" / "app.py").read_text(encoding="utf-8")
    ui_source = (ROOT / "examples" / "streamlit_v15_integrated.py").read_text(encoding="utf-8")
    assert '@app.patch("/backtests/batch/jobs/{job_id}/cancelled")' in api_source
    assert '@app.post("/backtests/batch/jobs/{job_id}/retry")' in api_source
    assert '@st.fragment(run_every="15s")' in ui_source
    assert "Confirmo que desejo interromper este lote" in ui_source
    assert "Repetir somente ativos com falha ou pendentes" in ui_source

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from investment_engine.core.backtesting.batch import BacktestBatchService
from investment_engine.api.app import BacktestAutomationAssetRequest
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import BacktestBatchChunkORM, BacktestBatchDeliveryORM
from investment_engine.integrations.backtest_delivery import BacktestDeliveryClient, delivery_checksum
from investment_engine.integrations.github_actions import dispatch_official_backtests


ROOT = Path(__file__).resolve().parents[1]


class _Response:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {"accepted": True}

    def json(self):
        return self._data


class _HTTP:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.status_code)


def test_client_splits_large_asset_and_signs_every_retry_safe_part():
    http = _HTTP()
    client = BacktestDeliveryClient(
        base_url="https://formacaodoinvestidor.com.br/testefdi",
        token="x" * 64,
        http=http,
    )
    payload = {
        "ticker": "PETR4",
        "completed_runs": 17,
        "failed_runs": 0,
        "results": [{"strategy_id": f"strategy-{index}", "curve": [index] * 20} for index in range(17)],
        "errors": [{"message": "aviso final"}],
    }

    response = client.deliver_asset("job-1", payload)

    assert response["chunks_sent"] == 3
    assert len(http.calls) == 3
    for expected_index, (_url, call) in enumerate(http.calls, start=1):
        body = call["json"]
        signed = {key: value for key, value in body.items() if key != "checksum"}
        assert body["chunk_index"] == expected_index
        assert body["chunk_count"] == 3
        assert body["checksum"] == delivery_checksum(signed)
        assert len(body["results"]) <= 8
        assert body["errors"] == ([{"message": "aviso final"}] if expected_index == 3 else [])


def test_original_one_part_checksum_remains_compatible():
    payload = {
        "ticker": "PETR4",
        "completed_runs": 1,
        "failed_runs": 0,
        "results": [{"strategy_id": "old-client"}],
        "errors": [],
    }
    request = BacktestAutomationAssetRequest(
        **payload,
        checksum=delivery_checksum(payload),
    )
    signed = request.model_dump(exclude={"checksum"}, exclude_unset=True)
    assert signed == payload
    assert delivery_checksum(signed) == request.checksum


def test_service_accepts_repeated_chunks_without_duplicate_delivery():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = BacktestBatchService(session)
        job = service.create_job(
            requested_by="owner@example.com",
            source="retry",
            tickers=["PETR4"],
            max_combinations=2,
        )
        first, created = service.receive_asset_delivery(
            job,
            ticker="PETR4",
            checksum="a" * 64,
            completed_runs=0,
            failed_runs=2,
            results=[],
            errors=[],
            chunk_index=1,
            chunk_count=2,
        )
        repeated, repeated_created = service.receive_asset_delivery(
            job,
            ticker="PETR4",
            checksum="a" * 64,
            completed_runs=0,
            failed_runs=2,
            results=[],
            errors=[],
            chunk_index=1,
            chunk_count=2,
        )
        final, final_created = service.receive_asset_delivery(
            job,
            ticker="PETR4",
            checksum="b" * 64,
            completed_runs=0,
            failed_runs=2,
            results=[],
            errors=[{"message": "dados indisponíveis"}],
            chunk_index=2,
            chunk_count=2,
        )
        session.commit()

        chunks = list(session.scalars(select(BacktestBatchChunkORM)))
        deliveries = list(session.scalars(select(BacktestBatchDeliveryORM)))
        final_status = job.status

    assert created is True and first["asset_complete"] is False
    assert repeated_created is False and repeated["asset_complete"] is False
    assert final_created is True and final["asset_complete"] is True
    assert len(chunks) == 2
    assert len(deliveries) == 1
    assert final_status == "completed_with_errors"


def test_dispatch_routes_manual_validation_back_to_staging():
    http = _HTTP(status_code=204)
    result = dispatch_official_backtests(
        token="secret-token",
        tickers=["PETR4"],
        job_id="job-1",
        environment="staging",
        http=http,
    )
    sent = http.calls[0][1]["json"]["inputs"]
    assert sent["environment"] == "staging"
    assert result["environment"] == "staging"


def test_workflow_and_panel_keep_scheduled_production_separate_from_test_retry():
    workflow = (ROOT / ".github/workflows/backtests-semanais.yml").read_text(encoding="utf-8")
    script = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")
    assert "github.event_name == 'schedule'" in workflow
    assert "formacaodoinvestidor.com.br/testefdi" in workflow
    assert "data-retry-official-job" in script
    assert "received_chunks" in script
    assert "HTTP 413" in script

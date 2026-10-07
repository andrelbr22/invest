from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import smtplib
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.core.investor_events.service import DataQualityService
from investment_engine.core.jobs.schedules import RefreshSchedule, _snapshot_is_stale_at
from investment_engine.core.repositories.background_jobs import BackgroundJobRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetORM
from investment_engine.integrations import email_delivery
from investment_engine.integrations.email_delivery import AlertEmailSender


ROOT = Path(__file__).resolve().parents[1]


def _sqlite_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_job_completion_serializes_python_native_diagnostics():
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)
    identifier = uuid4()
    with Session(engine) as session:
        repository = BackgroundJobRepository(session)
        row, created = repository.enqueue("alb_universe_monitor", {"trigger": "test"})
        assert created is True
        repository.complete(row, {
            "reference_date": date(2026, 10, 7),
            "updated_at": datetime(2026, 10, 7, 18, tzinfo=timezone.utc),
            "ratio": Decimal("12.50"),
            "identifier": identifier,
            "tickers": {"PETR4", "VALE3"},
            "invalid_float": float("nan"),
        })
        session.commit()
        session.refresh(row)

        assert row.status == "succeeded"
        assert row.result_json["reference_date"] == "2026-10-07"
        assert row.result_json["updated_at"] == "2026-10-07T18:00:00+00:00"
        assert row.result_json["ratio"] == 12.5
        assert row.result_json["identifier"] == str(identifier)
        assert sorted(row.result_json["tickers"]) == ["PETR4", "VALE3"]
        assert row.result_json["invalid_float"] is None


def test_smtp_transient_disconnect_is_retried_once(monkeypatch):
    attempts = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            attempts.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, *_args):
            return None

        def send_message(self, _message):
            if len(attempts) == 1:
                raise smtplib.SMTPServerDisconnected("temporary disconnect")

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_delivery.time, "sleep", lambda _seconds: None)
    configuration = SimpleNamespace(
        smtp_configured=True,
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_timeout_seconds=30,
        smtp_starttls=True,
        smtp_username="user",
        smtp_password="secret",
        smtp_from_name="FDI",
        smtp_from_email="sender@example.test",
    )

    AlertEmailSender(configuration).send(
        recipients=["owner@example.test"],
        subject="Operational",
        text_body="Test",
    )

    assert attempts == [
        ("smtp.example.test", 587, 30),
        ("smtp.example.test", 587, 30),
    ]


def test_fixed_daily_source_stays_fresh_until_its_next_real_slot():
    schedule = RefreshSchedule(
        "daily",
        "Daily",
        "daily_refresh",
        "daily:snapshot",
        "Test",
        timedelta(hours=6),
        fixed_times=(time(19),),
        weekdays_only=True,
    )
    # Wednesday at 17:00 in São Paulo. Tuesday's 19:01 result is the newest
    # possible scheduled result even though it is older than six hours.
    current = datetime(2026, 10, 7, 20, tzinfo=timezone.utc)
    previous_result = datetime(2026, 10, 6, 22, 1, tzinfo=timezone.utc)
    assert _snapshot_is_stale_at(schedule, previous_result, current) is False

    # Once Wednesday's 19:00 slot passes, the old result is correctly stale.
    after_slot = datetime(2026, 10, 7, 22, 30, tzinfo=timezone.utc)
    assert _snapshot_is_stale_at(schedule, previous_result, after_slot) is True


def test_data_quality_skips_components_not_produced_for_multiassets():
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for asset_type in ("stock", "fii", "etf", "bdr", "future"):
            session.add(AssetORM(
                ticker=f"{asset_type[:3].upper()}1",
                name=asset_type,
                asset_type=asset_type,
                is_active=True,
            ))
        session.commit()
        rows = DataQualityService(session)._asset_coverage(
            datetime(2026, 10, 7, tzinfo=timezone.utc)
        )

    keys = {row["key"] for row in rows}
    for asset_type in ("etf", "bdr", "future"):
        assert f"assets:{asset_type}:fundamentals" not in keys
        assert f"assets:{asset_type}:scores" not in keys
        assert f"assets:{asset_type}:technicals_daily" in keys
    for asset_type in ("stock", "fii"):
        assert f"assets:{asset_type}:fundamentals" in keys
        assert f"assets:{asset_type}:scores" in keys


def test_backup_retention_runs_only_after_confirmed_object_upload():
    script = (ROOT / "deployment/backup-local-db.sh").read_text(encoding="utf-8")
    upload = script.index("Backup enviado ao Object Storage")
    remote_check = script.index("os object head")
    retention = script.index("Retenção local concluída")
    removal = script.index('rm -- "${RESOLVED}"')

    assert 'LOCAL_BACKUP_KEEP_COUNT="${LOCAL_BACKUP_KEEP_COUNT:-3}"' in script
    assert "--auth instance_principal" in script
    assert upload < remote_check < removal < retention
    assert '"${BACKUP_DIR}"/investment_engine_*.sql.gz)' in script
    assert "preservado por falta de confirmação remota" in script

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.api.app import app, get_db
from investment_engine.core.auth.email_code import (
    CODE_TTL,
    EmailLoginCodeORM,
    EmailLoginCodeService,
    EmailLoginRequestGuard,
    utcnow,
)
from investment_engine.infrastructure.db.base import Base
from investment_engine.integrations.email_delivery import AlertEmailSender


def test_email_login_table_is_part_of_alembic_target_metadata():
    assert "email_login_codes" in Base.metadata.tables


def _client(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as session:
            yield session

    delivered = []
    monkeypatch.setattr(
        AlertEmailSender,
        "send_login_code",
        lambda _self, **payload: delivered.append(payload),
    )
    app.dependency_overrides[get_db] = override_db
    # Production cookies are Secure; HTTPS keeps this test equivalent to the deployed flow.
    return engine, TestClient(app, base_url="https://localhost"), delivered


def test_email_code_login_is_hashed_rate_limited_single_use_and_creates_session(monkeypatch):
    engine, client, delivered = _client(monkeypatch)
    try:
        requested = client.post("/auth/email/request", json={
            "email": "Pessoa@Example.com",
            "next": "/plataforma/",
        })
        assert requested.status_code == 200
        assert requested.json()["expires_in_seconds"] == 600
        code = delivered[-1]["code"]
        assert len(code) == 6 and code.isdigit()

        with Session(engine) as session:
            stored = session.get(EmailLoginCodeORM, "pessoa@example.com")
            assert stored is not None
            assert code not in stored.code_hash
            assert stored.expires_at > stored.requested_at

        limited = client.post("/auth/email/request", json={"email": "pessoa@example.com"})
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1

        wrong = client.post("/auth/email/verify", json={
            "email": "pessoa@example.com", "code": "000000",
        })
        assert wrong.status_code == 401

        verified = client.post("/auth/email/verify", json={
            "email": "pessoa@example.com", "code": code,
        })
        assert verified.status_code == 200
        assert verified.json()["authenticated"] is True
        session_response = client.get("/session/me").json()
        assert session_response["authenticated"] is True
        assert session_response["user"]["email"] == "pessoa@example.com"
        assert session_response["user"]["auth_method"] == "email_code"

        reused = client.post("/auth/email/verify", json={
            "email": "pessoa@example.com", "code": code,
        })
        assert reused.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_new_email_code_replaces_previous_and_expired_code_fails(monkeypatch):
    engine, client, delivered = _client(monkeypatch)
    try:
        assert client.post("/auth/email/request", json={"email": "a@example.com"}).status_code == 200
        old_code = delivered[-1]["code"]
        with Session(engine) as session:
            row = session.get(EmailLoginCodeORM, "a@example.com")
            row.requested_at = row.requested_at - timedelta(minutes=2)
            session.commit()
        assert client.post("/auth/email/request", json={"email": "a@example.com"}).status_code == 200
        new_code = delivered[-1]["code"]
        assert new_code != old_code
        assert client.post("/auth/email/verify", json={
            "email": "a@example.com", "code": old_code,
        }).status_code == 401
        assert client.post("/auth/email/verify", json={
            "email": "a@example.com", "code": new_code,
        }).status_code == 200

        with Session(engine) as session:
            service = EmailLoginCodeService(session, secret="x" * 48)
            _row, expired_code = service.issue("expired@example.com", now=utcnow() - CODE_TTL - timedelta(seconds=1))
            session.commit()
            assert service.verify("expired@example.com", expired_code, now=utcnow()) is False
    finally:
        app.dependency_overrides.clear()


def test_email_login_rejects_invalid_addresses_without_sending(monkeypatch):
    _engine, client, delivered = _client(monkeypatch)
    try:
        response = client.post("/auth/email/request", json={"email": "not-an-email"})
        assert response.status_code == 422
        assert delivered == []
    finally:
        app.dependency_overrides.clear()


def test_delivery_failure_preserves_the_persisted_one_minute_cooldown(monkeypatch):
    engine, client, _delivered = _client(monkeypatch)

    def delivery_failure(_self, **_payload):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr(AlertEmailSender, "send_login_code", delivery_failure)
    try:
        failed = client.post("/auth/email/request", json={"email": "failure@example.com"})
        assert failed.status_code == 503
        with Session(engine) as session:
            persisted = session.get(EmailLoginCodeORM, "failure@example.com")
            assert persisted is not None
            assert persisted.requested_at is not None

        repeated = client.post("/auth/email/request", json={"email": "failure@example.com"})
        assert repeated.status_code == 429
        assert repeated.json()["detail"] == "email_login_rate_limited"
    finally:
        app.dependency_overrides.clear()


def test_expired_challenges_are_cleaned_and_burst_guard_has_no_raw_identifiers():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = EmailLoginCodeService(session, secret="x" * 48)
        service.issue("old@example.com", now=utcnow() - timedelta(days=2))
        session.commit()
        service.issue("current@example.com", now=utcnow())
        session.commit()
        assert session.get(EmailLoginCodeORM, "old@example.com") is None
        assert session.get(EmailLoginCodeORM, "current@example.com") is not None

    guard = EmailLoginRequestGuard(client_limit=2, global_limit=3, window_seconds=60)
    assert guard.reserve("hashed-client-a", now=100) is None
    assert guard.reserve("hashed-client-a", now=101) is None
    assert guard.reserve("hashed-client-a", now=102) == 59
    assert guard.reserve("hashed-client-b", now=102) is None
    assert guard.reserve("hashed-client-c", now=103) == 58
    assert "192.0.2.1" not in guard._clients


def test_first_code_issue_uses_a_per_email_postgresql_transaction_lock():
    class PostgreSQLBind:
        class dialect:
            name = "postgresql"

    class SessionRecorder:
        calls = []

        @staticmethod
        def get_bind():
            return PostgreSQLBind()

        @classmethod
        def execute(cls, statement, parameters):
            cls.calls.append((str(statement), parameters))

    recorder = SessionRecorder()
    service = EmailLoginCodeService(recorder, secret="x" * 48)
    service._serialize_first_issue("Pessoa@Example.com")
    assert len(recorder.calls) == 1
    sql, parameters = recorder.calls[0]
    assert "pg_advisory_xact_lock" in sql
    assert isinstance(parameters["lock_id"], int)
    assert "pessoa@example.com" not in str(parameters)

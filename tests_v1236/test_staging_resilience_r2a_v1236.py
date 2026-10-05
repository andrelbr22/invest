from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from investment_engine.integrations import email_delivery
from investment_engine.integrations.email_delivery import AlertEmailSender


ROOT = Path(__file__).resolve().parents[1]


def test_staging_pool_and_notifications_match_concurrent_runtime():
    compose = (ROOT / "docker-compose.oracle-web.yml").read_text(encoding="utf-8")
    staging = compose.split("  staging:", 1)[1].split("  worker:", 1)[0]

    assert 'DATABASE_POOL_SIZE: "4"' in staging
    assert 'DATABASE_MAX_OVERFLOW: "1"' in staging
    assert 'DATABASE_POOL_TIMEOUT_SECONDS: "20"' in staging
    assert 'OPERATIONAL_NOTIFICATIONS_ENABLED: "false"' in staging


def test_navigation_projections_use_independent_savepoints():
    source = (
        ROOT / "investment_engine" / "core" / "current_metrics.py"
    ).read_text(encoding="utf-8")

    navigation = source.split("def sync_navigation_metrics(", 1)[1].split(
        "def sync_navigation_tickers(", 1,
    )[0]
    assert navigation.count("with self.session.begin_nested():") == 2
    assert navigation.count("self.session.flush()") >= 3


def test_smtp_sender_uses_the_bounded_configured_timeout(monkeypatch):
    observed = {}

    class FakeSMTP:
        def __init__(self, _host, _port, *, timeout):
            observed["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, _username, _password):
            return None

        def send_message(self, _message):
            return None

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)
    configuration = SimpleNamespace(
        smtp_configured=True,
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_timeout_seconds=7,
        smtp_starttls=True,
        smtp_username="user",
        smtp_password="secret",
        smtp_from_name="Formação do Investidor",
        smtp_from_email="noreply@example.test",
    )

    AlertEmailSender(configuration).send(
        recipients=["owner@example.test"],
        subject="Teste",
        text_body="Mensagem de teste",
    )

    assert observed["timeout"] == 7


def test_worker_treats_mail_outage_as_recoverable_warning():
    source = (
        ROOT / "investment_engine" / "core" / "jobs" / "worker.py"
    ).read_text(encoding="utf-8")

    assert "if settings.operational_notifications_enabled:" in source
    assert "except EmailDeliveryError as exc:" in source
    assert "operational_notification_failed" in source

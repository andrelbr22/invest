from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import investment_engine.core.alerts.service as alert_service_module
from investment_engine.core.alerts.service import AlertMonitor, evaluate_alert, is_b3_monitoring_window
from investment_engine.core.repositories.access import AccessPolicyRepository, full_owner_policy, policy_dict
from investment_engine.core.repositories.alerts import AlertRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import PriceAlertEventORM, PriceAlertORM


def _factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_alert_permissions_and_limits_are_isolated_per_user():
    factory = _factory()
    with factory() as session:
        repository = AccessPolicyRepository(session)
        first = repository.register("first@example.com")
        second = repository.register("second@example.com")
        repository.update(
            first.email,
            can_view_portfolio=True,
            can_use_price_alerts=True,
            can_alert_price_above=True,
            alert_asset_limit=3,
        )
        session.commit()

        first_policy = policy_dict(first)
        second_policy = policy_dict(second)
        assert first_policy["can_use_price_alerts"] is True
        assert first_policy["can_alert_price_above"] is True
        assert first_policy["alert_asset_limit"] == 3
        assert second_policy["can_use_price_alerts"] is False
        assert second_policy["alert_asset_limit"] == 0
        assert full_owner_policy("owner@example.com")["alert_asset_limit"] == 10


def test_rule_evaluation_uses_high_low_and_previous_close_change():
    factory = _factory()
    with factory() as session:
        alert = AlertRepository(session).upsert(
            owner_email="owner@example.com",
            symbol="PETR4",
            provider_symbol="PETR4",
            display_name="Petrobras",
            market_scope="b3",
            rules={
                "price_above": 40,
                "price_below": 38,
                "change_positive_pct": 3,
                "change_negative_pct": None,
            },
        )
        matched, configured = evaluate_alert(alert, {
            "high": 40.1,
            "low": 38.5,
            "change_pct": 3.2,
        })
        assert matched == ["price_above", "change_positive_pct"]
        assert configured["price_below"] == 38.0


def test_permission_reduction_disables_surplus_and_removes_denied_rules():
    factory = _factory()
    with factory() as session:
        repository = AlertRepository(session)
        for symbol in ("PETR4", "VALE3", "BBAS3"):
            repository.upsert(
                owner_email="member@example.com",
                symbol=symbol,
                provider_symbol=symbol,
                display_name=symbol,
                market_scope="b3",
                rules={
                    "price_above": 50,
                    "price_below": 40,
                    "change_positive_pct": None,
                    "change_negative_pct": None,
                },
            )
        repository.enforce_policy(
            "member@example.com",
            limit=1,
            permissions={
                "price_above": True,
                "price_below": False,
                "change_positive_pct": False,
                "change_negative_pct": False,
            },
        )
        session.commit()
        alerts = repository.list_for_owner("member@example.com")
        assert sum(row.status == "active" for row in alerts) == 1
        assert all(row.price_below is None for row in alerts)
        assert all(row.price_above is not None for row in alerts)


def test_b3_window_uses_brasilia_weekdays_from_10_to_18():
    assert is_b3_monitoring_window(datetime(2026, 8, 25, 13, 0, tzinfo=timezone.utc)) is True
    assert is_b3_monitoring_window(datetime(2026, 8, 25, 21, 0, tzinfo=timezone.utc)) is False
    assert is_b3_monitoring_window(datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)) is False


def test_monitor_triggers_once_sends_to_both_emails_and_keeps_history(monkeypatch):
    factory = _factory()
    with factory() as session:
        repository = AlertRepository(session)
        repository.update_preference("owner@example.com", "secondary@example.com")
        repository.upsert(
            owner_email="owner@example.com",
            symbol="PETR4",
            provider_symbol="PETR4",
            display_name="Petrobras",
            market_scope="b3",
            rules={
                "price_above": 40,
                "price_below": None,
                "change_positive_pct": None,
                "change_negative_pct": None,
            },
        )
        session.commit()

    class Provider:
        def snapshot(self, symbols, *, market_scope):
            assert symbols == ["PETR4"]
            assert market_scope == "b3"
            return {
                "price": 40.05,
                "high": 40.10,
                "low": 39.90,
                "previous_close": 39.00,
                "change_pct": 2.69,
                "quote_at": datetime(2026, 8, 25, 13, 1, tzinfo=timezone.utc),
                "currency": "BRL",
                "interval": "1m",
                "source": "fonte de teste",
            }

    class Sender:
        configured = True

        def __init__(self):
            self.sent = []

        def send_alert(self, payload):
            self.sent.append(payload)

    sender = Sender()
    monkeypatch.setattr(alert_service_module, "get_session_factory", lambda: factory)
    monitor = AlertMonitor(provider=Provider(), sender=sender)
    outcome = monitor.run_once(datetime(2026, 8, 25, 13, 2, tzinfo=timezone.utc))

    assert outcome == {"checked": 1, "triggered": 1, "delivered": 1, "quote_failures": 0}
    assert sender.sent[0]["recipients"] == ["owner@example.com", "secondary@example.com"]

    with factory() as session:
        alert = session.scalar(select(PriceAlertORM))
        event = session.scalar(select(PriceAlertEventORM))
        assert alert.status == "triggered"
        assert event.delivery_status == "sent"
        assert event.quote_at == datetime(2026, 8, 25, 13, 1)

    second = monitor.run_once(datetime(2026, 8, 25, 13, 8, tzinfo=timezone.utc))
    assert second["checked"] == 0
    assert len(sender.sent) == 1

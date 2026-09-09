from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.alert_policy import (
    B3_ALERT_INTERVAL_MINUTES,
    MARKET_ALERT_INTERVAL_MINUTES,
)
from investment_engine.core.alerts.catalog import market_alert_catalog
from investment_engine.core.alerts.service import is_b3_monitoring_window
from investment_engine.core.repositories.alerts import AlertRepository
from investment_engine.infrastructure.db.base import Base


def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def add_alert(session, *, symbol, market_scope, last_checked_at=None, status="active"):
    row = AlertRepository(session).upsert(
        owner_email=f"{symbol.lower()}@example.com",
        symbol=symbol,
        provider_symbol=symbol,
        display_name=symbol,
        market_scope=market_scope,
        rules={"price_above": 100},
    )
    row.last_checked_at = last_checked_at
    row.status = status
    return row


def test_due_alerts_respect_five_and_thirty_minute_boundaries():
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    with database_session() as session:
        cases = (
            ("B3DUE", "b3", now - timedelta(minutes=5), True),
            ("B3WAIT", "b3", now - timedelta(minutes=5) + timedelta(seconds=1), False),
            ("MKTDUE", "market", now - timedelta(minutes=30), True),
            ("MKTWAIT", "market", now - timedelta(minutes=30) + timedelta(seconds=1), False),
        )
        for symbol, scope, checked_at, _expected in cases:
            add_alert(session, symbol=symbol, market_scope=scope, last_checked_at=checked_at)
        session.commit()

        due_symbols = {row.symbol for row in AlertRepository(session).due_alerts(now)}

        for symbol, _scope, _checked_at, expected in cases:
            assert (symbol in due_symbols) is expected


def test_due_alerts_include_never_checked_and_ignore_disabled_rows():
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    with database_session() as session:
        add_alert(session, symbol="B3NEW", market_scope="b3")
        add_alert(session, symbol="MKTNEW", market_scope="market")
        add_alert(session, symbol="MKTOFF", market_scope="market", status="disabled")
        session.commit()

        due_symbols = {row.symbol for row in AlertRepository(session).due_alerts(now)}

        assert due_symbols == {"B3NEW", "MKTNEW"}


def test_market_catalog_and_repository_share_monitoring_intervals():
    assert B3_ALERT_INTERVAL_MINUTES == 5
    assert MARKET_ALERT_INTERVAL_MINUTES == 30
    catalog = market_alert_catalog()
    assert catalog
    assert {item["interval_minutes"] for item in catalog} == {30}
    assert all(item["market_scope"] == "market" for item in catalog)
    assert all(item["continuous_monitoring"] is True for item in catalog)


def test_b3_window_is_weekdays_from_ten_until_before_eighteen_in_brasilia():
    # 8 September 2026 is a Tuesday; Brasília is UTC-3 on this date.
    assert is_b3_monitoring_window(datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)) is True
    assert is_b3_monitoring_window(datetime(2026, 9, 8, 20, 59, tzinfo=timezone.utc)) is True
    assert is_b3_monitoring_window(datetime(2026, 9, 8, 12, 59, tzinfo=timezone.utc)) is False
    assert is_b3_monitoring_window(datetime(2026, 9, 8, 21, 0, tzinfo=timezone.utc)) is False
    assert is_b3_monitoring_window(datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)) is False

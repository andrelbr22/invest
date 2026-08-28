from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.repositories.economic_series import (
    EconomicSeriesRepository,
    SharedSnapshotRepository,
)
from investment_engine.infrastructure.db.base import Base


def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_series_point_is_upserted_without_duplicate():
    with database_session() as session:
        repository = EconomicSeriesRepository(session)
        series = repository.upsert_series(
            code="ipca_12m",
            name="IPCA acumulado em 12 meses",
            unit="%",
            frequency="monthly",
            source="IBGE",
            accumulation_method="twelve_month_change",
        )
        observed = datetime(2026, 7, 1, tzinfo=timezone.utc)
        first, created = repository.add_point(
            series,
            observed_at=observed,
            reference_period="2026-07",
            value="4.25",
            published_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
        second, created_again = repository.add_point(
            series,
            observed_at=observed,
            reference_period="2026-07",
            value="4.26",
            published_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
        session.commit()
        assert created is True
        assert created_again is False
        assert second.id == first.id
        assert second.value == Decimal("4.26")
        assert repository.latest_points("IPCA_12M", 10) == [second]


def test_failed_refresh_preserves_last_valid_snapshot():
    with database_session() as session:
        repository = SharedSnapshotRepository(session)
        valid = repository.save_valid(
            snapshot_key="market-dashboard:main",
            snapshot_kind="market_dashboard",
            payload={"ibov": 100000},
            source="test",
            valid_until=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        original_hash = valid.payload_hash
        repository.mark_refresh_failed("market-dashboard:main", "provider_timeout")
        session.commit()
        current = repository.get("market-dashboard:main")
        assert current.payload_json == {"ibov": 100000}
        assert current.payload_hash == original_hash
        assert current.last_error_code == "provider_timeout"

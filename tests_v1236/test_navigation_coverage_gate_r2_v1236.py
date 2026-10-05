from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetCurrentMetricsORM, AssetORM
from scripts.check_navigation_coverage import navigation_coverage


ROOT = Path(__file__).resolve().parents[1]


def session_for_test() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_navigation_coverage_requires_both_materialized_projections():
    with session_for_test() as session:
        complete = AssetORM(ticker="OK3", name="Completo", asset_type="stock")
        pending = AssetORM(ticker="WAIT3", name="Pendente", asset_type="stock")
        inactive = AssetORM(
            ticker="OLD3", name="Inativo", asset_type="stock", is_active=False,
        )
        session.add_all([complete, pending, inactive])
        session.flush()
        session.add_all([
            AssetCurrentMetricsORM(
                asset_id=complete.id,
                valuation_calculated_at=complete.created_at,
                backtest_leaders_calculated_at=complete.created_at,
            ),
            AssetCurrentMetricsORM(asset_id=pending.id),
        ])
        session.commit()

        coverage = navigation_coverage(session)

        assert coverage.active_assets == 2
        assert coverage.current_metrics == 2
        assert coverage.valuations == 1
        assert coverage.backtest_leaders == 1
        assert coverage.complete is False


def test_navigation_coverage_is_complete_only_at_one_hundred_percent():
    with session_for_test() as session:
        asset = AssetORM(ticker="FAST3", name="Completo", asset_type="stock")
        session.add(asset)
        session.flush()
        session.add(AssetCurrentMetricsORM(
            asset_id=asset.id,
            valuation_calculated_at=asset.created_at,
            backtest_leaders_calculated_at=asset.created_at,
        ))
        session.commit()

        coverage = navigation_coverage(session)

        assert coverage.complete is True


def test_promotion_checks_navigation_coverage_before_benchmark_and_backup():
    promotion = (
        ROOT / "deployment" / "promote-staging-to-production.sh"
    ).read_text(encoding="utf-8")

    coverage = promotion.index("python -m scripts.check_navigation_coverage")
    benchmark = promotion.index("python -m scripts.benchmark_application_routes")
    backup = promotion.index('bash "${PROJECT_DIR}/deployment/backup-local-db.sh"')

    assert coverage < benchmark < backup
    assert "conclua a materialização das métricas atuais" in promotion

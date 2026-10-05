from __future__ import annotations

"""Block a release while navigation would still use expensive history fallbacks."""

from dataclasses import asdict, dataclass

from sqlalchemy import func, select

from investment_engine.infrastructure.db.models import AssetCurrentMetricsORM, AssetORM
from investment_engine.infrastructure.db.session import get_session_factory


@dataclass(frozen=True)
class NavigationCoverage:
    active_assets: int
    current_metrics: int
    valuations: int
    backtest_leaders: int

    @property
    def complete(self) -> bool:
        return (
            self.active_assets > 0
            and self.current_metrics == self.active_assets
            and self.valuations == self.active_assets
            and self.backtest_leaders == self.active_assets
        )


def navigation_coverage(session) -> NavigationCoverage:
    row = session.execute(
        select(
            func.count(AssetORM.id).label("active_assets"),
            func.count(AssetCurrentMetricsORM.asset_id).label("current_metrics"),
            func.count(AssetCurrentMetricsORM.asset_id)
            .filter(AssetCurrentMetricsORM.valuation_calculated_at.is_not(None))
            .label("valuations"),
            func.count(AssetCurrentMetricsORM.asset_id)
            .filter(AssetCurrentMetricsORM.backtest_leaders_calculated_at.is_not(None))
            .label("backtest_leaders"),
        )
        .select_from(AssetORM)
        .outerjoin(
            AssetCurrentMetricsORM,
            AssetCurrentMetricsORM.asset_id == AssetORM.id,
        )
        .where(AssetORM.is_active.is_(True))
    ).one()
    return NavigationCoverage(**{
        key: int(value or 0) for key, value in row._mapping.items()
    })


def main() -> int:
    session = get_session_factory()()
    try:
        coverage = navigation_coverage(session)
    finally:
        session.close()
    values = asdict(coverage)
    print(
        "navigation_coverage "
        + " ".join(f"{key}={value}" for key, value in values.items())
    )
    if not coverage.complete:
        print(
            "Cobertura incompleta: a navegação ainda poderia recorrer aos "
            "históricos. Aguarde o current_metrics_refresh antes de promover."
        )
        return 2
    print("navigation coverage ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

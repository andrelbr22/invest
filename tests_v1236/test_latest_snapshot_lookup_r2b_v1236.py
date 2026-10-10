from pathlib import Path
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.infrastructure.db.models import (
    FundamentalSnapshotORM,
    TechnicalSnapshotORM,
)


ROOT = Path(__file__).resolve().parents[1]


class _PostgresBind:
    dialect = postgresql.dialect()


class _CaptureSession:
    def __init__(self):
        self.statement = None

    def get_bind(self):
        return _PostgresBind()

    def scalars(self, statement):
        self.statement = statement
        return []


def _compiled_latest(model, *, filters=(), order_by=()) -> str:
    session = _CaptureSession()
    repository = AssetRepository(session)
    assert repository._latest_rows_by_asset(
        model,
        [uuid4(), uuid4()],
        filters=filters,
        order_by=order_by,
    ) == {}
    return str(session.statement.compile(dialect=postgresql.dialect())).upper()


def test_postgres_latest_fundamental_uses_distinct_on_instead_of_window_rank():
    sql = _compiled_latest(
        FundamentalSnapshotORM,
        order_by=(
            FundamentalSnapshotORM.reference_date.desc(),
            FundamentalSnapshotORM.retrieved_at.desc(),
            FundamentalSnapshotORM.id.desc(),
        ),
    )

    assert "DISTINCT ON (FUNDAMENTAL_SNAPSHOTS.ASSET_ID)" in sql
    assert "ROW_NUMBER" not in sql
    assert "REFERENCE_DATE DESC" in sql


def test_postgres_latest_technical_keeps_timeframe_and_descending_priority():
    sql = _compiled_latest(
        TechnicalSnapshotORM,
        filters=(TechnicalSnapshotORM.timeframe == "1D",),
        order_by=(
            TechnicalSnapshotORM.as_of.desc(),
            TechnicalSnapshotORM.retrieved_at.desc(),
            TechnicalSnapshotORM.id.desc(),
        ),
    )

    assert "DISTINCT ON (TECHNICAL_SNAPSHOTS.ASSET_ID)" in sql
    assert "TECHNICAL_SNAPSHOTS.TIMEFRAME" in sql
    assert "AS_OF DESC" in sql


def test_r2b_adds_concurrent_descending_indexes_and_updates_release_identity():
    migration = (ROOT / "alembic/versions/0031_v123_latest_snapshot_idx.py").read_text(
        encoding="utf-8",
    )
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")

    assert migration.count("CREATE INDEX CONCURRENTLY") >= 1
    assert "reference_date DESC" in migration
    assert "as_of DESC" in migration
    assert "timestamp DESC" in migration
    assert "V1.23.8 R1" in publisher
    assert '0032_v1237_browser_perf' in workflow

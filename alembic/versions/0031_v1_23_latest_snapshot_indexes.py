"""V1.23.6 R2B indexes for bounded latest-snapshot lookups.

Revision ID: 0031_v1_23_latest_snapshot_indexes
Revises: 0030_v1_23_navigation_metrics

The indexes are additive.  Historical snapshots and the previous indexes are
kept intact.  PostgreSQL builds the new indexes concurrently so normal reads
and ingestion can continue while the isolated migration service is running.
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_v1_23_latest_snapshot_indexes"
down_revision = "0030_v1_23_navigation_metrics"
branch_labels = None
depends_on = None


POSTGRES_INDEXES = {
    "ix_fundamental_latest_desc": (
        "fundamental_snapshots",
        "asset_id, reference_date DESC, retrieved_at DESC, id DESC",
    ),
    "ix_technical_latest_desc": (
        "technical_snapshots",
        "asset_id, timeframe, as_of DESC, retrieved_at DESC, id DESC",
    ),
    "ix_score_latest_desc": (
        "score_snapshots",
        "asset_id, as_of DESC, calculated_at DESC, id DESC",
    ),
    "ix_price_latest_desc": (
        "price_bars",
        "asset_id, timeframe, timestamp DESC, retrieved_at DESC, id DESC",
    ),
}


PORTABLE_INDEXES = {
    "ix_fundamental_latest_desc": (
        "fundamental_snapshots",
        ["asset_id", "reference_date", "retrieved_at", "id"],
    ),
    "ix_technical_latest_desc": (
        "technical_snapshots",
        ["asset_id", "timeframe", "as_of", "retrieved_at", "id"],
    ),
    "ix_score_latest_desc": (
        "score_snapshots",
        ["asset_id", "as_of", "calculated_at", "id"],
    ),
    "ix_price_latest_desc": (
        "price_bars",
        ["asset_id", "timeframe", "timestamp", "retrieved_at", "id"],
    ),
}


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _existing_tables()
    if bind.dialect.name == "postgresql":
        context = op.get_context()
        with context.autocommit_block():
            op.execute("SET statement_timeout = '15min'")
            op.execute("SET lock_timeout = '30s'")
            for name, (table, expression) in POSTGRES_INDEXES.items():
                if table not in tables:
                    continue
                # A cancelled concurrent build can leave an invalid index.
                # Dropping the R2B-only name first makes the migration safely
                # repeatable after an interrupted deployment.
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
                op.execute(
                    f'CREATE INDEX CONCURRENTLY "{name}" '
                    f'ON "{table}" ({expression})'
                )
            op.execute("RESET lock_timeout")
            op.execute("RESET statement_timeout")
        return

    inspector = sa.inspect(bind)
    for name, (table, columns) in PORTABLE_INDEXES.items():
        if table not in tables:
            continue
        existing = {item["name"] for item in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)
            inspector = sa.inspect(bind)


def downgrade() -> None:
    bind = op.get_bind()
    tables = _existing_tables()
    if bind.dialect.name == "postgresql":
        context = op.get_context()
        with context.autocommit_block():
            op.execute("SET statement_timeout = '15min'")
            for name in reversed(tuple(POSTGRES_INDEXES)):
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
            op.execute("RESET statement_timeout")
        return

    inspector = sa.inspect(bind)
    for name, (table, _columns) in reversed(tuple(PORTABLE_INDEXES.items())):
        if table not in tables:
            continue
        existing = {item["name"] for item in inspector.get_indexes(table)}
        if name in existing:
            op.drop_index(name, table_name=table)
            inspector = sa.inspect(bind)

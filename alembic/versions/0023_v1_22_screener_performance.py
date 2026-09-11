"""V1.22 indexed latest-snapshot lookups for market screeners.

Revision ID: 0023_v1_22_screener_performance
Revises: 0022_v1_22_observability
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_v1_22_screener_performance"
down_revision = "0022_v1_22_observability"
branch_labels = None
depends_on = None


INDEXES = {
    "assets": (
        "ix_assets_type_active_ticker",
        ["asset_type", "is_active", "ticker"],
    ),
    "fundamental_snapshots": (
        "ix_fundamental_latest_lookup",
        ["asset_id", "reference_date", "retrieved_at", "id"],
    ),
    "technical_snapshots": (
        "ix_technical_latest_lookup",
        ["asset_id", "timeframe", "as_of", "retrieved_at", "id"],
    ),
    "score_snapshots": (
        "ix_score_latest_lookup",
        ["asset_id", "as_of", "calculated_at", "id"],
    ),
}


def _index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table_name, (index_name, columns) in INDEXES.items():
        if table_name not in tables:
            continue
        if index_name not in _index_names(inspector, table_name):
            # PostgreSQL can scan this B-tree backwards after the equality
            # prefixes, matching the DESC lookup used by the repository.
            op.create_index(index_name, table_name, columns)
            inspector = sa.inspect(bind)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table_name, (index_name, _columns) in reversed(tuple(INDEXES.items())):
        if table_name in tables and index_name in _index_names(inspector, table_name):
            op.drop_index(index_name, table_name=table_name)
            inspector = sa.inspect(bind)

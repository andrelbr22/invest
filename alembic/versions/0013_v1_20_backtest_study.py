"""Optimize the official backtest study query.

Revision ID: 0013_v1_20_backtest_study
Revises: 0012_v1_20_foundation
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_v1_20_backtest_study"
down_revision = "0012_v1_20_foundation"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_backtest_runs_official_study"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("backtest_runs")}
    if INDEX_NAME not in indexes:
        op.create_index(
            INDEX_NAME,
            "backtest_runs",
            ["scope", "status", "asset_id", "config_hash", "created_at", "id"],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("backtest_runs")}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="backtest_runs")

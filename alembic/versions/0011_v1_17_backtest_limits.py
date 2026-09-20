"""V1.17 user backtest limits and daily request accounting.

Revision ID: 0011_v1_17_backtest_limits
Revises: 0010_v1_14_alerts
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_v1_17_backtest_limits"
down_revision = "0010_v1_14_alerts"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "user_access_policies" in tables:
        columns = {column["name"] for column in inspector.get_columns("user_access_policies")}
        if "backtest_asset_limit" not in columns:
            op.add_column("user_access_policies", sa.Column(
                "backtest_asset_limit", sa.Integer(), nullable=False, server_default="0"
            ))
        if "backtest_daily_limit" not in columns:
            op.add_column("user_access_policies", sa.Column(
                "backtest_daily_limit", sa.Integer(), nullable=False, server_default="0"
            ))

    if "backtest_request_usage" not in tables:
        op.create_table(
            "backtest_request_usage",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_email", sa.String(320), nullable=False),
            sa.Column("market_date", sa.Date(), nullable=False),
            sa.Column("asset_count", sa.Integer(), nullable=False),
            sa.Column("strategy_count", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="running"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_backtest_request_usage_owner_email", "backtest_request_usage", ["owner_email"])
        op.create_index("ix_backtest_request_usage_market_date", "backtest_request_usage", ["market_date"])
        op.create_index(
            "ix_backtest_request_usage_owner_day", "backtest_request_usage",
            ["owner_email", "market_date"],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "backtest_request_usage" in tables:
        op.drop_table("backtest_request_usage")
    if "user_access_policies" in tables:
        columns = {column["name"] for column in inspector.get_columns("user_access_policies")}
        if "backtest_daily_limit" in columns:
            op.drop_column("user_access_policies", "backtest_daily_limit")
        if "backtest_asset_limit" in columns:
            op.drop_column("user_access_policies", "backtest_asset_limit")

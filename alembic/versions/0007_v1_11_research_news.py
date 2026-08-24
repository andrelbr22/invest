"""V1.11.0 permissions for backtest studies and market news.

Revision ID: 0007_v1_11_research
Revises: 0006_v1_9_backtests
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_v1_11_research"
down_revision = "0006_v1_9_backtests"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_access_policies" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("user_access_policies")}
    if "can_view_backtest_studies" not in columns:
        op.add_column("user_access_policies", sa.Column(
            "can_view_backtest_studies", sa.Boolean(), nullable=False, server_default=sa.false()
        ))
    if "can_view_news_insights" not in columns:
        op.add_column("user_access_policies", sa.Column(
            "can_view_news_insights", sa.Boolean(), nullable=False, server_default=sa.false()
        ))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_access_policies" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("user_access_policies")}
    if "can_view_news_insights" in columns:
        op.drop_column("user_access_policies", "can_view_news_insights")
    if "can_view_backtest_studies" in columns:
        op.drop_column("user_access_policies", "can_view_backtest_studies")

"""Custom portfolio investments and manual value history.

Revision ID: 0016_v1_20_custom_investments
Revises: 0015_v1_20_personal_backtests
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_v1_20_custom_investments"
down_revision = "0015_v1_20_personal_backtests"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "portfolio_custom_investments" not in tables:
        op.create_table(
            "portfolio_custom_investments",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("portfolio_id", sa.Uuid(), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
            sa.Column("category", sa.String(40), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("institution", sa.String(160)),
            sa.Column("application_date", sa.Date(), nullable=False),
            sa.Column("maturity_date", sa.Date()),
            sa.Column("invested_value", sa.Numeric(22, 2), nullable=False),
            sa.Column("current_value", sa.Numeric(22, 2), nullable=False),
            sa.Column("current_value_as_of", sa.Date(), nullable=False),
            sa.Column("benchmark", sa.String(80)),
            sa.Column("liquidity", sa.String(120)),
            sa.Column("notes", sa.Text()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_portfolio_custom_investments_portfolio_id", "portfolio_custom_investments", ["portfolio_id"])
        op.create_index("ix_portfolio_custom_investments_category", "portfolio_custom_investments", ["category"])
        op.create_index("ix_portfolio_custom_investments_portfolio_active", "portfolio_custom_investments", ["portfolio_id", "is_active"])
    if "portfolio_custom_investment_values" not in tables:
        op.create_table(
            "portfolio_custom_investment_values",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("investment_id", sa.Uuid(), sa.ForeignKey("portfolio_custom_investments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reference_date", sa.Date(), nullable=False),
            sa.Column("value", sa.Numeric(22, 2), nullable=False),
            sa.Column("source", sa.String(24), nullable=False, server_default="manual"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("investment_id", "reference_date", name="uq_custom_investment_value_date"),
        )
        op.create_index("ix_portfolio_custom_investment_values_investment_id", "portfolio_custom_investment_values", ["investment_id"])
        op.create_index("ix_custom_investment_values_history", "portfolio_custom_investment_values", ["investment_id", "reference_date"])


def downgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "portfolio_custom_investment_values" in tables:
        op.drop_table("portfolio_custom_investment_values")
    if "portfolio_custom_investments" in tables:
        op.drop_table("portfolio_custom_investments")

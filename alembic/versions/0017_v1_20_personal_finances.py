"""V1.20 personal finances.

Revision ID: 0017_v1_20_personal_finances
Revises: 0016_v1_20_custom_investments
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_v1_20_personal_finances"
down_revision = "0016_v1_20_custom_investments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_access_policies", sa.Column("can_view_finances", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_access_policies", sa.Column("can_write_finances", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "finance_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("competence_month", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(22, 2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("institution", sa.String(length=120)),
        sa.Column("payment_method", sa.String(length=80)),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_transactions_owner_email", "finance_transactions", ["owner_email"])
    op.create_index("ix_finance_transactions_owner_month", "finance_transactions", ["owner_email", "competence_month"])
    op.create_index("ix_finance_transactions_owner_date", "finance_transactions", ["owner_email", "transaction_date"])
    op.create_table(
        "finance_monthly_budgets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=False),
        sa.Column("competence_month", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("limit_value", sa.Numeric(22, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_email", "competence_month", "category", name="uq_finance_budget_owner_month_category"),
    )
    op.create_index("ix_finance_monthly_budgets_owner_email", "finance_monthly_budgets", ["owner_email"])
    op.create_index("ix_finance_budgets_owner_month", "finance_monthly_budgets", ["owner_email", "competence_month"])


def downgrade():
    op.drop_table("finance_monthly_budgets")
    op.drop_table("finance_transactions")
    op.drop_column("user_access_policies", "can_write_finances")
    op.drop_column("user_access_policies", "can_view_finances")

"""V1.6.2 Google user access policies.

Revision ID: 0004_v1_6_access
Revises: 0003_v1_5
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_v1_6_access"
down_revision = "0003_v1_5"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "user_access_policies" in tables:
        return
    op.create_table(
        "user_access_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(180)),
        sa.Column("role", sa.String(24), nullable=False, server_default="visitor"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("can_view_market", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_use_advanced_filters", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_view_portfolio", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_write_portfolio", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_view_backtests", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_run_backtests", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_sync_market", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_manage_users", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_user_access_email"),
    )
    op.create_index("ix_user_access_policies_email", "user_access_policies", ["email"], unique=True)


def downgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "user_access_policies" in tables:
        op.drop_table("user_access_policies")

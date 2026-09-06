"""V1.21 valuation-family permissions.

Revision ID: 0020_v1_21_valuation_access
Revises: 0019_v1_20_access_rules
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_v1_21_valuation_access"
down_revision = "0019_v1_20_access_rules"
branch_labels = None
depends_on = None


PERMISSION_COLUMNS = (
    "can_use_relative_valuation",
    "can_use_economic_valuation",
)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if "user_access_policies" not in _tables():
        return

    access_columns = _columns("user_access_policies")
    for name in PERMISSION_COLUMNS:
        if name not in access_columns:
            op.add_column(
                "user_access_policies",
                sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    # Preserve the existing ALB contract: granting ALB grants every valuation
    # family, including accounts approved before this migration existed.
    op.get_bind().execute(
        sa.text(
            "UPDATE user_access_policies "
            "SET can_use_relative_valuation = :enabled, "
            "can_use_economic_valuation = :enabled "
            "WHERE can_use_alb_analysis = :enabled"
        ).bindparams(enabled=True)
    )


def downgrade():
    if "user_access_policies" not in _tables():
        return
    access_columns = _columns("user_access_policies")
    for name in reversed(PERMISSION_COLUMNS):
        if name in access_columns:
            op.drop_column("user_access_policies", name)

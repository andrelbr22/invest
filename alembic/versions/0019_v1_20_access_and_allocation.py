"""V1.20 analysis permissions and portfolio subcategories.

Revision ID: 0019_v1_20_access_rules
Revises: 0018_v1_20_curve_history
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_v1_20_access_rules"
down_revision = "0018_v1_20_curve_history"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    tables = _tables()
    if "user_access_policies" in tables:
        access_columns = _columns("user_access_policies")
        for name in (
            "can_use_fdi_analysis", "can_use_alb_analysis",
            "can_use_graham_valuation", "can_use_dividend_ceiling",
        ):
            if name not in access_columns:
                op.add_column(
                    "user_access_policies",
                    sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()),
                )
    if "portfolio_positions" in tables:
        position_columns = _columns("portfolio_positions")
        if "sector_override" not in position_columns:
            op.add_column("portfolio_positions", sa.Column("sector_override", sa.String(length=120)))
        if "segment_override" not in position_columns:
            op.add_column("portfolio_positions", sa.Column("segment_override", sa.String(length=120)))
    if "portfolio_custom_investments" in tables:
        custom_columns = _columns("portfolio_custom_investments")
        if "sector" not in custom_columns:
            op.add_column("portfolio_custom_investments", sa.Column("sector", sa.String(length=120)))
        if "segment" not in custom_columns:
            op.add_column("portfolio_custom_investments", sa.Column("segment", sa.String(length=120)))


def downgrade():
    tables = _tables()
    if "portfolio_custom_investments" in tables:
        custom_columns = _columns("portfolio_custom_investments")
        if "segment" in custom_columns:
            op.drop_column("portfolio_custom_investments", "segment")
        if "sector" in custom_columns:
            op.drop_column("portfolio_custom_investments", "sector")
    if "portfolio_positions" in tables:
        position_columns = _columns("portfolio_positions")
        if "segment_override" in position_columns:
            op.drop_column("portfolio_positions", "segment_override")
        if "sector_override" in position_columns:
            op.drop_column("portfolio_positions", "sector_override")
    if "user_access_policies" in tables:
        access_columns = _columns("user_access_policies")
        for name in reversed((
            "can_use_fdi_analysis", "can_use_alb_analysis",
            "can_use_graham_valuation", "can_use_dividend_ceiling",
        )):
            if name in access_columns:
                op.drop_column("user_access_policies", name)

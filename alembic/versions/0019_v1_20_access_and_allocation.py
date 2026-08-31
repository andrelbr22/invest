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


def upgrade():
    for name in (
        "can_use_fdi_analysis", "can_use_alb_analysis",
        "can_use_graham_valuation", "can_use_dividend_ceiling",
    ):
        op.add_column(
            "user_access_policies",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.add_column("portfolio_positions", sa.Column("sector_override", sa.String(length=120)))
    op.add_column("portfolio_positions", sa.Column("segment_override", sa.String(length=120)))
    op.add_column("portfolio_custom_investments", sa.Column("sector", sa.String(length=120)))
    op.add_column("portfolio_custom_investments", sa.Column("segment", sa.String(length=120)))


def downgrade():
    op.drop_column("portfolio_custom_investments", "segment")
    op.drop_column("portfolio_custom_investments", "sector")
    op.drop_column("portfolio_positions", "segment_override")
    op.drop_column("portfolio_positions", "sector_override")
    for name in reversed((
        "can_use_fdi_analysis", "can_use_alb_analysis",
        "can_use_graham_valuation", "can_use_dividend_ceiling",
    )):
        op.drop_column("user_access_policies", name)

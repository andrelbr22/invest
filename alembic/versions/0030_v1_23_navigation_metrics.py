"""V1.23.5 R2 materialized valuation and official-backtest navigation data.

Revision ID: 0030_v1_23_navigation_metrics
Revises: 0029_v1_23_current_metrics

The historical valuation and backtest tables remain untouched.  These fields
are a rebuildable current read model populated by the background worker.
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_v1_23_navigation_metrics"
down_revision = "0029_v1_23_current_metrics"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if "asset_current_metrics" not in set(inspector.get_table_names()):
        return set()
    return {
        str(column["name"])
        for column in inspector.get_columns("asset_current_metrics")
    }


def upgrade() -> None:
    existing = _columns()
    if not existing:
        return
    if "valuation_json" not in existing:
        op.add_column(
            "asset_current_metrics",
            sa.Column(
                "valuation_json", sa.JSON(), nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
    if "backtest_leaders_json" not in existing:
        op.add_column(
            "asset_current_metrics",
            sa.Column(
                "backtest_leaders_json", sa.JSON(), nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )
    if "valuation_calculated_at" not in existing:
        op.add_column(
            "asset_current_metrics",
            sa.Column("valuation_calculated_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "backtest_leaders_calculated_at" not in existing:
        op.add_column(
            "asset_current_metrics",
            sa.Column(
                "backtest_leaders_calculated_at", sa.DateTime(timezone=True), nullable=True,
            ),
        )


def downgrade() -> None:
    existing = _columns()
    for name in (
        "backtest_leaders_calculated_at",
        "valuation_calculated_at",
        "backtest_leaders_json",
        "valuation_json",
    ):
        if name in existing:
            op.drop_column("asset_current_metrics", name)

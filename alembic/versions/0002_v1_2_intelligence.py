"""V1.2 intelligence layer.

Revision ID: 0002_v1_2
Revises: 0001_v1_1
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_v1_2"
down_revision = "0001_v1_1"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    tables = _tables()
    if "technical_snapshots" in tables:
        cols = _columns("technical_snapshots")
        for c in ("bb_middle", "macd", "atr14", "volatility_annual_pct", "max_drawdown_1y_pct", "return_1m_pct", "return_3m_pct", "return_12m_pct"):
            if c not in cols:
                op.add_column("technical_snapshots", sa.Column(c, sa.Numeric(18, 6), nullable=True))
    if "price_bars" in tables:
        cols = _columns("price_bars")
        if "adjusted_close" not in cols:
            op.add_column("price_bars", sa.Column("adjusted_close", sa.Numeric(18, 6), nullable=True))
        if "retrieved_at" not in cols:
            op.add_column("price_bars", sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True))
        if "status" not in cols:
            op.add_column("price_bars", sa.Column("status", sa.String(24), nullable=False, server_default="valid"))

    tables = _tables()
    if "valuation_snapshots" not in tables:
        op.create_table(
            "valuation_snapshots",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("method", sa.String(48), nullable=False),
            sa.Column("method_version", sa.String(24), nullable=False),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("value", sa.Numeric(18, 6)),
            sa.Column("upside_pct", sa.Numeric(18, 6)),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("inputs_json", sa.JSON(), nullable=False),
            sa.UniqueConstraint("asset_id", "method", "as_of", "method_version", name="uq_valuation_asset_method_asof_version"),
        )
        op.create_index("ix_valuation_snapshots_asset_id", "valuation_snapshots", ["asset_id"])
    if "score_snapshots" not in tables:
        op.create_table(
            "score_snapshots",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("model_version", sa.String(24), nullable=False),
            sa.Column("quality_score", sa.Numeric(5, 2)),
            sa.Column("value_score", sa.Numeric(5, 2)),
            sa.Column("growth_score", sa.Numeric(5, 2)),
            sa.Column("technical_score", sa.Numeric(5, 2)),
            sa.Column("risk_score", sa.Numeric(5, 2)),
            sa.Column("liquidity_score", sa.Numeric(5, 2)),
            sa.Column("alb_score", sa.Numeric(5, 2)),
            sa.Column("coverage_pct", sa.Numeric(5, 2)),
            sa.Column("data_quality_score", sa.Numeric(5, 2)),
            sa.Column("details_json", sa.JSON(), nullable=False),
            sa.UniqueConstraint("asset_id", "as_of", "model_version", name="uq_score_asset_asof_version"),
        )
        op.create_index("ix_score_snapshots_asset_id", "score_snapshots", ["asset_id"])


def downgrade():
    tables = _tables()
    if "score_snapshots" in tables:
        op.drop_table("score_snapshots")
    if "valuation_snapshots" in tables:
        op.drop_table("valuation_snapshots")
    # Columns are intentionally retained on downgrade to avoid destructive loss of historical market data.

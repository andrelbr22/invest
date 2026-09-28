"""V1.23.2 current metrics materialization without removing history.

Revision ID: 0029_v1_23_current_metrics
Revises: 0028_v1_23_operational_retention
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_v1_23_current_metrics"
down_revision = "0028_v1_23_operational_retention"
branch_labels = None
depends_on = None


def _metric(name: str, precision: int = 18, scale: int = 6) -> sa.Column:
    return sa.Column(name, sa.Numeric(precision=precision, scale=scale), nullable=True)


def upgrade() -> None:
    if "asset_current_metrics" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "asset_current_metrics",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("fundamental_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("technical_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("score_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("price_bar_id", sa.Uuid(), nullable=True),
        sa.Column("fundamental_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fundamental_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score_calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        _metric("price"), _metric("pe"), _metric("pbv"),
        _metric("dividend_yield_pct"), _metric("ev_ebitda"),
        _metric("ebit_margin_pct"), _metric("net_margin_pct"),
        _metric("current_ratio"), _metric("roe_pct"), _metric("roic_pct"),
        _metric("gross_debt_to_equity"), _metric("net_debt_to_ebitda"),
        _metric("revenue_cagr_5y_pct"), _metric("earnings_cagr_5y_pct"),
        _metric("ffo_yield_pct"), _metric("cap_rate_pct"),
        _metric("vacancy_pct"), _metric("financial_vacancy_pct"),
        _metric("ltv_pct"), _metric("wale_years"),
        _metric("fundamental_daily_liquidity", 24, 2),
        _metric("score_tv", 8, 6),
        sa.Column("signal_tv", sa.String(length=24), nullable=True),
        _metric("market_cap", 24, 2),
        _metric("technical_daily_liquidity", 24, 2),
        _metric("daily_liquidity", 24, 2),
        _metric("sma20"), _metric("sma50"), _metric("sma200"),
        _metric("sma20_1w"), _metric("sma50_1w"),
        _metric("sma20_1m"), _metric("sma50_1m"),
        _metric("rsi14"), _metric("macd"), _metric("atr14"),
        _metric("volatility_annual_pct"), _metric("max_drawdown_1y_pct"),
        _metric("return_1m_pct"), _metric("return_3m_pct"), _metric("return_12m_pct"),
        _metric("quality_score", 5, 2), _metric("value_score", 5, 2),
        _metric("growth_score", 5, 2), _metric("technical_score", 5, 2),
        _metric("risk_score", 5, 2), _metric("liquidity_score", 5, 2),
        _metric("alb_score", 5, 2), _metric("coverage_pct", 5, 2),
        _metric("data_quality_score", 5, 2),
        sa.Column("fundamental_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("technical_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("score_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("technical_features_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_refs_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("fallback_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("parity_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["fundamental_snapshot_id"], ["fundamental_snapshots.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["technical_snapshot_id"], ["technical_snapshots.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["score_snapshot_id"], ["score_snapshots.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["price_bar_id"], ["price_bars.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("asset_id"),
    )
    op.create_index(
        "ix_asset_current_metrics_updated", "asset_current_metrics", ["updated_at"], unique=False,
    )
    op.create_index(
        "ix_asset_current_metrics_fundamental_asof",
        "asset_current_metrics", ["fundamental_as_of"], unique=False,
    )
    op.create_index(
        "ix_asset_current_metrics_technical_asof",
        "asset_current_metrics", ["technical_as_of"], unique=False,
    )
    op.create_index(
        "ix_asset_current_metrics_alb_score", "asset_current_metrics", ["alb_score"], unique=False,
    )


def downgrade() -> None:
    if "asset_current_metrics" not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.drop_index("ix_asset_current_metrics_alb_score", table_name="asset_current_metrics")
    op.drop_index("ix_asset_current_metrics_technical_asof", table_name="asset_current_metrics")
    op.drop_index("ix_asset_current_metrics_fundamental_asof", table_name="asset_current_metrics")
    op.drop_index("ix_asset_current_metrics_updated", table_name="asset_current_metrics")
    op.drop_table("asset_current_metrics")

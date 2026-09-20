"""V1.5 portfolio and backtesting modules.

Revision ID: 0003_v1_5
Revises: 0002_v1_2
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_v1_5"
down_revision = "0002_v1_2"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    tables = _tables()
    if "portfolios" not in tables:
        op.create_table(
            "portfolios",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("base_currency", sa.String(8), nullable=False, server_default="BRL"),
            sa.Column("cash_balance", sa.Numeric(22, 2), nullable=False, server_default="0"),
            sa.Column("target_cash_pct", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_portfolios_name", "portfolios", ["name"])

    tables = _tables()
    if "portfolio_positions" not in tables:
        op.create_table(
            "portfolio_positions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("portfolio_id", sa.Uuid(), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
            sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stage", sa.String(24), nullable=False, server_default="position"),
            sa.Column("quantity", sa.Numeric(24, 8), nullable=False, server_default="0"),
            sa.Column("average_price", sa.Numeric(18, 6)),
            sa.Column("target_weight_pct", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("classification_override", sa.String(120)),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("portfolio_id", "asset_id", name="uq_portfolio_asset"),
        )
        op.create_index("ix_portfolio_positions_portfolio", "portfolio_positions", ["portfolio_id"])
    else:
        columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("portfolio_positions")}
        if "classification_override" not in columns:
            op.add_column("portfolio_positions", sa.Column("classification_override", sa.String(120)))

    tables = _tables()
    if "backtest_runs" not in tables:
        op.create_table(
            "backtest_runs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("strategy_id", sa.String(64), nullable=False),
            sa.Column("strategy_name", sa.String(160), nullable=False),
            sa.Column("requested_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("requested_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("actual_start", sa.DateTime(timezone=True)),
            sa.Column("actual_end", sa.DateTime(timezone=True)),
            sa.Column("initial_capital", sa.Numeric(22, 2), nullable=False),
            sa.Column("fee_pct", sa.Numeric(10, 6), nullable=False, server_default="0"),
            sa.Column("slippage_pct", sa.Numeric(10, 6), nullable=False, server_default="0"),
            sa.Column("risk_free_rate_pct", sa.Numeric(10, 6), nullable=False, server_default="0"),
            sa.Column("parameters_json", sa.JSON(), nullable=False),
            sa.Column("metrics_json", sa.JSON(), nullable=False),
            sa.Column("equity_curve_json", sa.JSON(), nullable=False),
            sa.Column("data_source", sa.String(64), nullable=False, server_default="yahoo"),
            sa.Column("status", sa.String(24), nullable=False, server_default="valid"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_backtest_runs_asset_id", "backtest_runs", ["asset_id"])
        op.create_index("ix_backtest_runs_strategy_id", "backtest_runs", ["strategy_id"])
        op.create_index("ix_backtest_runs_asset_created", "backtest_runs", ["asset_id", "created_at"])

    tables = _tables()
    if "backtest_trades" not in tables:
        op.create_table(
            "backtest_trades",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("run_id", sa.Uuid(), sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("entry_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("entry_price", sa.Numeric(18, 6), nullable=False),
            sa.Column("exit_date", sa.DateTime(timezone=True)),
            sa.Column("exit_price", sa.Numeric(18, 6)),
            sa.Column("return_pct", sa.Numeric(18, 6)),
            sa.Column("pnl_value", sa.Numeric(22, 2)),
            sa.Column("holding_days", sa.Integer()),
            sa.Column("exit_reason", sa.String(64)),
            sa.UniqueConstraint("run_id", "sequence", name="uq_backtest_run_sequence"),
        )
        op.create_index("ix_backtest_trades_run_id", "backtest_trades", ["run_id"])


def downgrade():
    tables = _tables()
    if "backtest_trades" in tables:
        op.drop_table("backtest_trades")
    if "backtest_runs" in tables:
        op.drop_table("backtest_runs")
    if "portfolio_positions" in tables:
        op.drop_table("portfolio_positions")
    if "portfolios" in tables:
        op.drop_table("portfolios")

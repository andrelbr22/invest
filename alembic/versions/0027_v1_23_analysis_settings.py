"""V1.23.0 R8 owner-managed screening presets and default columns.

Revision ID: 0027_v1_23_analysis_settings
Revises: 0026_v1_23_email_login
"""

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0027_v1_23_analysis_settings"
down_revision = "0026_v1_23_email_login"
branch_labels = None
depends_on = None


ASSET_TYPES = ("stock", "fii", "etf", "bdr", "future")
PRESET_KEYS = ("default", "cnpi", "alb")
FACTORY_VERSION = "v1.23.0-r7"


def _technical(values: dict | None = None) -> dict:
    return {
        "daily_trend": "any",
        "weekly_trend": "any",
        "monthly_trend": "any",
        "rsi14": None,
        "pivot_zone": "any",
        "near_pivot_level": "none",
        "pivot_tolerance_pct": 0.5,
        "volume_daily_above_ma9": False,
        "volume_monthly_above_ma9": False,
        **(values or {}),
    }


def _configuration(
    asset_type: str,
    *,
    fundamental: dict | None = None,
    valuation: dict | None = None,
    technical: dict | None = None,
    trend_period: int = 21,
) -> dict:
    return {
        "asset_type": asset_type,
        "fundamental_filters": fundamental or {},
        "score_filters": {},
        "valuation_flags": valuation or {},
        "valuation_assumptions": {},
        "technical_filters": _technical(technical),
        "trend_period": trend_period,
        "pivot_timeframe": "daily",
        "include_technical_columns": True,
        "limit": 50,
        "allowed_tickers": None,
        "company_sizes": [],
        "ibov_membership": "any",
    }


def _range(*, minimum=None, maximum=None) -> dict:
    return {"min": minimum, "max": maximum}


def _factory_presets() -> dict[tuple[str, str], dict]:
    stock = {
        "default": _configuration("stock", fundamental={
            "roe_pct": _range(minimum=8.0),
            "ebit_margin_pct": _range(minimum=5.0),
            "pbv": _range(maximum=5.0),
            "pe": _range(minimum=0.1, maximum=20.0),
            "current_ratio": _range(minimum=1.0),
            "daily_liquidity": _range(minimum=1_000_000.0),
        }, valuation={"below_graham": False, "logic": "all"}),
        "cnpi": _configuration("stock", fundamental={
            "roe_pct": _range(minimum=10.0),
            "net_margin_pct": _range(minimum=5.0),
            "pe": _range(minimum=0.1, maximum=20.0),
            "pbv": _range(maximum=3.0),
            "dividend_yield_pct": _range(minimum=4.0),
            "current_ratio": _range(minimum=1.0),
            "daily_liquidity": _range(minimum=1_000_000.0),
        }, valuation={"below_graham": False, "logic": "all"}),
        "alb": _configuration("stock", fundamental={
            "roe_pct": _range(minimum=15.0),
            "net_margin_pct": _range(minimum=8.0),
            "pe": _range(minimum=0.1, maximum=15.0),
            "pbv": _range(maximum=2.5),
            "dividend_yield_pct": _range(minimum=5.0),
            "current_ratio": _range(minimum=1.0),
            "daily_liquidity": _range(minimum=2_000_000.0),
        }, valuation={"below_graham": True, "logic": "all"}),
    }
    fii = {
        "default": _configuration("fii", fundamental={
            "pbv": _range(maximum=1.10),
            "dividend_yield_pct": _range(minimum=8.0),
            "ffo_yield_pct": _range(minimum=7.0),
            "vacancy_pct": _range(maximum=15.0),
            "daily_liquidity": _range(minimum=500_000.0),
        }, valuation={"below_barsi_6pct": False, "logic": "all"}),
        "cnpi": _configuration("fii", fundamental={
            "pbv": _range(maximum=1.05),
            "dividend_yield_pct": _range(minimum=9.0),
            "ffo_yield_pct": _range(minimum=9.0),
            "cap_rate_pct": _range(minimum=8.0),
            "vacancy_pct": _range(maximum=10.0),
            "daily_liquidity": _range(minimum=1_000_000.0),
        }, valuation={"below_barsi_6pct": False, "logic": "all"}),
        "alb": _configuration("fii", fundamental={
            "pbv": _range(maximum=0.95),
            "dividend_yield_pct": _range(minimum=10.0),
            "ffo_yield_pct": _range(minimum=10.0),
            "cap_rate_pct": _range(minimum=9.0),
            "vacancy_pct": _range(maximum=5.0),
            "daily_liquidity": _range(minimum=2_000_000.0),
        }, valuation={"below_barsi_6pct": True, "logic": "all"}),
    }
    technical = {
        "default": {},
        "cnpi": {"daily_trend": "up", "rsi14": {"min": 35.0, "max": 75.0}},
        "alb": {
            "daily_trend": "up", "weekly_trend": "up",
            "rsi14": {"min": 40.0, "max": 70.0},
        },
    }
    result = {("stock", key): value for key, value in stock.items()}
    result.update({("fii", key): value for key, value in fii.items()})
    for asset_type in ("etf", "bdr", "future"):
        for key, values in technical.items():
            result[(asset_type, key)] = _configuration(
                asset_type, technical=values, trend_period=20,
            )
    return result


FACTORY_COLUMNS = {
    "stock": ["ticker", "sector", "price", "pe", "pbv", "dy", "roe", "graham_upside", "barsi", "relative", "best_signal"],
    "fii": ["ticker", "segment", "price", "pbv", "dy", "ffo", "vacancy", "barsi", "relative", "best_signal"],
    "etf": ["ticker", "price", "nav", "nav_upside", "premium", "relative", "best_signal"],
    "bdr": ["ticker", "sector", "price", "pbv", "relative", "relative_upside", "best_signal"],
    "future": ["ticker", "price", "front", "expiry", "spot", "carry", "basis", "best_signal"],
}


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "screening_preset_settings" not in tables:
        op.create_table(
            "screening_preset_settings",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("asset_type", sa.String(length=16), nullable=False),
            sa.Column("preset_key", sa.String(length=16), nullable=False),
            sa.Column("factory_version", sa.String(length=40), nullable=False),
            sa.Column("factory_configuration_json", sa.JSON(), nullable=False),
            sa.Column("owner_configuration_json", sa.JSON()),
            sa.Column("owner_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_by", sa.String(length=320)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_type", "preset_key", name="uq_screening_preset_setting_type_key"),
        )
        op.create_index(
            "ix_screening_preset_settings_type", "screening_preset_settings", ["asset_type"], unique=False,
        )
    if "analysis_column_settings" not in tables:
        op.create_table(
            "analysis_column_settings",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("asset_type", sa.String(length=16), nullable=False),
            sa.Column("factory_columns_json", sa.JSON(), nullable=False),
            sa.Column("owner_columns_json", sa.JSON()),
            sa.Column("owner_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_by", sa.String(length=320)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_type"),
        )
        op.create_index(
            "ix_analysis_column_settings_asset_type", "analysis_column_settings", ["asset_type"], unique=True,
        )

    now = datetime.now(timezone.utc)
    preset_table = sa.table(
        "screening_preset_settings",
        sa.column("id", sa.Uuid()), sa.column("asset_type", sa.String()),
        sa.column("preset_key", sa.String()), sa.column("factory_version", sa.String()),
        sa.column("factory_configuration_json", sa.JSON()),
        sa.column("owner_configuration_json", sa.JSON()), sa.column("owner_enabled", sa.Boolean()),
        sa.column("revision", sa.Integer()), sa.column("updated_by", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)), sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing_presets = set(bind.execute(sa.select(
        preset_table.c.asset_type, preset_table.c.preset_key,
    )).all())
    preset_rows = [
        {
            "id": uuid.uuid4(), "asset_type": asset_type, "preset_key": preset_key,
            "factory_version": FACTORY_VERSION, "factory_configuration_json": configuration,
            "owner_configuration_json": None, "owner_enabled": False, "revision": 1,
            "updated_by": None, "created_at": now, "updated_at": now,
        }
        for (asset_type, preset_key), configuration in _factory_presets().items()
        if (asset_type, preset_key) not in existing_presets
    ]
    if preset_rows:
        bind.execute(preset_table.insert(), preset_rows)

    column_table = sa.table(
        "analysis_column_settings",
        sa.column("id", sa.Uuid()), sa.column("asset_type", sa.String()),
        sa.column("factory_columns_json", sa.JSON()), sa.column("owner_columns_json", sa.JSON()),
        sa.column("owner_enabled", sa.Boolean()), sa.column("revision", sa.Integer()),
        sa.column("updated_by", sa.String()), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing_columns = set(bind.execute(sa.select(column_table.c.asset_type)).scalars())
    column_rows = [
        {
            "id": uuid.uuid4(), "asset_type": asset_type,
            "factory_columns_json": columns, "owner_columns_json": None,
            "owner_enabled": False, "revision": 1, "updated_by": None,
            "created_at": now, "updated_at": now,
        }
        for asset_type, columns in FACTORY_COLUMNS.items()
        if asset_type not in existing_columns
    ]
    if column_rows:
        bind.execute(column_table.insert(), column_rows)


def downgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "analysis_column_settings" in tables:
        op.drop_index("ix_analysis_column_settings_asset_type", table_name="analysis_column_settings")
        op.drop_table("analysis_column_settings")
    if "screening_preset_settings" in tables:
        op.drop_index("ix_screening_preset_settings_type", table_name="screening_preset_settings")
        op.drop_table("screening_preset_settings")

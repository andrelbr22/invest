"""V1.21.3 reusable access levels and safe per-user overrides.

Revision ID: 0021_v1_21_access_levels
Revises: 0020_v1_21_valuation_access
"""

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0021_v1_21_access_levels"
down_revision = "0020_v1_21_valuation_access"
branch_labels = None
depends_on = None


PERMISSION_COLUMNS = (
    "can_view_market", "can_use_advanced_filters", "can_use_fdi_analysis",
    "can_use_alb_analysis", "can_use_graham_valuation", "can_use_dividend_ceiling",
    "can_use_relative_valuation", "can_use_economic_valuation", "can_view_portfolio",
    "can_write_portfolio", "can_view_finances", "can_write_finances",
    "can_view_backtests", "can_run_backtests", "can_refresh_backtest_signals",
    "can_view_backtest_studies", "can_view_news_insights", "can_use_price_alerts",
    "can_alert_price_above", "can_alert_price_below", "can_alert_change_positive",
    "can_alert_change_negative", "can_sync_market", "can_manage_users",
)
LIMIT_COLUMNS = (
    "custom_filter_limit", "alert_asset_limit", "backtest_asset_limit",
    "backtest_daily_limit", "backtest_strategy_limit", "backtest_cooldown_seconds",
)


def _level(name, description, sort_order, enabled=(), **limits):
    return {
        "name": name,
        "description": description,
        "sort_order": sort_order,
        "is_system": True,
        "is_active": True,
        **{field: field in enabled for field in PERMISSION_COLUMNS},
        "custom_filter_limit": 0,
        "alert_asset_limit": 0,
        "backtest_asset_limit": 0,
        "backtest_daily_limit": 0,
        "backtest_strategy_limit": 0,
        "backtest_cooldown_seconds": 60,
        **limits,
    }


BASIC = (
    "can_view_market", "can_use_advanced_filters", "can_view_portfolio",
    "can_write_portfolio", "can_view_backtests", "can_run_backtests",
    "can_view_news_insights", "can_use_price_alerts", "can_alert_price_above",
    "can_alert_price_below", "can_alert_change_positive", "can_alert_change_negative",
)
MEMBER = (
    *BASIC, "can_use_fdi_analysis", "can_use_graham_valuation",
    "can_use_dividend_ceiling", "can_view_finances", "can_write_finances",
    "can_refresh_backtest_signals", "can_view_backtest_studies",
)
VIP = tuple(field for field in PERMISSION_COLUMNS if field not in {"can_sync_market", "can_manage_users"})


DEFAULT_LEVELS = {
    "guest": _level(
        "Convidado", "Consulta o Painel de Mercado, sem recursos privados ou gravações.",
        10, ("can_view_market",),
    ),
    "basic": _level(
        "Acesso básico", "Recursos essenciais com limites reduzidos para filtros, carteira, alertas e backtests.",
        20, BASIC, custom_filter_limit=1, alert_asset_limit=1,
        backtest_asset_limit=1, backtest_daily_limit=1, backtest_strategy_limit=1,
    ),
    "member": _level(
        "Membro", "Análises, carteira, finanças, alertas e backtests com limites intermediários.",
        30, MEMBER, custom_filter_limit=2, alert_asset_limit=3,
        backtest_asset_limit=3, backtest_daily_limit=5, backtest_strategy_limit=2,
    ),
    "vip": _level(
        "Membro VIP", "Todos os recursos de investimento e os maiores limites de uso.",
        40, VIP, custom_filter_limit=3, alert_asset_limit=10,
        backtest_asset_limit=10, backtest_daily_limit=20, backtest_strategy_limit=5,
    ),
    "owner": _level(
        "Proprietário", "Acesso permanente e integral à plataforma e à administração.",
        1000, PERMISSION_COLUMNS, custom_filter_limit=3, alert_asset_limit=10,
        backtest_asset_limit=10, backtest_daily_limit=20, backtest_strategy_limit=5,
    ),
}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    tables = _tables()
    if "access_levels" not in tables:
        op.create_table(
            "access_levels",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("slug", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("description", sa.String(length=500)),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            *(
                sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false())
                for name in PERMISSION_COLUMNS
            ),
            *(
                sa.Column(
                    name,
                    sa.Integer(),
                    nullable=False,
                    server_default="60" if name == "backtest_cooldown_seconds" else "0",
                )
                for name in LIMIT_COLUMNS
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug", name="uq_access_levels_slug"),
        )
        op.create_index("ix_access_levels_slug", "access_levels", ["slug"], unique=True)

    levels = sa.table(
        "access_levels",
        sa.column("id", sa.Uuid()), sa.column("slug", sa.String()),
        sa.column("name", sa.String()), sa.column("description", sa.String()),
        sa.column("is_system", sa.Boolean()), sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        *(sa.column(name, sa.Boolean()) for name in PERMISSION_COLUMNS),
        *(sa.column(name, sa.Integer()) for name in LIMIT_COLUMNS),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    for slug, configuration in DEFAULT_LEVELS.items():
        exists = bind.execute(sa.select(levels.c.id).where(levels.c.slug == slug)).first()
        if not exists:
            bind.execute(sa.insert(levels).values(
                id=uuid.uuid4(), slug=slug, created_at=now, updated_at=now, **configuration,
            ))

    if "user_access_policies" not in tables:
        return
    access_columns = _columns("user_access_policies")
    if "access_level_id" not in access_columns:
        op.add_column("user_access_policies", sa.Column("access_level_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_user_access_policies_access_level_id",
            "user_access_policies", "access_levels", ["access_level_id"], ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_user_access_policies_access_level_id",
            "user_access_policies", ["access_level_id"], unique=False,
        )
    if "access_overrides_json" not in access_columns:
        op.add_column(
            "user_access_policies",
            sa.Column("access_overrides_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )
    access_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("user_access_policies")}
    if "ix_user_access_policies_status" not in access_indexes:
        op.create_index(
            "ix_user_access_policies_status",
            "user_access_policies", ["status"], unique=False,
        )

    # Only rows already marked owner are attached automatically. All other
    # historical rows remain in legacy mode so their exact permissions survive.
    bind.execute(sa.text(
        "UPDATE user_access_policies SET access_level_id = "
        "(SELECT id FROM access_levels WHERE slug = 'owner') "
        "WHERE role = 'owner' AND access_level_id IS NULL"
    ))


def downgrade():
    tables = _tables()
    if "user_access_policies" in tables:
        access_columns = _columns("user_access_policies")
        access_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("user_access_policies")}
        if "ix_user_access_policies_status" in access_indexes:
            op.drop_index("ix_user_access_policies_status", table_name="user_access_policies")
        if "access_overrides_json" in access_columns:
            op.drop_column("user_access_policies", "access_overrides_json")
        if "access_level_id" in access_columns:
            op.drop_index("ix_user_access_policies_access_level_id", table_name="user_access_policies")
            op.drop_constraint(
                "fk_user_access_policies_access_level_id", "user_access_policies", type_="foreignkey",
            )
            op.drop_column("user_access_policies", "access_level_id")
    if "access_levels" in tables:
        op.drop_index("ix_access_levels_slug", table_name="access_levels")
        op.drop_table("access_levels")

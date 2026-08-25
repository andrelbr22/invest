"""V1.14.0 multi-user intraday price alerts.

Revision ID: 0010_v1_14_alerts
Revises: 0009_v1_12_news_cache
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_v1_14_alerts"
down_revision = "0009_v1_12_news_cache"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "user_access_policies" in tables:
        columns = {column["name"] for column in inspector.get_columns("user_access_policies")}
        for name in (
            "can_use_price_alerts", "can_alert_price_above", "can_alert_price_below",
            "can_alert_change_positive", "can_alert_change_negative",
        ):
            if name not in columns:
                op.add_column("user_access_policies", sa.Column(
                    name, sa.Boolean(), nullable=False, server_default=sa.false()
                ))
        if "alert_asset_limit" not in columns:
            op.add_column("user_access_policies", sa.Column(
                "alert_asset_limit", sa.Integer(), nullable=False, server_default="0"
            ))

    if "user_alert_preferences" not in tables:
        op.create_table(
            "user_alert_preferences",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_email", sa.String(320), nullable=False),
            sa.Column("secondary_email", sa.String(320)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("owner_email", name="uq_user_alert_preferences_owner"),
        )
        op.create_index("ix_user_alert_preferences_owner_email", "user_alert_preferences", ["owner_email"])

    if "price_alerts" not in tables:
        op.create_table(
            "price_alerts",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_email", sa.String(320), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("provider_symbol", sa.String(32), nullable=False),
            sa.Column("display_name", sa.String(180), nullable=False),
            sa.Column("market_scope", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("price_above", sa.Numeric(22, 8)),
            sa.Column("price_below", sa.Numeric(22, 8)),
            sa.Column("change_positive_pct", sa.Numeric(12, 6)),
            sa.Column("change_negative_pct", sa.Numeric(12, 6)),
            sa.Column("last_checked_at", sa.DateTime(timezone=True)),
            sa.Column("last_quote_at", sa.DateTime(timezone=True)),
            sa.Column("last_price", sa.Numeric(22, 8)),
            sa.Column("last_change_pct", sa.Numeric(12, 6)),
            sa.Column("triggered_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("owner_email", "symbol", name="uq_price_alert_owner_symbol"),
        )
        op.create_index("ix_price_alerts_owner_email", "price_alerts", ["owner_email"])
        op.create_index("ix_price_alerts_symbol", "price_alerts", ["symbol"])
        op.create_index("ix_price_alerts_status", "price_alerts", ["status"])
        op.create_index("ix_price_alert_due", "price_alerts", ["status", "market_scope", "last_checked_at"])

    if "price_alert_events" not in tables:
        op.create_table(
            "price_alert_events",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("alert_id", sa.Uuid(), nullable=False),
            sa.Column("owner_email", sa.String(320), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("display_name", sa.String(180), nullable=False),
            sa.Column("triggered_rules_json", sa.JSON(), nullable=False),
            sa.Column("configured_values_json", sa.JSON(), nullable=False),
            sa.Column("observed_json", sa.JSON(), nullable=False),
            sa.Column("recipients_json", sa.JSON(), nullable=False),
            sa.Column("delivery_status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text()),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
            sa.Column("quote_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["alert_id"], ["price_alerts.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_price_alert_events_alert_id", "price_alert_events", ["alert_id"])
        op.create_index("ix_price_alert_events_owner_email", "price_alert_events", ["owner_email"])
        op.create_index("ix_price_alert_events_symbol", "price_alert_events", ["symbol"])
        op.create_index("ix_price_alert_events_owner_created", "price_alert_events", ["owner_email", "created_at"])
        op.create_index("ix_price_alert_events_delivery", "price_alert_events", ["delivery_status", "next_attempt_at"])


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table in ("price_alert_events", "price_alerts", "user_alert_preferences"):
        if table in tables:
            op.drop_table(table)
    if "user_access_policies" in tables:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("user_access_policies")}
        for name in (
            "alert_asset_limit", "can_alert_change_negative", "can_alert_change_positive",
            "can_alert_price_below", "can_alert_price_above", "can_use_price_alerts",
        ):
            if name in columns:
                op.drop_column("user_access_policies", name)

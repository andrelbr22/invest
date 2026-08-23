"""V1.7.0 isolated portfolios and personal screeners.

Revision ID: 0005_v1_7_multiuser
Revises: 0004_v1_6_access
"""
import os
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0005_v1_7_multiuser"
down_revision = "0004_v1_6_access"
branch_labels = None
depends_on = None


def _legacy_owner(bind) -> str:
    try:
        database_owner = bind.execute(sa.text(
            "SELECT email FROM user_access_policies WHERE role = 'owner' ORDER BY created_at LIMIT 1"
        )).scalar()
        if database_owner:
            return str(database_owner).strip().lower()
    except Exception:
        pass
    configured = os.getenv("APP_OWNER_EMAILS") or os.getenv("APP_ALLOWED_EMAILS") or ""
    configured_owner = next((x.strip().lower() for x in configured.split(",") if x.strip()), "")
    if configured_owner:
        return configured_owner
    return "local-owner@localhost"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "user_access_policies" in tables:
        columns = {c["name"] for c in inspector.get_columns("user_access_policies")}
        if "custom_filter_limit" not in columns:
            op.add_column("user_access_policies", sa.Column("custom_filter_limit", sa.Integer(), nullable=False, server_default="0"))

    if "portfolios" in tables:
        columns = {c["name"] for c in inspector.get_columns("portfolios")}
        if "owner_email" not in columns:
            op.add_column("portfolios", sa.Column("owner_email", sa.String(320), nullable=True))
            bind.execute(sa.text("UPDATE portfolios SET owner_email = :email WHERE owner_email IS NULL"), {"email": _legacy_owner(bind)})
            with op.batch_alter_table("portfolios") as batch:
                batch.alter_column("owner_email", existing_type=sa.String(320), nullable=False)
                batch.create_index("ix_portfolios_owner_email", ["owner_email"], unique=False)

    if "saved_screening_filters" not in tables:
        now = datetime.now(timezone.utc)
        op.create_table(
            "saved_screening_filters",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_email", sa.String(320), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("asset_type", sa.String(16), nullable=False),
            sa.Column("filters_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, default=now),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, default=now),
            sa.UniqueConstraint("owner_email", "name", name="uq_saved_filter_owner_name"),
        )
        op.create_index("ix_saved_screening_filters_owner_email", "saved_screening_filters", ["owner_email"], unique=False)
        op.create_index("ix_saved_filter_owner_type", "saved_screening_filters", ["owner_email", "asset_type"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "saved_screening_filters" in tables:
        op.drop_table("saved_screening_filters")
    if "portfolios" in tables and "owner_email" in {c["name"] for c in inspector.get_columns("portfolios")}:
        with op.batch_alter_table("portfolios") as batch:
            batch.drop_column("owner_email")
    if "user_access_policies" in tables and "custom_filter_limit" in {c["name"] for c in inspector.get_columns("user_access_policies")}:
        op.drop_column("user_access_policies", "custom_filter_limit")

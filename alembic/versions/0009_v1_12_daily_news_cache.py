"""V1.12.5 daily per-user news cache.

Revision ID: 0009_v1_12_news_cache
Revises: 0008_v1_12_delivery
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_v1_12_news_cache"
down_revision = "0008_v1_12_delivery"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "user_news_cache" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "user_news_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=False),
        sa.Column("cache_kind", sa.String(length=24), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("market_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.String(length=24), nullable=False, server_default="automatic"),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_email", "cache_kind", "cache_key", "market_date",
            name="uq_user_news_cache_daily",
        ),
    )
    op.create_index("ix_user_news_cache_owner_email", "user_news_cache", ["owner_email"], unique=False)
    op.create_index("ix_user_news_cache_market_date", "user_news_cache", ["market_date"], unique=False)
    op.create_index("ix_user_news_cache_owner_date", "user_news_cache", ["owner_email", "market_date"], unique=False)


def downgrade():
    bind = op.get_bind()
    if "user_news_cache" in set(sa.inspect(bind).get_table_names()):
        op.drop_table("user_news_cache")

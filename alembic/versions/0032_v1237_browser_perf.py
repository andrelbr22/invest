"""V1.23.7 R1 hourly real-browser performance summaries.

Revision ID: 0032_v1237_browser_perf
Revises: 0031_v123_latest_snapshot_idx
"""

from alembic import op
import sqlalchemy as sa


revision = "0032_v1237_browser_perf"
down_revision = "0031_v123_latest_snapshot_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The historical 0001 migration creates the current SQLAlchemy metadata on
    # a brand-new database.  Keep fresh installs idempotent while still adding
    # the table normally to every existing production/staging database.
    if "client_performance_hourly" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "client_performance_hourly",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bucket_hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("panel", sa.String(length=32), nullable=False),
        sa.Column("cache_state", sa.String(length=16), nullable=False),
        sa.Column("device_class", sa.String(length=16), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_ms", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("max_duration_ms", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("histogram_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("web_vitals_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket_hour", "panel", "cache_state", "device_class",
            name="uq_client_performance_hour_panel_context",
        ),
    )
    op.create_index("ix_client_performance_hourly_bucket", "client_performance_hourly", ["bucket_hour"])
    op.create_index("ix_client_performance_hourly_panel", "client_performance_hourly", ["panel", "bucket_hour"])


def downgrade() -> None:
    op.drop_index("ix_client_performance_hourly_panel", table_name="client_performance_hourly")
    op.drop_index("ix_client_performance_hourly_bucket", table_name="client_performance_hourly")
    op.drop_table("client_performance_hourly")

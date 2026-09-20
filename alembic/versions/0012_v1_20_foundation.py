"""V1.20 asynchronous work queue and economic snapshot foundation.

Revision ID: 0012_v1_20_foundation
Revises: 0011_v1_17_backtest_limits
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_v1_20_foundation"
down_revision = "0011_v1_17_backtest_limits"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "background_jobs" not in tables:
        op.create_table(
            "background_jobs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("job_type", sa.String(64), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("requested_by", sa.String(320)),
            sa.Column("deduplication_key", sa.String(160)),
            sa.Column("idempotency_key", sa.String(160)),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
            sa.Column("locked_by", sa.String(160)),
            sa.Column("locked_at", sa.DateTime(timezone=True)),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
            sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("message", sa.String(500)),
            sa.Column("last_error_code", sa.String(120)),
            sa.Column("last_error_message", sa.String(500)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("idempotency_key", name="uq_background_jobs_idempotency"),
        )
        op.create_index("ix_background_jobs_job_type", "background_jobs", ["job_type"])
        op.create_index("ix_background_jobs_status", "background_jobs", ["status"])
        op.create_index("ix_background_jobs_requested_by", "background_jobs", ["requested_by"])
        op.create_index("ix_background_jobs_deduplication_key", "background_jobs", ["deduplication_key"])
        op.create_index("ix_background_jobs_ready", "background_jobs", ["status", "run_after", "priority", "created_at"])
        op.create_index("ix_background_jobs_lease", "background_jobs", ["status", "heartbeat_at"])
        op.create_index(
            "uq_background_jobs_active_deduplication",
            "background_jobs",
            ["deduplication_key"],
            unique=True,
            postgresql_where=sa.text("deduplication_key IS NOT NULL AND status IN ('queued', 'running')"),
            sqlite_where=sa.text("deduplication_key IS NOT NULL AND status IN ('queued', 'running')"),
        )
        op.create_index("ix_background_jobs_requester", "background_jobs", ["requested_by", "created_at"])

    if "shared_snapshots" not in tables:
        op.create_table(
            "shared_snapshots",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("snapshot_key", sa.String(160), nullable=False),
            sa.Column("snapshot_kind", sa.String(64), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="valid"),
            sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("source", sa.String(120)),
            sa.Column("source_url", sa.String(500)),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("valid_until", sa.DateTime(timezone=True)),
            sa.Column("payload_hash", sa.String(64)),
            sa.Column("last_error_code", sa.String(120)),
            sa.Column("last_error_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("snapshot_key", name="uq_shared_snapshots_key"),
        )
        op.create_index("ix_shared_snapshots_snapshot_kind", "shared_snapshots", ["snapshot_kind"])
        op.create_index("ix_shared_snapshots_kind_asof", "shared_snapshots", ["snapshot_kind", "as_of"])
        op.create_index("ix_shared_snapshots_expiry", "shared_snapshots", ["valid_until"])

    if "economic_series" not in tables:
        op.create_table(
            "economic_series",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("code", sa.String(80), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("unit", sa.String(40), nullable=False),
            sa.Column("frequency", sa.String(24), nullable=False),
            sa.Column("source", sa.String(120), nullable=False),
            sa.Column("source_url", sa.String(500)),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Sao_Paulo"),
            sa.Column("accumulation_method", sa.String(40), nullable=False, server_default="level"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("code", name="uq_economic_series_code"),
        )
    if "economic_series_points" not in tables:
        op.create_table(
            "economic_series_points",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("series_id", sa.Uuid(), sa.ForeignKey("economic_series.id", ondelete="CASCADE"), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reference_period", sa.String(32), nullable=False, server_default=""),
            sa.Column("value", sa.Numeric(28, 10), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("source_payload_hash", sa.String(64)),
            sa.Column("quality_status", sa.String(24), nullable=False, server_default="valid"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "series_id", "observed_at", "reference_period",
                name="uq_economic_series_point_reference",
            ),
        )
        op.create_index("ix_economic_series_points_series_id", "economic_series_points", ["series_id"])
        op.create_index("ix_economic_series_points_observed", "economic_series_points", ["series_id", "observed_at"])
        op.create_index("ix_economic_series_points_published", "economic_series_points", ["series_id", "published_at"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table in ("economic_series_points", "economic_series", "shared_snapshots", "background_jobs"):
        if table in tables:
            op.drop_table(table)

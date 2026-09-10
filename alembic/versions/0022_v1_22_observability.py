"""V1.22 distributed coordination and operational observability.

Revision ID: 0022_v1_22_observability
Revises: 0021_v1_21_access_levels
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_v1_22_observability"
down_revision = "0021_v1_21_access_levels"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    tables = _tables()
    if "runtime_leases" not in tables:
        op.create_table(
            "runtime_leases",
            sa.Column("lease_name", sa.String(length=80), nullable=False),
            sa.Column("holder_id", sa.String(length=160), nullable=False),
            sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("lease_name"),
        )
        op.create_index("ix_runtime_leases_expires", "runtime_leases", ["expires_at"])
    if "service_heartbeats" not in tables:
        op.create_table(
            "service_heartbeats",
            sa.Column("service_id", sa.String(length=160), nullable=False),
            sa.Column("node_id", sa.String(length=120), nullable=False),
            sa.Column("role", sa.String(length=40), nullable=False),
            sa.Column("environment", sa.String(length=40), nullable=False),
            sa.Column("version", sa.String(length=32), nullable=False),
            sa.Column("commit_sha", sa.String(length=64)),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("scheduler_leader", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("alert_monitor_leader", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("metrics_json", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("service_id"),
        )
        op.create_index("ix_service_heartbeats_role_seen", "service_heartbeats", ["role", "last_seen_at"])
        op.create_index("ix_service_heartbeats_node", "service_heartbeats", ["node_id"])
    if "operational_incidents" not in tables:
        op.create_table(
            "operational_incidents",
            sa.Column("code", sa.String(length=160), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("message", sa.String(length=500), nullable=False),
            sa.Column("details_json", sa.JSON(), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("last_notified_at", sa.DateTime(timezone=True)),
            sa.PrimaryKeyConstraint("code"),
        )
        op.create_index(
            "ix_operational_incidents_status_severity",
            "operational_incidents", ["status", "severity"],
        )


def downgrade():
    tables = _tables()
    if "operational_incidents" in tables:
        op.drop_index("ix_operational_incidents_status_severity", table_name="operational_incidents")
        op.drop_table("operational_incidents")
    if "service_heartbeats" in tables:
        op.drop_index("ix_service_heartbeats_node", table_name="service_heartbeats")
        op.drop_index("ix_service_heartbeats_role_seen", table_name="service_heartbeats")
        op.drop_table("service_heartbeats")
    if "runtime_leases" in tables:
        op.drop_index("ix_runtime_leases_expires", table_name="runtime_leases")
        op.drop_table("runtime_leases")

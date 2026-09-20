"""V1.12.0 secure and idempotent official backtest delivery.

Revision ID: 0008_v1_12_delivery
Revises: 0007_v1_11_research
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_v1_12_delivery"
down_revision = "0007_v1_11_research"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "backtest_batch_jobs" not in tables or "backtest_batch_deliveries" in tables:
        return
    op.create_table(
        "backtest_batch_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_job_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="received"),
        sa.Column("completed_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_job_id"], ["backtest_batch_jobs.id"],
            name="fk_backtest_batch_deliveries_job", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_job_id", "ticker", name="uq_backtest_batch_delivery_asset"),
    )
    op.create_index(
        "ix_backtest_batch_deliveries_batch_job_id",
        "backtest_batch_deliveries", ["batch_job_id"], unique=False,
    )
    op.create_index(
        "ix_backtest_batch_deliveries_job_received",
        "backtest_batch_deliveries", ["batch_job_id", "received_at"], unique=False,
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "backtest_batch_deliveries" in set(inspector.get_table_names()):
        op.drop_table("backtest_batch_deliveries")

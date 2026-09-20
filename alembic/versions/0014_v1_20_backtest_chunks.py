"""Add retry-safe chunks for official backtest delivery.

Revision ID: 0014_v1_20_backtest_chunks
Revises: 0013_v1_20_backtest_study
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_v1_20_backtest_chunks"
down_revision = "0013_v1_20_backtest_study"
branch_labels = None
depends_on = None


TABLE_NAME = "backtest_batch_chunks"


def upgrade():
    bind = op.get_bind()
    if TABLE_NAME in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "batch_job_id", sa.Uuid(),
            sa.ForeignKey("backtest_batch_jobs.id", name="fk_backtest_batch_chunks_job", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("completed_runs", sa.Integer(), nullable=False),
        sa.Column("failed_runs", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("batch_job_id", "ticker", "chunk_index", name="uq_backtest_batch_chunk_position"),
    )
    op.create_index("ix_backtest_batch_chunks_batch_job_id", TABLE_NAME, ["batch_job_id"])
    op.create_index("ix_backtest_batch_chunks_job_asset", TABLE_NAME, ["batch_job_id", "ticker", "chunk_index"])


def downgrade():
    if TABLE_NAME in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE_NAME)

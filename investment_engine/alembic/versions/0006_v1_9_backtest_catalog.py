"""V1.9.0 private backtest history and official weekly catalog.

Revision ID: 0006_v1_9_backtests
Revises: 0005_v1_7_multiuser
"""
import os
from datetime import date

from alembic import op
import sqlalchemy as sa


revision = "0006_v1_9_backtests"
down_revision = "0005_v1_7_multiuser"
branch_labels = None
depends_on = None


def _owner(bind) -> str:
    try:
        value = bind.execute(sa.text(
            "SELECT email FROM user_access_policies WHERE role = 'owner' ORDER BY created_at LIMIT 1"
        )).scalar()
        if value:
            return str(value).strip().lower()
    except Exception:
        pass
    configured = os.getenv("APP_OWNER_EMAILS") or os.getenv("APP_ALLOWED_EMAILS") or ""
    return next((item.strip().lower() for item in configured.split(",") if item.strip()), "local-owner@localhost")


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "user_access_policies" in tables:
        columns = {column["name"] for column in inspector.get_columns("user_access_policies")}
        if "can_refresh_backtest_signals" not in columns:
            op.add_column("user_access_policies", sa.Column(
                "can_refresh_backtest_signals", sa.Boolean(), nullable=False, server_default=sa.false()
            ))

    if "backtest_batch_jobs" not in tables:
        op.create_table(
            "backtest_batch_jobs",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("requested_by", sa.String(320), nullable=False),
            sa.Column("source", sa.String(24), nullable=False, server_default="manual"),
            sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
            sa.Column("requested_tickers_json", sa.JSON(), nullable=False),
            sa.Column("grid_version", sa.String(24), nullable=False, server_default="1.0"),
            sa.Column("max_combinations", sa.Integer(), nullable=False, server_default="200"),
            sa.Column("total_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completed_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_json", sa.JSON(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_backtest_batch_jobs_requested_by", "backtest_batch_jobs", ["requested_by"])
        op.create_index("ix_backtest_batch_jobs_status", "backtest_batch_jobs", ["status"])
        op.create_index("ix_backtest_batch_jobs_created", "backtest_batch_jobs", ["created_at"])

    inspector = sa.inspect(bind)
    if "backtest_runs" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("backtest_runs")}
    additions = [
        ("owner_email", sa.Column("owner_email", sa.String(320), nullable=True)),
        ("scope", sa.Column("scope", sa.String(24), nullable=False, server_default="personal")),
        ("config_hash", sa.Column("config_hash", sa.String(64), nullable=False, server_default="")),
        ("market_date", sa.Column("market_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE"))),
        ("engine_version", sa.Column("engine_version", sa.String(24), nullable=False, server_default="legacy")),
        ("result_json", sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))),
        ("ranking_score", sa.Column("ranking_score", sa.Numeric(10, 4))),
        ("sample_status", sa.Column("sample_status", sa.String(24), nullable=False, server_default="insufficient")),
        ("current_signal", sa.Column("current_signal", sa.String(16), nullable=False, server_default="neutral")),
        ("signal_as_of", sa.Column("signal_as_of", sa.DateTime(timezone=True))),
        ("sector_label", sa.Column("sector_label", sa.String(160))),
        ("batch_job_id", sa.Column("batch_job_id", sa.Uuid(), sa.ForeignKey(
            "backtest_batch_jobs.id", name="fk_backtest_runs_batch_job", ondelete="SET NULL"
        ))),
    ]
    with op.batch_alter_table("backtest_runs") as batch:
        for name, column in additions:
            if name not in columns:
                batch.add_column(column)

    bind.execute(sa.text(
        "UPDATE backtest_runs SET owner_email = :owner WHERE owner_email IS NULL OR owner_email = ''"
    ), {"owner": _owner(bind)})
    bind.execute(sa.text(
        "UPDATE backtest_runs SET config_hash = :prefix || CAST(id AS VARCHAR) WHERE config_hash IS NULL OR config_hash = ''"
    ), {"prefix": "legacy-"})
    with op.batch_alter_table("backtest_runs") as batch:
        batch.alter_column("owner_email", existing_type=sa.String(320), nullable=False)

    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("backtest_runs")}
    for name, fields in (
        ("ix_backtest_runs_owner_email", ["owner_email"]),
        ("ix_backtest_runs_config_hash", ["config_hash"]),
        ("ix_backtest_runs_market_date", ["market_date"]),
        ("ix_backtest_runs_ranking_score", ["ranking_score"]),
        ("ix_backtest_runs_signal_as_of", ["signal_as_of"]),
        ("ix_backtest_runs_sector_label", ["sector_label"]),
        ("ix_backtest_runs_batch_job_id", ["batch_job_id"]),
        ("ix_backtest_runs_owner_created", ["owner_email", "created_at"]),
        ("ix_backtest_runs_daily_cache", ["owner_email", "config_hash", "market_date", "scope"]),
        ("ix_backtest_runs_official_rank", ["scope", "asset_id", "ranking_score"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "backtest_runs", fields)


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "backtest_runs" in tables:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("backtest_runs")}
        with op.batch_alter_table("backtest_runs") as batch:
            for name in (
                "batch_job_id", "sector_label", "signal_as_of", "current_signal", "sample_status",
                "ranking_score", "result_json", "engine_version", "market_date", "config_hash", "scope", "owner_email",
            ):
                if name in columns:
                    batch.drop_column(name)
    if "backtest_batch_jobs" in tables:
        op.drop_table("backtest_batch_jobs")
    if "user_access_policies" in tables:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("user_access_policies")}
        if "can_refresh_backtest_signals" in columns:
            op.drop_column("user_access_policies", "can_refresh_backtest_signals")

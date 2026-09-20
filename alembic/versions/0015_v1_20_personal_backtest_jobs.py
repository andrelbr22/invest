"""Asynchronous personal backtests, combination limits and cooldown.

Revision ID: 0015_v1_20_personal_backtests
Revises: 0014_v1_20_backtest_chunks
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_v1_20_personal_backtests"
down_revision = "0014_v1_20_backtest_chunks"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    access_columns = _columns("user_access_policies")
    if "backtest_strategy_limit" not in access_columns:
        op.add_column(
            "user_access_policies",
            sa.Column("backtest_strategy_limit", sa.Integer(), nullable=False, server_default="0"),
        )
    if "backtest_cooldown_seconds" not in access_columns:
        op.add_column(
            "user_access_policies",
            sa.Column("backtest_cooldown_seconds", sa.Integer(), nullable=False, server_default="60"),
        )

    usage_columns = _columns("backtest_request_usage")
    additions = (
        ("background_job_id", sa.Uuid(), True, None),
        ("execution_mode", sa.String(24), False, "compare"),
        ("combination_rule", sa.String(24), True, None),
        ("configuration_json", sa.JSON(), False, "{}"),
        ("error_json", sa.JSON(), False, "[]"),
        ("updated_at", sa.DateTime(timezone=True), False, sa.func.now()),
    )
    for name, column_type, nullable, default in additions:
        if name not in usage_columns:
            op.add_column(
                "backtest_request_usage",
                sa.Column(name, column_type, nullable=nullable, server_default=default),
            )
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("backtest_request_usage")
    background_job_fk_exists = any(
        set(item.get("constrained_columns") or []) == {"background_job_id"}
        and item.get("referred_table") == "background_jobs"
        for item in foreign_keys
    )
    if not background_job_fk_exists:
        op.create_foreign_key(
            "fk_backtest_request_usage_background_job",
            "backtest_request_usage", "background_jobs",
            ["background_job_id"], ["id"], ondelete="SET NULL",
        )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("backtest_request_usage")}
    if "ix_backtest_request_usage_background_job_id" not in indexes:
        op.create_index(
            "ix_backtest_request_usage_background_job_id",
            "backtest_request_usage", ["background_job_id"],
        )


def downgrade():
    columns = _columns("backtest_request_usage")
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("backtest_request_usage")}
    if "ix_backtest_request_usage_background_job_id" in indexes:
        op.drop_index("ix_backtest_request_usage_background_job_id", table_name="backtest_request_usage")
    foreign_keys = {item.get("name") for item in sa.inspect(op.get_bind()).get_foreign_keys("backtest_request_usage")}
    if "fk_backtest_request_usage_background_job" in foreign_keys:
        op.drop_constraint("fk_backtest_request_usage_background_job", "backtest_request_usage", type_="foreignkey")
    for name in ("updated_at", "error_json", "configuration_json", "combination_rule", "execution_mode", "background_job_id"):
        if name in columns:
            op.drop_column("backtest_request_usage", name)
    access_columns = _columns("user_access_policies")
    for name in ("backtest_cooldown_seconds", "backtest_strategy_limit"):
        if name in access_columns:
            op.drop_column("user_access_policies", name)

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import sleep

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


KEY_NAVIGATION_TABLES = {
    "assets",
    "asset_current_metrics",
    "fundamental_snapshots",
    "technical_snapshots",
    "score_snapshots",
    "valuation_snapshots",
    "price_bars",
    "backtest_runs",
}


def _pool_snapshot(session) -> dict:
    """Return bounded SQLAlchemy pool usage without opening another connection."""
    bind = session.get_bind()
    pool = getattr(bind, "pool", None)
    result = {"implementation": type(pool).__name__ if pool is not None else None}
    for key, method_name in (
        ("capacity", "size"),
        ("available", "checkedin"),
        ("in_use", "checkedout"),
        ("overflow", "overflow"),
    ):
        method = getattr(pool, method_name, None)
        try:
            result[key] = int(method()) if callable(method) else None
        except (AttributeError, NotImplementedError, TypeError, ValueError):
            result[key] = None
    capacity = result.get("capacity")
    in_use = result.get("in_use")
    result["used_pct"] = (
        round(in_use * 100 / capacity, 2)
        if isinstance(capacity, int) and capacity > 0 and isinstance(in_use, int)
        else None
    )
    return result


def _cpu_values() -> tuple[int, int] | None:
    try:
        values = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    except (OSError, ValueError, IndexError):
        return None
    if len(values) < 5:
        return None
    return sum(values), values[4]


def sample_io_wait(*, seconds: float = 0.25) -> dict:
    """Sample host-visible CPU I/O wait and the container cgroup I/O counters."""
    before = _cpu_values()
    sleep(max(0.05, min(float(seconds), 2.0)))
    after = _cpu_values()
    wait_pct = None
    if before and after:
        total_delta = after[0] - before[0]
        wait_delta = after[1] - before[1]
        if total_delta > 0:
            wait_pct = round(max(0, wait_delta) * 100 / total_delta, 3)

    counters = {"read_bytes": 0, "write_bytes": 0, "read_operations": 0, "write_operations": 0}
    try:
        for line in Path("/sys/fs/cgroup/io.stat").read_text(encoding="utf-8").splitlines():
            for item in line.split()[1:]:
                key, raw = item.split("=", 1)
                if key == "rbytes":
                    counters["read_bytes"] += int(raw)
                elif key == "wbytes":
                    counters["write_bytes"] += int(raw)
                elif key == "rios":
                    counters["read_operations"] += int(raw)
                elif key == "wios":
                    counters["write_operations"] += int(raw)
    except (OSError, ValueError):
        counters = {key: None for key in counters}
    return {"cpu_iowait_pct": wait_pct, "cgroup": counters}


def collect_database_performance(session, *, include_statements: bool = True) -> dict:
    """Collect a read-only PostgreSQL baseline used before any tuning change.

    The queries rely only on PostgreSQL statistics views.  They neither reset
    counters nor create extensions, indexes or configuration changes.
    """
    bind = session.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    payload = {
        "supported": dialect == "postgresql",
        "collected_at": datetime.now(timezone.utc),
        "pool": _pool_snapshot(session),
        "database": {},
        "sessions": [],
        "io": {},
        "tables": [],
        "indexes": [],
        "index_candidates": [],
        "statements": [],
        "warnings": [],
    }
    if dialect != "postgresql":
        payload["warnings"].append("database_performance_requires_postgresql")
        return payload

    try:
        with session.begin_nested():
            row = session.execute(text("""
                SELECT datname, pg_database_size(datname) AS size_bytes, numbackends,
                       xact_commit, xact_rollback, blks_read, blks_hit,
                       tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
                       temp_files, temp_bytes, deadlocks, stats_reset
                FROM pg_stat_database
                WHERE datname = current_database()
            """)).mappings().one()
        blocks = int(row["blks_read"] or 0) + int(row["blks_hit"] or 0)
        payload["database"] = {
            **{key: row[key] for key in (
                "datname", "size_bytes", "numbackends", "xact_commit", "xact_rollback",
                "blks_read", "blks_hit", "tup_returned", "tup_fetched", "tup_inserted",
                "tup_updated", "tup_deleted", "temp_files", "temp_bytes", "deadlocks",
                "stats_reset",
            )},
            "cache_hit_pct": round(int(row["blks_hit"] or 0) * 100 / blocks, 3) if blocks else None,
        }
    except SQLAlchemyError as exc:
        payload["warnings"].append(f"database_stats_unavailable:{type(exc).__name__}")

    try:
        with session.begin_nested():
            payload["sessions"] = [dict(row) for row in session.execute(text("""
                SELECT COALESCE(state, 'unknown') AS state,
                       COALESCE(wait_event_type, 'CPU') AS wait_event_type,
                       COALESCE(wait_event, 'executing') AS wait_event,
                       COUNT(*) AS connections,
                       MAX(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - query_start)))
                         FILTER (WHERE state = 'active') AS longest_active_seconds
                FROM pg_stat_activity
                WHERE datname = current_database()
                GROUP BY state, wait_event_type, wait_event
                ORDER BY connections DESC, state, wait_event_type
            """)).mappings()]
    except SQLAlchemyError as exc:
        payload["warnings"].append(f"session_stats_unavailable:{type(exc).__name__}")

    try:
        with session.begin_nested():
            io_row = session.execute(text("""
                SELECT COALESCE(SUM(heap_blks_read), 0) AS heap_blks_read,
                       COALESCE(SUM(heap_blks_hit), 0) AS heap_blks_hit,
                       COALESCE(SUM(idx_blks_read), 0) AS index_blks_read,
                       COALESCE(SUM(idx_blks_hit), 0) AS index_blks_hit,
                       COALESCE(SUM(toast_blks_read), 0) AS toast_blks_read,
                       COALESCE(SUM(toast_blks_hit), 0) AS toast_blks_hit
                FROM pg_statio_user_tables
            """)).mappings().one()
        io_blocks = int(io_row["heap_blks_read"] or 0) + int(io_row["heap_blks_hit"] or 0)
        index_blocks = int(io_row["index_blks_read"] or 0) + int(io_row["index_blks_hit"] or 0)
        payload["io"] = {
            **dict(io_row),
            "heap_cache_hit_pct": round(int(io_row["heap_blks_hit"] or 0) * 100 / io_blocks, 3) if io_blocks else None,
            "index_cache_hit_pct": round(int(io_row["index_blks_hit"] or 0) * 100 / index_blocks, 3) if index_blocks else None,
        }
    except SQLAlchemyError as exc:
        payload["warnings"].append(f"io_stats_unavailable:{type(exc).__name__}")

    try:
        with session.begin_nested():
            table_rows = session.execute(text("""
                SELECT relname AS table_name, n_live_tup, n_dead_tup,
                       seq_scan, seq_tup_read, idx_scan, idx_tup_fetch,
                       pg_total_relation_size(relid) AS total_bytes,
                       last_analyze, last_autoanalyze, last_vacuum, last_autovacuum
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(relid) DESC, relname
                LIMIT 30
            """)).mappings().all()
        payload["tables"] = [dict(row) for row in table_rows]
        payload["index_candidates"] = [
            {
                "table_name": row["table_name"],
                "n_live_tup": int(row["n_live_tup"] or 0),
                "seq_scan": int(row["seq_scan"] or 0),
                "idx_scan": int(row["idx_scan"] or 0),
                "reason": "sequential_scans_dominate",
            }
            for row in table_rows
            if row["table_name"] in KEY_NAVIGATION_TABLES
            and int(row["n_live_tup"] or 0) >= 1_000
            and int(row["seq_scan"] or 0) > max(20, int(row["idx_scan"] or 0) * 2)
        ]
    except SQLAlchemyError as exc:
        payload["warnings"].append(f"table_stats_unavailable:{type(exc).__name__}")

    try:
        with session.begin_nested():
            payload["indexes"] = [dict(row) for row in session.execute(text("""
                SELECT relname AS table_name, indexrelname AS index_name, idx_scan,
                       idx_tup_read, idx_tup_fetch,
                       pg_relation_size(indexrelid) AS size_bytes
                FROM pg_stat_user_indexes
                WHERE relname IN (
                    'assets', 'asset_current_metrics', 'fundamental_snapshots',
                    'technical_snapshots', 'score_snapshots', 'valuation_snapshots',
                    'price_bars', 'backtest_runs'
                )
                ORDER BY pg_relation_size(indexrelid) DESC, relname, indexrelname
                LIMIT 60
            """)).mappings()]
    except SQLAlchemyError as exc:
        payload["warnings"].append(f"index_stats_unavailable:{type(exc).__name__}")

    if include_statements:
        try:
            with session.begin_nested():
                available = bool(session.scalar(text(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_stat_statements')"
                )))
                if available:
                    payload["statements"] = [dict(row) for row in session.execute(text("""
                        SELECT queryid::text AS query_id, calls,
                               ROUND(total_exec_time::numeric, 2) AS total_exec_ms,
                               ROUND(mean_exec_time::numeric, 2) AS mean_exec_ms,
                               ROUND(max_exec_time::numeric, 2) AS max_exec_ms,
                               rows,
                               LEFT(REGEXP_REPLACE(query, '\\s+', ' ', 'g'), 240) AS query
                        FROM pg_stat_statements
                        WHERE dbid = (SELECT oid FROM pg_database WHERE datname=current_database())
                        ORDER BY total_exec_time DESC
                        LIMIT 20
                    """)).mappings()]
                else:
                    payload["warnings"].append("pg_stat_statements_not_enabled")
        except SQLAlchemyError as exc:
            payload["warnings"].append(f"statement_stats_unavailable:{type(exc).__name__}")
    return payload


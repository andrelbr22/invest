#!/usr/bin/env python3
"""Apply or verify Alembic migrations as an explicit deployment step.

The API and worker only run the ``verify`` operation during startup.  Schema
changes are applied by the release scripts through the ``upgrade`` operation,
before a new application container replaces the healthy one.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import time
from typing import Iterator

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from investment_engine.infrastructure.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Cluster-wide and stable.  Serializing production and staging migrations is
# intentional: both databases live in the same small PostgreSQL instance.
MIGRATION_LOCK_KEY = int.from_bytes(b"FDIMIGR", "big", signed=False)


def _database_url() -> str:
    return os.getenv("DATABASE_ADMIN_URL", "").strip() or settings.database_url


def _alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", _database_url().replace("%", "%%"))
    return config


def _expected_heads(config: Config) -> tuple[str, ...]:
    heads = tuple(sorted(ScriptDirectory.from_config(config).get_heads()))
    if len(heads) != 1:
        raise RuntimeError(f"Esperada uma única revisão de destino; encontradas: {heads!r}")
    return heads


def _current_heads(connection: Connection) -> tuple[str, ...]:
    return tuple(sorted(MigrationContext.configure(connection).get_current_heads()))


@contextmanager
def _migration_lock(engine: Engine, timeout_seconds: int) -> Iterator[Connection]:
    with engine.connect() as raw_connection:
        if raw_connection.dialect.name != "postgresql":
            yield raw_connection
            return

        # The advisory lock is session-scoped, so it does not need a database
        # transaction.  Keeping the coordinator SELECT inside an open
        # transaction creates an old snapshot which CREATE INDEX CONCURRENTLY
        # must wait for, causing a self-inflicted lock timeout.  AUTOCOMMIT
        # preserves the session lock while leaving no transaction snapshot
        # behind during Alembic's separate migration connection.
        connection = raw_connection.execution_options(
            isolation_level="AUTOCOMMIT",
        )

        deadline = time.monotonic() + max(1, timeout_seconds)
        acquired = False
        while time.monotonic() < deadline:
            acquired = bool(connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": MIGRATION_LOCK_KEY},
            ))
            if acquired:
                break
            time.sleep(1)
        if not acquired:
            raise TimeoutError("Outra migração continua em andamento; nenhuma alteração foi aplicada.")
        try:
            yield connection
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": MIGRATION_LOCK_KEY},
            )


def _verify(connection: Connection, expected: tuple[str, ...]) -> None:
    current = _current_heads(connection)
    if current != expected:
        raise RuntimeError(
            "Banco fora da revisão exigida pela aplicação: "
            f"atual={current or ('sem revisão',)!r}; esperada={expected!r}."
        )


def run(operation: str, *, timeout_seconds: int = 300) -> tuple[str, ...]:
    config = _alembic_config()
    expected = _expected_heads(config)
    engine = create_engine(_database_url(), poolclass=NullPool, pool_pre_ping=True)
    try:
        with _migration_lock(engine, timeout_seconds) as lock_connection:
            if operation == "upgrade":
                # Alembic opens its own transaction/connection while this
                # session keeps the advisory lock for the whole operation.
                command.upgrade(config, "head")
            _verify(lock_connection, expected)
    finally:
        engine.dispose()
    return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("upgrade", "verify"))
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    heads = run(args.operation, timeout_seconds=args.timeout_seconds)
    verb = "aplicada e verificada" if args.operation == "upgrade" else "verificada"
    print(f"Migração {verb}: {','.join(heads)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

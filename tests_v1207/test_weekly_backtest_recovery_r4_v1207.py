from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect

from investment_engine.infrastructure.db import models  # noqa: F401
from investment_engine.infrastructure.db.base import Base
from scripts import run_weekly_backtests


ROOT = Path(__file__).resolve().parents[1]


def _load_migration(filename: str):
    path = ROOT / "alembic" / "versions" / filename
    spec = spec_from_file_location(f"migration_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recent_migrations_are_safe_when_initial_schema_is_already_current(monkeypatch):
    """Regression for weekly run #21, which failed on a duplicate DB object."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    def unexpected_mutation(*_args, **_kwargs):
        pytest.fail("A migração tentou recriar um objeto que já existe.")

    with engine.connect() as connection:
        for filename in (
            "0015_v1_20_personal_backtest_jobs.py",
            "0017_v1_20_personal_finances.py",
            "0018_v1_20_interest_curve_history.py",
            "0019_v1_20_access_and_allocation.py",
        ):
            migration = _load_migration(filename)
            monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
            for operation in ("add_column", "create_table", "create_index", "create_foreign_key"):
                monkeypatch.setattr(migration.op, operation, unexpected_mutation)
            migration.upgrade()


def test_weekly_worker_builds_only_the_explicit_local_disposable_database(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(
        "sqlalchemy.engine.make_url",
        lambda _value: SimpleNamespace(host="127.0.0.1", database="backtests_ci"),
    )
    monkeypatch.setattr(
        "investment_engine.infrastructure.db.session.make_engine",
        lambda _value: engine,
    )

    prepared = run_weekly_backtests.prepare_calculation_database(
        "postgresql+psycopg://temporary@127.0.0.1/backtests_ci",
        {"BACKTEST_EPHEMERAL_DATABASE": "true"},
    )

    assert prepared is engine
    assert "backtest_runs" in inspect(engine).get_table_names()
    assert "finance_transactions" in inspect(engine).get_table_names()


@pytest.mark.parametrize(
    "url,environment",
    (
        (
            "postgresql+psycopg://temporary@127.0.0.1/backtests_ci",
            {},
        ),
        (
            "postgresql+psycopg://temporary@database.example/production",
            {"BACKTEST_EPHEMERAL_DATABASE": "true"},
        ),
    ),
)
def test_weekly_worker_refuses_unconfirmed_or_nonlocal_database(url, environment):
    with pytest.raises(SystemExit):
        run_weekly_backtests.prepare_calculation_database(url, environment)


def test_workflows_validate_current_tests_postgres_and_supported_actions():
    backtests = (ROOT / ".github" / "workflows" / "backtests-semanais.yml").read_text(encoding="utf-8")
    tests = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")

    assert 'BACKTEST_EPHEMERAL_DATABASE: "true"' in backtests
    assert "actions/checkout@v5" in backtests and "actions/setup-python@v6" in backtests
    assert "migrations-postgres:" in tests
    assert "alembic upgrade head" in tests
    assert "tests_v1207" in tests


def test_panel_explains_the_correct_recovery_action_and_destination():
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert "Reprocessar ativos pendentes ou com falha" in script
    assert 'result.dispatch?.environment==="production"' in script
    assert "prepare_temporary_database" in script

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _runner_module():
    path = ROOT / "deployment/run-migrations.py"
    spec = spec_from_file_location("run_migrations_r2c", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Connection:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.execution_options_calls = []
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def execution_options(self, **options):
        self.execution_options_calls.append(options)
        return self

    def scalar(self, statement, parameters):
        self.statements.append((str(statement), parameters))
        return True

    def execute(self, statement, parameters):
        self.statements.append((str(statement), parameters))


class _Engine:
    def __init__(self):
        self.connection = _Connection()

    def connect(self):
        return self.connection


def test_migration_advisory_lock_uses_autocommit_without_open_snapshot():
    runner = _runner_module()
    engine = _Engine()

    with runner._migration_lock(engine, timeout_seconds=1) as connection:
        assert connection is engine.connection

    assert engine.connection.execution_options_calls == [
        {"isolation_level": "AUTOCOMMIT"},
    ]
    statements = [statement for statement, _params in engine.connection.statements]
    assert statements == [
        "SELECT pg_try_advisory_lock(:lock_key)",
        "SELECT pg_advisory_unlock(:lock_key)",
    ]


def test_r2c_documents_the_fail_closed_recovery_without_new_schema_revision():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    patch = (ROOT / "PATCH_V1236_R2C.md").read_text(encoding="utf-8")
    migration = (ROOT / "alembic/versions/0031_v1_23_latest_snapshot_indexes.py").read_text(
        encoding="utf-8",
    )

    assert "R2C" in readme
    assert "AUTOCOMMIT" in patch
    assert 'revision = "0031_v1_23_latest_snapshot_indexes"' in migration

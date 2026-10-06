import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _revision_value(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "revision" for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise AssertionError(f"revision não encontrada em {path.name}")


def test_every_alembic_revision_fits_the_historical_version_column():
    migrations = sorted((ROOT / "alembic/versions").glob("[0-9]*.py"))
    revisions = {path.name: _revision_value(path) for path in migrations}

    assert revisions
    assert {
        name: revision
        for name, revision in revisions.items()
        if len(revision) > 32
    } == {}
    assert revisions["0031_v123_latest_snapshot_idx.py"] == (
        "0031_v123_latest_snapshot_idx"
    )

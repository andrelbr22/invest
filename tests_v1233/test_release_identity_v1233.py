from pathlib import Path

from investment_engine import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_docs_ci_and_schema_are_v1234():
    assert __version__ == "1.23.4"
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8",
    )
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert 'version = "1.23.4"' in project
    assert '"tests_v1233"' in project
    assert '"tests_v1234"' in project
    assert workflow.count("tests_v1232 tests_v1233 tests_v1234") == 2
    assert '0029_v1_23_current_metrics' in workflow
    assert "V1.23.4" in publisher
    assert readme.startswith("# Formação do Investidor • V1.23.4")
    assert "Otimização estrutural V1.23.2" in readme

    for relative in (
        "V1_23_3.md",
        "PATCH_V1233.md",
        "INSTRUCOES_ORACLE_V1233.md",
        "RELATORIO_VALIDACAO_V1233.md",
    ):
        assert (ROOT / relative).is_file(), relative


def test_v1233_has_no_new_schema_migration_and_preserves_all_history():
    migrations = sorted((ROOT / "alembic" / "versions").glob("[0-9]*.py"))
    assert migrations[-1].name == "0029_v1_23_current_metrics.py"
    current_metrics = (ROOT / "investment_engine" / "core" / "current_metrics.py").read_text(
        encoding="utf-8",
    )
    assert "latest_current_sources_batch" in current_metrics
    assert "price_history" in current_metrics
    assert "delete(" not in current_metrics.lower()
    assert "truncate" not in current_metrics.lower()

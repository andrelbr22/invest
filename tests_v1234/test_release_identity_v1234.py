from pathlib import Path

from investment_engine import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_ci_assets_and_documents_are_v1234():
    assert __version__ == "1.23.6"
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    platform = (ROOT / "investment_engine/web/index.html").read_text(encoding="utf-8")

    assert 'version = "1.23.6"' in project
    assert '"tests_v1234"' in project
    assert '"tests_v1235"' in project
    assert '"tests_v1236"' in project
    assert workflow.count("tests_v1232 tests_v1233 tests_v1234 tests_v1235") == 2
    assert "0031_v123_latest_snapshot_idx" in workflow
    assert "V1.23.6 R2" in publisher
    assert readme.startswith("# Formação do Investidor • V1.23.6")
    assert "../ui-assets/app.css?v=1.23.6-r2" in platform
    assert "../ui-assets/app.js?v=1.23.6-r2" in platform

    for relative in (
        "V1_23_4.md",
        "PATCH_V1234.md",
        "INSTRUCOES_ORACLE_V1234.md",
        "RELATORIO_VALIDACAO_V1234.md",
    ):
        assert (ROOT / relative).is_file(), relative


def test_v1234_preserves_schema_head_and_historical_release_documents():
    migrations = sorted((ROOT / "alembic/versions").glob("[0-9]*.py"))
    assert migrations[-1].name == "0031_v123_latest_snapshot_idx.py"
    for relative in (
        "V1_23_3.md",
        "PATCH_V1233.md",
        "INSTRUCOES_ORACLE_V1233.md",
        "RELATORIO_VALIDACAO_V1233.md",
    ):
        assert (ROOT / relative).is_file(), relative

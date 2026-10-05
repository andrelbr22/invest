from pathlib import Path

from investment_engine import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_current_release_preserves_v1232_docs_assets_and_adds_v1233_suite():
    assert __version__ == "1.23.6"
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    platform = (ROOT / "investment_engine" / "web" / "index.html").read_text(encoding="utf-8")
    portal = (ROOT / "investment_engine" / "web" / "portal.html").read_text(encoding="utf-8")

    assert 'version = "1.23.6"' in project
    assert '"tests_v1232"' in project
    assert '"tests_v1233"' in project
    assert '"tests_v1234"' in project
    assert '"tests_v1235"' in project
    assert '"tests_v1236"' in project
    assert workflow.count("tests_v1232 tests_v1233 tests_v1234 tests_v1235") == 2
    assert '0030_v1_23_navigation_metrics' in workflow
    assert "V1.23.6 R2" in publisher
    assert "?v=1.23.6-r2" in platform
    assert "?v=1.23.2-r1" in portal
    for relative in (
        "V1_23_2.md",
        "PATCH_V1232.md",
        "INSTRUCOES_ORACLE_V1232.md",
        "RELATORIO_VALIDACAO_V1232.md",
    ):
        assert (ROOT / relative).is_file(), relative


def test_readme_preserves_v1232_history_beneath_current_release():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# Formação do Investidor • V1.23.6")
    assert "Otimização estrutural V1.23.2" in readme
    assert "V1.23.1 R2" in readme
    assert "V1.23.0" in readme

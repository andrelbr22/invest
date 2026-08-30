from pathlib import Path

from investment_engine import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_and_operational_guides_are_v1207():
    assert __version__ == "1.20.7"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    assert 'version = "1.20.7"' in pyproject
    assert "V1.20.7" in publisher
    for name in (
        "V1_20_7.md",
        "PATCH_V1207.md",
        "INSTRUCOES_ORACLE_V1207.md",
        "RELATORIO_IMPLEMENTACOES_E_PENDENCIAS_V1207.md",
        "ARQUITETURA_DUAS_INSTANCIAS_V1207.md",
    ):
        assert (ROOT / name).is_file()


def test_new_portfolio_interactions_are_accessible_and_ticker_safe():
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    api = (ROOT / "investment_engine" / "api" / "app.py").read_text(encoding="utf-8")
    for marker in (
        "portfolio-position-form",
        "Rebalanceamento",
        "custom-value-dialog",
        "unsupported_or_duplicate_ticker",
    ):
        assert marker in script or marker in api

from pathlib import Path

from investment_engine import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_is_v1221_with_performance_migration():
    assert __version__ == "1.22.1"
    assert (ROOT / "V1_22_1.md").is_file()
    assert (ROOT / "PATCH_V1221.md").is_file()
    assert (ROOT / "INSTRUCOES_ORACLE_V1221.md").is_file()
    assert (ROOT / "RELATORIO_VALIDACAO_V1221.md").is_file()
    assert (ROOT / "alembic" / "versions" / "0023_v1_22_screener_performance.py").is_file()


def test_publication_and_readme_point_to_v1221_staging_validation():
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Acelera consultas e navegação na V1.22.1 em teste" in publisher
    assert "valide a V1.22.1" in publisher
    assert readme.startswith("# Formação do Investidor • V1.22.1")
    assert "INSTRUCOES_ORACLE_V1221.md" in readme

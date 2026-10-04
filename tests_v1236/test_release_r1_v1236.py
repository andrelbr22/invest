from pathlib import Path

from investment_engine import __version__


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_release_identity_documents_and_no_new_migration():
    assert __version__ == "1.23.6"
    assert sorted((ROOT / "alembic" / "versions").glob("[0-9]*.py"))[-1].name == (
        "0030_v1_23_navigation_metrics.py"
    )
    assert read("README.md").startswith("# Formação do Investidor • V1.23.6")
    assert "tests_v1236" in read("pyproject.toml")
    assert "tests_v1236" in read(".github/workflows/tests.yml")

    for relative in (
        "V1_23_6.md",
        "PATCH_V1236_R1.md",
        "RELATORIO_VALIDACAO_V1236_R1.md",
        "INSTRUCOES_ORACLE_V1236_R1.md",
    ):
        assert (ROOT / relative).is_file(), relative


def test_release_publication_and_browser_assets_point_to_r1():
    publisher = read("PUBLICAR_GITHUB.ps1")
    platform = read("investment_engine/web/index.html")

    assert "Acelera paineis preservando fallbacks na V1.23.6 R1 em teste" in publisher
    assert "valide a V1.23.6 R1" in publisher
    assert "../ui-assets/app.css?v=1.23.6-r1" in platform
    assert "../ui-assets/app.js?v=1.23.6-r1" in platform


def test_operator_document_keeps_promotion_manual_and_separates_shells():
    instructions = read("INSTRUCOES_ORACLE_V1236_R1.md")

    assert "Windows PowerShell" in instructions
    assert "Ubuntu" in instructions
    assert "-ValidateOnly" in instructions
    assert "testefdi/ready" in instructions
    assert "--cold --extended" in instructions
    assert "Somente após" in instructions

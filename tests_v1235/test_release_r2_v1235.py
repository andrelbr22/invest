from pathlib import Path

from investment_engine import __version__


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_r2_release_identity_schema_assets_and_operator_documents():
    assert __version__ == "1.23.5"
    assert sorted((ROOT / "alembic" / "versions").glob("[0-9]*.py"))[-1].name == (
        "0030_v1_23_navigation_metrics.py"
    )

    publisher = read("PUBLICAR_GITHUB.ps1")
    workflow = read(".github/workflows/tests.yml")
    html = read("investment_engine/web/index.html")
    assert "Materializa a navegacao e isola recursos na V1.23.5 R2 em teste" in publisher
    assert "valide a V1.23.5 R2" in publisher
    assert "SEGURANCA DA PRIMEIRA MIGRACAO" not in publisher
    assert "stagingConfirmation" not in publisher
    assert "0030_v1_23_navigation_metrics" in workflow
    assert "tests_v1235" in workflow
    assert "app.css?v=1.23.5-r2" in html
    assert "app.js?v=1.23.5-r2" in html

    for relative in (
        "PATCH_V1235_R2.md",
        "RELATORIO_VALIDACAO_V1235_R2.md",
        "INSTRUCOES_ORACLE_V1235_R2.md",
        "PATCH_V1235_R1.md",
        "RELATORIO_VALIDACAO_V1235_R1.md",
        "INSTRUCOES_ORACLE_V1235_R1.md",
    ):
        assert (ROOT / relative).is_file(), relative


def test_r2_release_preserves_history_and_keeps_vm2_cutover_explicit():
    migration = read("alembic/versions/0030_v1_23_navigation_metrics.py").lower()
    instructions = read("INSTRUCOES_ORACLE_V1235_R2.md")
    assert "drop_table" not in migration
    assert "truncate" not in migration
    assert "delete(" not in migration
    assert "segunda vm" in instructions.lower()
    assert "preflight-cutover.sh" in instructions
    assert "cutover-worker.sh" in instructions
    assert "failback-worker.sh" in instructions
    assert "não cria a vm" in instructions.lower()

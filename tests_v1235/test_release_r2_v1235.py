from pathlib import Path

from investment_engine import __version__


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_r2_release_identity_schema_assets_and_operator_documents():
    assert __version__ == "1.23.7"
    assert sorted((ROOT / "alembic" / "versions").glob("[0-9]*.py"))[-1].name == (
        "0032_v1237_browser_perf.py"
    )

    publisher = read("PUBLICAR_GITHUB.ps1")
    workflow = read(".github/workflows/tests.yml")
    html = read("investment_engine/web/index.html")
    assert "Carrega os paineis sob demanda na V1.23.7 R2 em teste" in publisher
    assert "valide a V1.23.7 R2" in publisher
    assert "SEGURANCA DA PRIMEIRA MIGRACAO" not in publisher
    assert "stagingConfirmation" not in publisher
    assert "0032_v1237_browser_perf" in workflow
    assert "tests_v1235" in workflow
    assert "app.css?v=1.23.7-r2" in html
    assert "app.js?v=1.23.7-r2" in html

    for relative in (
        "PATCH_V1235_R2B.md",
        "RELATORIO_VALIDACAO_V1235_R2B.md",
        "INSTRUCOES_ORACLE_V1235_R2B.md",
        "PATCH_V1235_R2A.md",
        "RELATORIO_VALIDACAO_V1235_R2A.md",
        "INSTRUCOES_ORACLE_V1235_R2A.md",
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


def test_r2a_operator_commands_validate_cycle_and_preserve_active_log():
    instructions = read("INSTRUCOES_ORACLE_V1235_R2A.md")
    legacy_instructions = read("INSTRUCOES_ORACLE_V1235_R2.md")

    for content in (instructions, legacy_instructions):
        assert '[[ "$STAGING_COMMIT" =~ ^[0-9a-f]{40}$ ]]' in content
        assert "'release:${STAGING_COMMIT}'" in content
        assert "-v cycle=" not in content
        assert "=:'cycle'" not in content

    promotion_line = next(
        line for line in instructions.splitlines()
        if line.startswith("nohup ./deployment/promote-staging-to-production.sh")
    )
    assert '>> "$PROMOTION_LOG" 2>&1 &' in promotion_line
    assert ' > "$PROMOTION_LOG"' not in promotion_line


def test_r2a_promotion_keeps_the_exclusive_lock_and_waits_for_coordination():
    promotion = read("deployment/promote-staging-to-production.sh")
    lock = promotion.index("flock -n 9")
    project_change = promotion.index('cd "${PROJECT_DIR}"')
    assert lock < project_change
    assert "wait_exact_worker()" in promotion
    assert 'wait_exact_worker primary-worker production "${TARGET_COMMIT}" 24' in promotion

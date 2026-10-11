from __future__ import annotations

from pathlib import Path

from investment_engine import __version__
from scripts.benchmark_browser_journeys import REQUIRED_JOURNEYS, percentile


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "investment_engine" / "web" / "static"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_release_identity_assets_docs_and_schema_are_v1238_r1():
    assert __version__ == "1.23.8"
    assert read("README.md").startswith("# Formação do Investidor • V1.23.8")
    assert 'version = "1.23.8"' in read("pyproject.toml")
    assert '"tests_v1238"' in read("pyproject.toml")
    assert "tests_v1238" in read(".github/workflows/tests.yml")
    platform = read("investment_engine/web/index.html")
    for asset in ("app.css", "web-vitals.js", "app.js"):
        assert f"{asset}?v=1.23.8-r1" in platform
    for relative in (
        "V1_23_8.md",
        "PATCH_V1238_R1.md",
        "INSTRUCOES_ORACLE_V1238_R1.md",
        "RELATORIO_VALIDACAO_V1238_R1.md",
        "PATCH_V1238_R1A.md",
        "RELATORIO_VALIDACAO_V1238_R1A.md",
        "INSTRUCOES_ORACLE_V1238_R1A.md",
        "PLANO_V1238_R2.md",
    ):
        assert (ROOT / relative).is_file(), relative
    assert not list((ROOT / "alembic" / "versions").glob("0033*"))
    publisher = read("PUBLICAR_GITHUB.ps1")
    assert "Corrige a regressao dos testes da V1.23.8 R1A em teste" in publisher
    assert "valide a V1.23.8 R1A" in publisher


def test_panels_are_freshness_aware_and_do_not_revalidate_every_return():
    source = read("investment_engine/web/static/app.js")
    assert "const PANEL_FRESHNESS_MS" in source
    assert "panelFreshness: new Map()" in source
    assert "function markPanelFresh(" in source
    assert "function panelNeedsRevalidation(" in source
    assert "if(force||!warm)loadCurrentView()" in source
    assert "else if(panelNeedsRevalidation(view))" in source
    assert "if(force||!restored)loadCurrentView()" in source
    assert "else if(panelNeedsRevalidation(group,tab))" in source
    assert "invalidatePanelFreshness([...requested])" in source


def test_gets_are_coalesced_and_browser_caches_are_bounded():
    source = read("investment_engine/web/static/app.js")
    assert "const READ_CACHE_LIMIT = 192" in source
    assert "const ANALYSIS_RESULT_CACHE_LIMIT = 24" in source
    assert "function setBoundedCache(" in source
    assert 'const coalesceKey = method === "GET" && !bypassCache' in source
    assert "state.readRequests.has(coalesceKey)" in source
    assert "setBoundedCache(state.readCache" in source
    assert "setBoundedCache(state.analysisResultCache" in read(
        "investment_engine/web/static/feature-analysis.js"
    )


def test_analysis_is_a_lazy_module_and_initial_bundle_is_small():
    initial = STATIC / "app.js"
    analysis = STATIC / "feature-analysis.js"
    assert initial.stat().st_size < 130_000
    assert analysis.stat().st_size > 50_000
    assert "Indicadores fundamentalistas" not in initial.read_text(encoding="utf-8")
    assert "Indicadores fundamentalistas" in analysis.read_text(encoding="utf-8")
    source = initial.read_text(encoding="utf-8")
    assert 'analysis:`${BASE_PATH}/ui-assets/feature-analysis.js' in source
    assert 'const FEATURE_ASSET_VERSION="1.23.8-r1"' in source
    assert 'FEATURE_BY_VIEW={analysis:"analysis"' in source


def test_alert_catalog_is_small_and_searches_only_after_a_query():
    api = read("investment_engine/api/app.py")
    section = api.split('@app.get("/alerts/catalog")', 1)[1].split(
        '@app.get("/alerts")', 1
    )[0]
    portfolio = read("investment_engine/web/static/feature-portfolio.js")
    assert 'q: str = Query(default="", max_length=80)' in section
    assert "search_assets(q" in section
    assert "list_assets" not in section
    assert "if q.strip() else []" in section
    assert "/alerts/catalog?limit=1" in portfolio
    assert "/alerts/catalog?q=${encodeURIComponent(term)}&limit=12" in portfolio
    assert "alertSuggestionTimer" in portfolio


def test_runtime_cache_ttls_are_explicit_in_both_web_environments():
    compose = read("docker-compose.oracle-web.yml")
    assert compose.count('ACCESS_POLICY_CACHE_TTL_SECONDS: "60"') >= 2
    assert compose.count('ANALYSIS_PRESET_CACHE_TTL_SECONDS: "300"') >= 2
    assert compose.count('SHARED_RESPONSE_CACHE_TTL_SECONDS: "60"') >= 2
    assert compose.count('SCREENER_RESPONSE_CACHE_TTL_SECONDS: "120"') >= 2


def test_real_browser_report_uses_p95_nine_journeys_and_commit_validation():
    benchmark = read("scripts/benchmark_browser_journeys.py")
    verifier = read("scripts/verify_browser_performance_report.py")
    promotion = read("deployment/promote-staging-to-production.sh")
    assert len(REQUIRED_JOURNEYS) == 9
    assert percentile([1, 2, 3, 4, 100], 0.95) == 100
    for journey in REQUIRED_JOURNEYS:
        assert journey in benchmark
    assert '"p95_ms": p95' in benchmark
    assert 'default=5' in benchmark
    assert "expected-commit" in verifier
    assert "verify_browser_performance_report" in promotion
    assert "FDI_REQUIRE_BROWSER_PERFORMANCE_REPORT" in promotion

def test_r2_commitment_is_explicit_and_keeps_one_database():
    plan = read("PLANO_V1238_R2.md")
    assert "somente depois que a R1 estiver" in plan
    assert "segunda VM" in plan
    assert "um único banco" in plan
    assert "scheduler" in plan
    assert "retorno" in plan

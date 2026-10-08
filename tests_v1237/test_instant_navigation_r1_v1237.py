from __future__ import annotations

import inspect
from pathlib import Path

from investment_engine import __version__
from investment_engine.api.app import record_client_panel_performance
from investment_engine.core.client_performance import ClientPerformanceAggregator


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_release_identity_schema_and_assets_are_v1237_r1():
    assert __version__ == "1.23.7"
    assert read("README.md").startswith("# Formação do Investidor • V1.23.7")
    assert 'version = "1.23.7"' in read("pyproject.toml")
    assert '"tests_v1237"' in read("pyproject.toml")
    assert "tests_v1237" in read(".github/workflows/tests.yml")
    assert 'assert revision == "0032_v1237_browser_perf"' in read(
        ".github/workflows/tests.yml"
    )
    platform = read("investment_engine/web/index.html")
    assert "app.css?v=1.23.7-r1" in platform
    assert "web-vitals.js?v=1.23.7-r1" in platform
    assert "app.js?v=1.23.7-r1" in platform
    for relative in (
        "V1_23_7.md",
        "PATCH_V1237_R1.md",
        "INSTRUCOES_ORACLE_V1237_R1.md",
        "RELATORIO_VALIDACAO_V1237_R1.md",
    ):
        assert (ROOT / relative).is_file(), relative


def test_panel_surfaces_urls_and_state_are_preserved_then_revalidated():
    source = read("investment_engine/web/static/app.js")
    assert "panelSurfaceCache: new Map()" in source
    assert "function capturePanelSurface(" in source
    assert "function restorePanelSurface(" in source
    assert "viewScroll: new Map()" in source
    assert "analysisFormState: new Map()" in source
    assert "PANEL_REVALIDATE_DELAY_MS" in source
    assert "if(restored)scheduleNavigationTask(()=>loadCurrentView()" in source
    assert 'params.set("view",state.view)' in source
    assert 'params.set("type",analysisTabTypes[state.tabs.analysis]' in source
    assert 'window.addEventListener("popstate"' in source
    assert "persistNavigationState()" in source


def test_cache_invalidation_is_selective_and_keeps_unrelated_panels_warm():
    source = read("investment_engine/web/static/app.js")
    assert "CACHE_TAG_PREFIXES" in source
    assert "function invalidateApplicationCache(" in source
    assert "invalidateApplicationCache(invalidateTags)" in source
    assert "state.readCache.clear()" not in source
    assert '["portfolio"]' in source
    assert '["backtests","analysis"]' in source
    assert '["admin","session"]' in source


def test_analysis_table_has_sort_density_sticky_ticker_and_clear_states():
    javascript = read("investment_engine/web/static/app.js")
    css = read("investment_engine/web/static/app.css")
    assert "function sortedAnalysisRows(" in javascript
    assert "data-analysis-sort" in javascript
    assert "data-analysis-density" in javascript
    assert "Sem resultado oficial" in javascript
    assert "status-na" in javascript
    assert ".analysis-data-table th:first-child" in css
    assert ".analysis-data-table.density-compact" in css
    assert ".status-updated" in css
    assert "prefers-reduced-motion: reduce" in css


def test_admin_is_grouped_and_real_browser_benchmark_is_operator_ready():
    platform = read("investment_engine/web/index.html")
    app = read("investment_engine/web/static/app.js")
    benchmark = read("scripts/benchmark_browser_journeys.py")
    assert "admin-workspace" in platform
    for label in ("Usuários e acessos", "Conteúdo", "Dados", "Operação"):
        assert label in platform
    assert "Experiência real no navegador" in app
    for journey in (
        "platform_entry",
        "analysis_first_open",
        "asset_detail",
        "portfolio",
        "backtests",
        "analysis_return",
    ):
        assert journey in benchmark
    assert "playwright" in read("requirements-browser.txt")


def test_browser_metrics_are_aggregated_in_memory_not_written_per_click():
    endpoint = inspect.getsource(record_client_panel_performance)
    assert "CLIENT_PERFORMANCE.observe" in endpoint
    assert "maybe_flush_client_performance" in endpoint
    assert "db.commit" not in endpoint
    assert "Depends(get_db)" not in endpoint

    aggregator = ClientPerformanceAggregator(flush_interval_seconds=60)
    aggregator.observe(
        panel="analysis",
        duration_ms=420,
        success=True,
        cache_state="cold",
        device_class="desktop",
        web_vitals={"lcp_ms": 600, "inp_ms": 75, "cls": 0.02},
    )
    aggregator.observe(
        panel="analysis",
        duration_ms=180,
        success=False,
        cache_state="cold",
        device_class="desktop",
    )
    batch = aggregator.begin_flush()
    assert len(batch) == 1
    row = next(iter(batch.values()))
    assert row["sample_count"] == 2
    assert row["success_count"] == 1
    assert row["total_duration_ms"] == 600
    assert row["histogram"] == {"250": 1, "500": 1}


def test_browser_performance_migration_is_additive_and_keeps_previous_head():
    migration = read("alembic/versions/0032_v1237_browser_perf.py")
    assert 'revision = "0032_v1237_browser_perf"' in migration
    assert 'down_revision = "0031_v123_latest_snapshot_idx"' in migration
    assert "client_performance_hourly" in migration
    assert '"client_performance_hourly" in set(sa.inspect' in migration
    upgrade = migration.split("def upgrade", 1)[1].split("def downgrade", 1)[0].lower()
    assert "drop_table" not in upgrade
    assert "delete(" not in upgrade
    assert "truncate" not in upgrade

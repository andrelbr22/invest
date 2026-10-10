from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "investment_engine" / "web" / "static"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_initial_javascript_is_smaller_and_heavy_areas_are_separate():
    app_js = STATIC / "app.js"
    modules = {
        "analysis": STATIC / "feature-analysis.js",
        "portfolio": STATIC / "feature-portfolio.js",
        "backtests": STATIC / "feature-backtests.js",
        "finances": STATIC / "feature-finances.js",
        "admin": STATIC / "feature-admin.js",
    }
    assert app_js.stat().st_size < 130_000
    for name, path in modules.items():
        assert path.is_file(), name
        assert path.stat().st_size > 5_000, name
        source = path.read_text(encoding="utf-8")
        assert f"window.FDIFeatures.{name}" in source


def test_feature_loader_is_lazy_coalesced_retryable_and_route_aware():
    source = read("investment_engine/web/static/app.js")
    assert 'const FEATURE_ASSET_VERSION="1.23.8-r1"' in source
    assert '${BASE_PATH}/ui-assets/feature-analysis.js' in source
    assert '${BASE_PATH}/ui-assets/feature-portfolio.js' in source
    assert '${BASE_PATH}/ui-assets/feature-backtests.js' in source
    assert '${BASE_PATH}/ui-assets/feature-finances.js' in source
    assert '${BASE_PATH}/ui-assets/feature-admin.js' in source
    assert "if(featureLoads.has(name))return featureLoads.get(name)" in source
    assert "featureLoads.delete(name)" in source
    assert 'script.async=true;script.dataset.feature=name' in source
    assert 'primaryNav.addEventListener("pointerover",prefetchFromNavigation' in source
    assert 'primaryNav.addEventListener("focusin",prefetchFromNavigation)' in source


def test_heavy_templates_are_not_part_of_the_initial_bundle():
    initial = read("investment_engine/web/static/app.js")
    assert "Fila de trabalhos em segundo plano" not in initial
    assert "Links de venda — até três" not in initial
    assert "Orçamento atualizado" not in initial
    assert "Combinação das tendências" not in initial
    assert "Alocação da carteira: tipos" not in initial
    assert "Indicadores fundamentalistas" not in initial

    assert "Fila de trabalhos em segundo plano" in read(
        "investment_engine/web/static/feature-admin.js"
    )
    assert "Orçamento atualizado" in read(
        "investment_engine/web/static/feature-finances.js"
    )
    assert "Combinação das tendências" in read(
        "investment_engine/web/static/feature-backtests.js"
    )
    assert "Alocação da carteira: tipos" in read(
        "investment_engine/web/static/feature-portfolio.js"
    )
    assert "Indicadores fundamentalistas" in read(
        "investment_engine/web/static/feature-analysis.js"
    )


def test_lazy_assets_are_served_by_the_same_versioned_static_route():
    api_source = read("investment_engine/api/app.py")
    assert 'app.mount("/ui-assets"' in api_source
    assert '"public, max-age=31536000, immutable"' in api_source
    for asset in (
        "feature-analysis.js",
        "feature-portfolio.js",
        "feature-backtests.js",
        "feature-finances.js",
        "feature-admin.js",
    ):
        path = STATIC / asset
        assert path.is_file(), asset
        assert path.read_text(encoding="utf-8").startswith('"use strict";'), asset


def test_r2_does_not_add_or_rewrite_a_database_migration():
    workflow = read(".github/workflows/tests.yml")
    assert 'assert revision == "0032_v1237_browser_perf"' in workflow
    assert not list((ROOT / "alembic" / "versions").glob("0033*"))

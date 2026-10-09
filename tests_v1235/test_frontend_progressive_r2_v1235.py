from pathlib import Path
from frontend_test_support import browser_source


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "investment_engine" / "web" / "static" / "app.js"
APP_CSS = ROOT / "investment_engine" / "web" / "static" / "app.css"


def test_analysis_renders_primary_rows_before_secondary_backtest_enrichment():
    javascript = browser_source(ROOT)

    primary_render = "state.analysisRows = primaryRows;"
    deferred_enrichment = "enrichAnalysisRowsInBackground(rows"
    assert primary_render in javascript
    assert deferred_enrichment in javascript
    assert javascript.index(primary_render) < javascript.index(deferred_enrichment)
    assert "const enrichedRows=await enrichBacktestLeaders(rows);" not in javascript
    assert "backtest_leaders_pending:true" in javascript
    assert "backtest_leaders_pending:false,backtest_leaders:leaders" in javascript
    assert "rows.map(row=>({...row,backtest_leaders_pending:false}))" in javascript
    assert "if(row.backtest_leaders_pending)return" in javascript


def test_navigation_aborts_obsolete_panel_requests_and_guards_late_results():
    javascript = browser_source(ROOT)

    assert "function beginNavigation(previousView,nextView)" in javascript
    assert "controller.abort()" in javascript
    assert "function navigationIsCurrent(" in javascript
    assert 'requestKey:"asset-detail"' in javascript
    assert 'requestKey:"portfolio-detail"' in javascript
    assert 'requestKey:"finance-catalog"' in javascript
    assert 'requestKey:"backtests-study"' in javascript
    assert 'requestKey:"admin-operations"' in javascript
    assert "function adminPanelIsCurrent(" in javascript
    assert "for(const timer of state.navigationTimers)clearTimeout(timer)" in javascript
    assert "if(serial!==state.navigationSerial)return" in javascript
    assert "Promise.resolve(callback()).catch" in javascript
    assert 'navigationIsCurrent(navigationSerial,"dashboard")' in javascript


def test_catalog_prefetch_and_inflight_get_dedup_do_not_block_first_panel():
    javascript = browser_source(ROOT)

    assert "function prefetchAnalysisCatalogs()" in javascript
    assert "scheduleIdleTask(next,1000)" in javascript
    assert 'const coalesceKey = method === "GET" && !bypassCache && !key ? path : null;' in javascript
    assert "else if(needCustom)customPromise.then(applyCustom)" in javascript
    # Shared prefetches intentionally have no panel request key, so changing
    # tabs does not discard useful catalog work for the next visit.
    assert 'api(`/screen/presets?asset_type=${type}`,{cacheTtlMs:300000})' in javascript


def test_same_panel_stays_visible_during_refresh_and_secondary_work_is_identified():
    javascript = browser_source(ROOT)
    stylesheet = APP_CSS.read_text(encoding="utf-8")

    assert 'root.classList.add("panel-refreshing")' in javascript
    assert ".tab-content.panel-refreshing::before" in stylesheet
    assert ".secondary-loading" in stylesheet
    assert "content-visibility: auto" in stylesheet


def test_search_and_news_timers_cannot_restore_obsolete_interface_state():
    javascript = browser_source(ROOT)

    assert 'state.requestControllers.get("search")?.abort()' in javascript
    assert 'String($("#global-search")?.value||"").trim()!==normalized' in javascript
    assert 'state.portfolioNewsMode===newsMode' in javascript
    assert "scheduleNavigationTask(()=>renderPortfolioTab({forceNews:true}),2500)" in javascript


def test_aborted_market_navigation_does_not_show_a_false_error():
    javascript = browser_source(ROOT)
    start = javascript.index("async function loadMarket(force = false)")
    end = javascript.index("\nfunction pollMarket", start)
    load_market = javascript[start:end]

    abort_guard = 'if (error.name === "AbortError") return;'
    assert abort_guard in load_market
    assert load_market.index(abort_guard) < load_market.index(
        'toast(`Dados de mercado:'
    )

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "investment_engine" / "web" / "static" / "app.js"


def source() -> str:
    return APP_JS.read_text(encoding="utf-8")


def function_body(javascript: str, start: str, end: str) -> str:
    begin = javascript.index(start)
    finish = javascript.index(end, begin)
    return javascript[begin:finish]


def test_same_view_and_tab_are_noops_before_navigation_is_cancelled():
    javascript = source()
    set_view = function_body(javascript, "function setView(", "\nfunction activateTab(")
    activate_tab = function_body(javascript, "function activateTab(", "\nfunction loadingCards(")

    assert "force=false" in set_view
    assert "sameView&&sameTab&&!force" in set_view
    assert set_view.index("sameView&&sameTab&&!force") < set_view.index("beginNavigation(")
    assert "force=false" in activate_tab
    assert "state.tabs[group]===tab&&!force" in activate_tab
    assert activate_tab.index("state.tabs[group]===tab&&!force") < activate_tab.index("beginNavigation(")
    assert "button&&activateTab(" in javascript


def test_read_only_advanced_screen_does_not_purge_navigation_caches():
    javascript = source()
    advanced_calls = javascript.split('api("/screen/advanced"')[1:]

    assert len(advanced_calls) == 3
    assert all("invalidateCache:false" in call.split(");", 1)[0] for call in advanced_calls)
    # Real mutations now invalidate only the affected domains.
    assert "else if (method !== \"GET\" && invalidateCache) invalidateApplicationCache(invalidateTags);" in javascript
    assert "function cacheTagsForPath(" in javascript


def test_stock_and_fii_presets_use_cached_get_routes_before_owner_fallback():
    javascript = source()
    loader = function_body(javascript, "async function loadAnalysisResults(", "\nfunction enrichAnalysisRowsInBackground(")

    owner_branch = loader.index('presetItem?.active_variant==="owner"')
    assert loader.index('type === "stock"') < owner_branch
    assert loader.index('type === "fii"') < owner_branch
    assert "/screen/db/stocks/${state.analysisPreset}" in loader
    assert "/screen/db/fiis/${state.analysisPreset}" in loader


def test_news_navigation_uses_ttl_while_polling_and_refresh_force_bypass():
    javascript = source()

    assert "cacheTtlMs:NEWS_NAVIGATION_CACHE_TTL_MS,bypassCache:force" in javascript
    assert "cacheTtlMs:15000,bypassCache:true" not in javascript
    assert "renderPortfolioTab({forceNews:true})" in javascript
    assert "scheduleNavigationTask(()=>renderPortfolioTab({forceNews:true}),2500)" in javascript
    assert 'if(state.portfolioNewsMode!==mode)' in javascript
    assert 'if(state.recommendationCategory!==category)' in javascript


def test_admin_navigation_uses_short_cache_and_explicit_reload_bypasses_it():
    javascript = source()
    load_admin = function_body(javascript, "async function loadAdmin(", "\nfunction dividendEventLabel(")

    assert "async function loadAdmin(force=false)" in load_admin
    assert "force:Boolean(force)" in load_admin
    assert "cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS" in javascript
    assert "bypassCache:context.force" in javascript
    assert 'if(event.target.closest("[data-reload-admin-jobs]")){loadAdmin(true)' in javascript
    assert 'if(event.target.closest("[data-reload-admin-operations]")){loadAdmin(true)' in javascript
    assert 'if(event.target.closest("[data-reload-admin-quality]")){loadAdmin(true)' in javascript


def test_existing_manual_market_refresh_and_navigation_safety_remain_enabled():
    javascript = source()

    assert '$("#refresh-market").addEventListener("click",()=>loadMarket(true))' in javascript
    assert "state.navigationSerial+=1" in javascript
    assert "controller.abort()" in javascript
    assert "function navigationIsCurrent(" in javascript
    assert "if(cached?.rows?.length)" in javascript

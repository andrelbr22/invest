from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "investment_engine" / "web" / "static" / "app.js"


def test_analysis_renders_rows_before_loading_backtest_leaders():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "const ANALYSIS_CACHE_TTL_MS = 300000;" in source
    render_position = source.index("state.analysisResultCache.set(cacheKey,{savedAt:Date.now(),rows});")
    enrichment_position = source.index("const enrichedRows=await enrichBacktestLeaders(rows);")

    assert render_position < enrichment_position
    assert 'requestSerial!==state.analysisRequestSerial' in source
    assert 'cacheKey!==analysisResultCacheKey(type)' in source
    advanced_start = source.index("async function applyAdvancedFilters")
    advanced_end = source.index("async function openAsset", advanced_start)
    advanced = source[advanced_start:advanced_end]
    assert advanced.index("renderAnalysisRows(rows)") < advanced.index("await enrichBacktestLeaders(rows)")
    assert "requestSerial!==state.analysisRequestSerial" in advanced


def test_background_ensure_does_not_flush_unrelated_read_cache():
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'const invalidateCache = requestOptions.invalidateCache !== false;' in source
    assert 'method !== "GET" && invalidateCache' in source
    assert '/ensure`,{method:"POST",invalidateCache:false}' in source
    assert '/insights/news/refresh-daily",{method:"POST",invalidateCache:false}' in source
    assert source.index("await loadAnalysisResults();") < source.index("state.analysisEnsureSentAt>300000")


def test_simultaneous_cached_gets_are_coalesced():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "readRequests: new Map()" in source
    assert "state.readRequests.has(coalesceKey)" in source
    assert "state.readRequests.set(coalesceKey,pending)" in source


def test_stale_analysis_rows_survive_a_refresh_failure():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "if(cached?.rows?.length){state.analysisRows=cached.rows;renderAnalysisRows(cached.rows)" in source
    assert "Exibindo a última consulta concluída." in source

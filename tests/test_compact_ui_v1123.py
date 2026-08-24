from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "examples" / "streamlit_v15_integrated.py"


def _source():
    return UI.read_text(encoding="utf-8")


def test_compact_visual_system_is_applied_globally():
    source = _source()
    assert ".ie-compact-summary" in source
    assert ".ie-filter-chip" in source
    assert "[data-testid=\"stExpander\"]" in source
    assert 'header[data-testid="stHeader"]' in source
    assert "padding-top: 4rem" in source
    assert "padding-top:4.35rem" in source


def test_market_filters_use_progressive_disclosure_and_visible_summaries():
    source = _source()
    assert 'st.expander("🎯 Universo e subfiltros — clique para ajustar",expanded=False)' in source
    assert 'st.expander("🔎 Filtro de análise e localização — clique para ajustar",expanded=False)' in source
    assert 'st.expander("🧰 Screener avançado — clique para montar regras combinadas",expanded=False)' in source
    assert '"UNIVERSO ATUAL"' in source
    assert '"VISUALIZAÇÃO"' in source


def test_backtest_rules_are_hidden_but_active_context_stays_visible():
    source = _source()
    assert 'st.expander("🧩 Filtros da estratégia — clique para configurar",expanded=False)' in source
    assert 'st.expander("📖 Entenda a estratégia e suas regras",expanded=False)' in source
    assert '"BACKTEST PREPARADO"' in source
    assert "_backtest_filter_summary(filters)" in source


def test_portfolio_keeps_metrics_visible_and_movements_collapsed():
    source = _source()
    assert 'left.expander("➕ Movimentações e edição — clique para abrir",expanded=False)' in source
    assert '"CARTEIRA ATUAL"' in source


def test_release_version_is_consistent():
    assert (ROOT / "investment_engine" / "__init__.py").read_text(encoding="utf-8").strip() == '__version__ = "0.13.4"'
    assert 'version = "0.13.4"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'EXPECTED_EMBEDDED_API_VERSION"] = "0.13.4"' in (ROOT / "streamlit_app.py").read_text(encoding="utf-8")

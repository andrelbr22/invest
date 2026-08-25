from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1] / "examples" / "streamlit_v15_integrated.py"
).read_text(encoding="utf-8")


def test_market_table_can_handoff_exact_visible_stock_selection():
    assert "def _remember_market_backtest_selection(tickers,label):" in SOURCE
    assert "def _send_market_selection_to_official_batch(tickers,label):" in SOURCE
    assert 'st.session_state["official_batch_selected_tickers"]=clean[:100]' in SOURCE
    assert "A seleção enviada será exatamente a que aparece na tabela acima" in SOURCE
    assert "market_to_official_backtests" in SOURCE


def test_admin_automatically_receives_latest_market_signature():
    assert 'market_selection=st.session_state.get("market_backtest_selection_stock")' in SOURCE
    assert 'official_batch_market_signature_applied' in SOURCE
    assert 'st.session_state[selection_key]=market_tickers' in SOURCE
    assert "Usar os {len(market_tickers)} da tela Mercado e análise" in SOURCE
    assert 'key=selection_key' in SOURCE
    assert 'disabled=not bool(github_token) or not callback_ready or not bool(selected)' in SOURCE


def test_advanced_screener_can_handoff_results_and_limit_is_kept():
    assert "advanced_to_official_backtests" in SOURCE
    assert 'f"Screener avançado • {universe_label}"' in SOURCE
    assert "O lote administrativo aceita no máximo 100 ativos" in SOURCE
    assert '_remember_market_backtest_selection([],f"Screener avançado' in SOURCE

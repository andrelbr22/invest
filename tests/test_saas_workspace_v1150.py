from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "examples" / "streamlit_v15_integrated.py"


def test_workspace_header_has_global_lookup_alert_count_and_profile():
    source = UI.read_text(encoding="utf-8")
    assert 'st.container(key="workspace_header")' in source
    assert 'placeholder="Buscar ativo: PETR4, HGLG11, BOVA11…"' in source
    assert 'active_alerts=sum(' in source
    assert '_apply_pending_global_asset_lookup()' in source
    assert 'position:sticky; top:3.15rem' in source


def test_private_short_cache_reuses_http_and_invalidates_after_mutation():
    source = UI.read_text(encoding="utf-8")
    assert 'st.session_state.get("_api_http_session_v1")' in source
    assert 'st.session_state.setdefault("_api_get_cache_v1",{})' in source
    assert 'return f"{CURRENT_USER_EMAIL}|{API}|{path}|{encoded}"' in source
    assert 'elif method!="GET":' in source
    assert '_clear_api_read_cache()' in source


def test_quick_view_reuses_sector_aware_alb_score():
    source = UI.read_text(encoding="utf-8")
    assert '@st.dialog("Visão rápida do ativo",width="large")' in source
    assert 'value=(intelligence or {}).get("alb_score")' in source
    assert 'Saúde (ALB)' in source
    assert 'Abre preço, gráfico curto e indicadores principais sem perder os filtros atuais.' in source


def test_backtest_exports_and_confirmation_forms_are_available():
    source = UI.read_text(encoding="utf-8")
    assert "Exportar operações em CSV" in source
    assert "Exportar comparação em CSV" in source
    assert "Exportar histórico filtrado em CSV" in source
    assert 'with st.form(f"portfolio_settings_{pid}")' in source
    assert 'with st.form("alert_email_preferences")' in source


def test_postgresql_pool_is_bounded_for_oracle_micro():
    source = (ROOT / "investment_engine" / "infrastructure" / "db" / "session.py").read_text(encoding="utf-8")
    assert 'pool_size=5' in source
    assert 'max_overflow=3' in source
    assert 'pool_recycle=1800' in source

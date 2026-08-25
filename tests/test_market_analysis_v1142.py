from pathlib import Path

import pytest

from investment_engine.core.instruments import is_alertable_b3_asset
from investment_engine.core.screening.advanced import row_from_orm
from investment_engine.core.strategies.presets import STOCK_STRATEGIES


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "examples" / "streamlit_v15_integrated.py"
API = ROOT / "investment_engine" / "api" / "app.py"


class Item:
    def __init__(self, **values):
        self.__dict__.update(values)


def test_alert_catalog_accepts_regular_b3_ticker_independent_of_exchange_alias():
    assert is_alertable_b3_asset("BBAS3", "stock") is True
    assert is_alertable_b3_asset("PETR4", "stock") is True
    assert is_alertable_b3_asset("BBAS3F", "stock") is False
    assert is_alertable_b3_asset("DOLQ26", "future") is False


def test_alert_endpoints_share_the_same_asset_eligibility_rule():
    source = API.read_text(encoding="utf-8")
    catalog = source[source.index('@app.get("/alerts/catalog")'):source.index('@app.get("/alerts")')]
    create = source[source.index('@app.post("/alerts")'):source.index('@app.patch("/alerts/{alert_id}/status")')]
    assert "is_alertable_b3_asset(asset.ticker, asset.asset_type)" in catalog
    assert "is_alertable_b3_asset(asset.ticker, asset.asset_type)" in create
    assert 'str(asset.exchange or "B3").upper() != "B3"' not in catalog


def test_graham_upside_is_present_in_advanced_screen_rows():
    asset = Item(
        id="asset-1", ticker="TEST3", name="Teste", asset_type="stock",
        sector="Finance", industry="Banks", segment="Banks",
        market_cap_category="large", metadata_json={},
    )
    fundamental = Item(price=10.0, pe=5.0, pbv=1.0)
    row = row_from_orm(asset, fundamental, None, None)
    expected = 10.0 * (22.5 / 5.0) ** 0.5
    assert row["fundamentals"]["graham_number"] == pytest.approx(expected)
    assert row["fundamentals"]["graham_upside_pct"] == pytest.approx((expected / 10.0 - 1.0) * 100.0)


def test_advanced_screen_ranks_complete_stock_result_before_display_limit():
    source = (ROOT / "investment_engine" / "core" / "screening" / "advanced.py").read_text(encoding="utf-8")
    append_position = source.index("results.append(flat)")
    sort_position = source.index('if asset_type == "stock":', append_position)
    limit_position = source.index("results = results[:limit]", sort_position)
    assert append_position < sort_position < limit_position


def test_market_opens_with_default_analysis_and_graham_ordering():
    source = UI.read_text(encoding="utf-8")
    assert 'st.session_state["market_asset_class"]="Ações"' in source
    assert 'st.session_state[f"market_strategy_ref_{asset_type}"]="preset:default"' in source
    assert 'raw_rows=sorted(raw_rows or [],key=_graham_sort_key,reverse=True)' in source
    assert '"Preço Justo Graham","Potencial Graham %"' in source


def test_analysis_buttons_reset_editable_fundamental_and_technical_sections():
    source = UI.read_text(encoding="utf-8")
    assert STOCK_STRATEGIES["cnpi"].name == "FDI - CNPI"
    assert 'on_click=_select_market_analysis,args=(asset_type,analysis_ref)' in source
    assert 'initial_analysis_filters=_analysis_filter_defaults(asset_type,strategy_ref,custom_by_id)' in source
    assert 'form_instance=active_form_instance,compact=True' in source
    assert 'st.markdown(f"#### Indicadores Fundamentalistas' in source
    assert 'st.markdown("#### Indicadores Técnicos")' in source
    for indicator in (
        "Usar P/L", "Usar P/VP", "Usar Dividend Yield", "Usar ROE", "Usar ROIC",
        "Usar margem EBIT", "Usar margem líquida", "Usar EV/EBITDA",
        "Usar dívida bruta/PL", "Usar dívida líquida/EBITDA", "Usar liquidez corrente",
        "Usar CAGR receita 5 anos", "Usar CAGR lucro 5 anos", "Preço abaixo do Graham",
        "Tendência diária", "Tendência semanal", "Tendência mensal", "Filtrar RSI (14)",
        "Faixa atual do preço", "Proximidade de nível",
    ):
        assert indicator in source

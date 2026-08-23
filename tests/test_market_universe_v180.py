from investment_engine.core.screening.universe import (
    BESST_LABELS,
    besst_category,
    filter_rows_by_tickers,
    universe_tickers,
)


CATALOG = [
    {"ticker": "BBAS3", "name": "Banco do Brasil", "sector": "Finance"},
    {"ticker": "BBSE3", "name": "BB Seguridade", "sector": "Finance"},
    {"ticker": "TAEE11", "name": "Taesa", "industry": "Electric Utilities"},
    {"ticker": "SAPR11", "name": "Sanepar", "industry": "Water Utilities"},
    {"ticker": "VIVT3", "name": "Telefônica Brasil", "industry": "Major Telecommunications"},
    {"ticker": "WEGE3", "name": "WEG", "classification": "Bens industriais", "sector_label": "Bens industriais"},
]


def test_besst_detects_each_requested_group_without_confusing_seguridade_with_bank():
    assert besst_category(CATALOG[0]) == "banks"
    assert besst_category(CATALOG[1]) == "insurance"
    assert besst_category(CATALOG[2]) == "energy"
    assert besst_category(CATALOG[3]) == "sanitation"
    assert besst_category(CATALOG[4]) == "telecom"
    assert besst_category(CATALOG[5]) is None


def test_besst_universe_can_show_all_or_one_group():
    assert universe_tickers(CATALOG, "besst") == ["BBAS3", "BBSE3", "TAEE11", "SAPR11", "VIVT3"]
    assert universe_tickers(CATALOG, "besst", besst_group="banks") == ["BBAS3"]
    assert set(BESST_LABELS) == {"all", "banks", "energy", "insurance", "sanitation", "telecom"}


def test_portfolio_specific_and_classification_scopes_intersect_the_catalog():
    assert universe_tickers(CATALOG, "portfolio", selected_tickers=["vIVt3", "INVALID3"]) == ["VIVT3"]
    assert universe_tickers(CATALOG, "specific", selected_tickers=["WEGE3", "BBAS3"]) == ["BBAS3", "WEGE3"]
    assert universe_tickers(CATALOG, "classification", classification="bens INDUSTRIAIS") == ["WEGE3"]
    assert universe_tickers(
        CATALOG, "classification", classification="BENS INDUSTRIAIS", classification_field="sector_label"
    ) == ["WEGE3"]


def test_row_intersection_preserves_screener_order_and_applies_display_limit():
    rows = [{"ticker": "WEGE3"}, {"ticker": "BBAS3"}, {"ticker": "VIVT3"}]
    assert filter_rows_by_tickers(rows, ["BBAS3", "VIVT3"], limit=1) == [{"ticker": "BBAS3"}]

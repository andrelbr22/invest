from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_portfolio_allocation_uses_two_accessible_svg_rings_without_an_extra_request():
    source = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")

    assert "function hierarchicalAllocationDonut" in source
    assert "allocation-type-slice" in source
    assert "allocation-breakdown-slice" in source
    assert "Interno: tipo • externo: setor ou segmento" in source
    assert 'data-allocation-type=' in source
    assert 'role="button" tabindex="0"' in source
    assert "state.portfolioAllocationHierarchy=data.consolidated_allocation_hierarchy" in source
    assert "function showPortfolioAllocationType" in source

    function_body = source.split("function showPortfolioAllocationType", 1)[1].split("\n}\n", 1)[0]
    assert "api(" not in function_body


def test_portfolio_change_clears_the_selected_allocation_type():
    source = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")

    assert "state.portfolioAllocationType=null;state.portfolioAllocationHierarchy=null;renderPortfolioTab()" in source
    assert 'event.key==="Enter"||event.key===" "' in source


def test_hierarchical_allocation_has_focus_and_mobile_styles():
    css = (ROOT / "investment_engine/web/static/app.css").read_text(encoding="utf-8")

    assert ".allocation-type-slice" in css
    assert ".allocation-breakdown-slice" in css
    assert ".allocation-legend-row" in css
    assert ".allocation-detail-card" in css
    assert "@media (max-width: 720px) { .allocation-visual { grid-template-columns: 1fr; } }" in css

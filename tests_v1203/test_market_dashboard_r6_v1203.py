from frontend_test_support import browser_source
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_comparison_r6_has_calendar_axis_and_custom_period_controls():
    script = browser_source(Path(__file__).resolve().parents[1])
    styles = (ROOT / "investment_engine/web/static/app.css").read_text(encoding="utf-8")

    assert 'comparisonCustom: false' in script
    assert 'data-comparison-custom="true">Personalizar</button>' in script
    assert 'data-comparison-date="from"' in script
    assert 'data-comparison-date="to"' in script
    assert "function comparisonTimeTicks(minX,maxX)" in script
    assert 'month:"short",year:"2-digit"' in script
    assert "cursor.getUTCFullYear()" in script
    assert "comparison-chart-wrap" in script
    assert ".comparison-date-range" in styles
    assert ".comparison-chart-wrap { overflow-x: auto; }" in styles


def test_comparison_r6_preserves_quick_periods_and_refresh():
    script = browser_source(Path(__file__).resolve().parents[1])

    for label in ("6 meses", "1 ano", "2 anos", "3 anos", "5 anos", "10 anos", "15 anos", "20 anos"):
        assert f'"{label}"' in script
    assert 'data-comparison-refresh="true">Atualizar séries</button>' in script

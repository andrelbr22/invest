from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_self_hosted_web_assets_are_complete():
    index = (ROOT / "investment_engine" / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "investment_engine" / "web" / "static" / "app.css").read_text(encoding="utf-8")
    assert "Painel de Mercado" in index
    assert "Mercado e Análises" in index
    assert 'data-tab="fiis"' in index
    assert 'data-tab="etfs"' in index
    assert "/session/me" in script
    assert "/search?q=" in script
    assert 'item.target_tab||"overview"' in script
    assert "sidebar" in styles


def test_runtime_and_dependency_files_have_no_legacy_frontend_reference():
    files = [
        ROOT / "requirements.txt",
        ROOT / "Dockerfile",
        ROOT / "docker-compose.production.yml",
        ROOT / "docker-compose.oracle-web.yml",
        ROOT / "investment_engine" / "api" / "app.py",
        ROOT / "investment_engine" / "infrastructure" / "config.py",
    ]
    forbidden = "stream" + "lit"
    for path in files:
        assert forbidden not in path.read_text(encoding="utf-8").lower(), path


def test_dashboard_uses_tabs_and_isolated_async_requests():
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "loadMarket" in script
    assert "loadHeadlines" in script
    assert "pollMarket" in script
    assert "AbortController" in script

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "investment_engine" / "web"


class _HomeLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.attributes: dict[str, str | None] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("id") == "home-page-link":
            self.attributes = values


def _home_link_attributes() -> dict[str, str | None]:
    parser = _HomeLinkParser()
    parser.feed((WEB_ROOT / "index.html").read_text(encoding="utf-8"))
    assert parser.attributes is not None
    return parser.attributes


def test_platform_has_a_persistent_accessible_link_to_the_public_home_page():
    attributes = _home_link_attributes()

    assert attributes["href"] == "../"
    assert attributes["aria-label"] == "Voltar à página principal"
    assert attributes["title"] == "Página principal"
    assert "topbar-home-link" in str(attributes["class"]).split()

    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert '<span class="topbar-home-label">Página principal</span>' in index
    assert index.index('id="home-page-link"') < index.index('class="icon-button notification-button"')
    assert index.index('id="home-page-link"') < index.index('id="logout-button"')


def test_relative_home_link_preserves_production_and_staging_environments():
    href = str(_home_link_attributes()["href"])

    assert urljoin("https://formacaodoinvestidor.com.br/plataforma/", href) == (
        "https://formacaodoinvestidor.com.br/"
    )
    assert urljoin("https://formacaodoinvestidor.com.br/testefdi/plataforma/", href) == (
        "https://formacaodoinvestidor.com.br/testefdi/"
    )


def test_home_link_remains_visible_on_small_screens_and_is_not_a_logout_action():
    styles = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert ".topbar-home-link {" in styles
    assert ".topbar-home-link:focus-visible" in styles
    assert ".topbar-home-label { display: none; }" in styles
    assert ".topbar-home-link { display: none; }" not in styles
    assert '$("#logout-button").addEventListener' in script
    assert '$("#home-page-link").addEventListener' not in script

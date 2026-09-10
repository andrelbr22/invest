from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from investment_engine.api.app import app


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "investment_engine" / "web"
api_module = importlib.import_module("investment_engine.api.app")

BOOK_COVERS = (
    "formacao-investidor-fundamentos.webp",
    "formacao-investidor-analise-tecnica.webp",
    "formacao-investidor-trade-system-psicologia.webp",
    "jogo-dos-imoveis.webp",
    "engenharia-trade-system.webp",
    "metodo-agir.webp",
    "caos-criativo.webp",
)


@pytest.fixture()
def client():
    # HTTPS also exercises the production-style Secure session cookie.
    with TestClient(app, base_url="https://localhost") as test_client:
        yield test_client


def test_public_root_and_head_serve_the_portal_instead_of_the_private_spa(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Conhecimento, método e autonomia" in response.text
    assert "Sete obras. Uma mesma busca por autonomia." in response.text
    assert 'href="./plataforma/"' in response.text
    assert 'id="app-shell"' not in response.text

    head = client.head("/")
    assert head.status_code == 200
    assert head.headers["content-type"].startswith("text/html")
    assert head.content == b""


def test_portal_presents_all_seven_books_and_only_local_cover_assets():
    portal = (WEB_ROOT / "portal.html").read_text(encoding="utf-8")
    expected_titles = (
        "Fundamentos",
        "Análise Técnica",
        "Trade System e Psicologia do Investidor",
        "O Jogo dos Imóveis",
        "A Engenharia do Trade System",
        "Método A.G.I.R.",
        "O Caos Criativo",
    )
    for title in expected_titles:
        assert title in portal

    cover_sources = re.findall(
        r'<img[^>]+src="\./portal-assets/books/([^"?]+)"', portal,
    )
    assert set(cover_sources) == set(BOOK_COVERS)
    assert len(cover_sources) == 10  # 3 hero covers plus the 7 catalog cards.
    assert "http://" not in portal
    assert "https://" not in portal


@pytest.mark.parametrize("filename", BOOK_COVERS)
def test_book_covers_are_served_as_immutable_webp_assets(client, filename):
    response = client.get(f"/portal-assets/books/{filename}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert len(response.content) > 10_000


def test_portal_stylesheet_is_available_but_not_marked_immutable(client):
    response = client.get("/portal-assets/portal.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert response.headers["cache-control"] == "no-cache"
    assert b".portal-header" in response.content


def test_platform_redirect_is_relative_and_spa_has_prefix_safe_assets(client):
    redirect = client.get("/plataforma", follow_redirects=False)
    assert redirect.status_code == 308
    assert redirect.headers["location"] == "plataforma/"

    response = client.get("/plataforma/")
    assert response.status_code == 200
    assert 'id="app-shell"' in response.text
    assert 'href="../favicon.svg"' in response.text
    assert 'href="../ui-assets/app.css"' in response.text
    assert 'src="../ui-assets/app.js"' in response.text

    head = client.head("/plataforma/")
    assert head.status_code == 200
    assert head.content == b""


@pytest.mark.parametrize(
    ("supplied", "expected"),
    (
        ("/plataforma/", "/plataforma/"),
        ("/testefdi/plataforma/", "/testefdi/plataforma/"),
        (None, "/plataforma/"),
        ("", "/plataforma/"),
        ("/plataforma", "/plataforma/"),
        ("//malicioso.example", "/plataforma/"),
        ("https://malicioso.example/", "/plataforma/"),
        ("/testefdi/plataforma/../../admin", "/plataforma/"),
    ),
)
def test_oauth_destination_accepts_only_the_two_exact_platform_paths(supplied, expected):
    assert api_module._safe_platform_destination(supplied) == expected


def test_login_redirect_preserves_staging_prefix_when_authentication_is_disabled(
    client, monkeypatch,
):
    monkeypatch.setattr(api_module.settings, "app_auth_required", False)

    staging = client.get(
        "/login?next=%2Ftestefdi%2Fplataforma%2F", follow_redirects=False,
    )
    assert staging.status_code in {302, 303, 307, 308}
    assert staging.headers["location"] == "/testefdi/plataforma/"

    malicious = client.get(
        "/login?next=https%3A%2F%2Fmalicioso.example%2F", follow_redirects=False,
    )
    assert malicious.headers["location"] == "/plataforma/"


def test_oauth_callback_uses_the_safe_staging_destination_saved_in_session(
    client, monkeypatch,
):
    class FakeOAuthClient:
        async def authorize_redirect(self, _request, _redirect_uri):
            return RedirectResponse("https://accounts.google.com/mock")

    monkeypatch.setattr(api_module.settings, "app_auth_required", True)
    monkeypatch.setattr(api_module.settings, "google_client_id", "test-client")
    monkeypatch.setattr(api_module.settings, "google_client_secret", "test-secret")
    monkeypatch.setattr(api_module.settings, "session_secret", "s" * 48)
    monkeypatch.setattr(
        api_module._OAUTH, "create_client", lambda _name: FakeOAuthClient(),
    )

    login = client.get(
        "/login?next=%2Ftestefdi%2Fplataforma%2F", follow_redirects=False,
    )
    assert login.headers["location"] == "https://accounts.google.com/mock"

    monkeypatch.setattr(api_module._OAUTH, "create_client", lambda _name: None)
    callback = client.get("/oauth2callback", follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"] == (
        "/testefdi/plataforma/?auth_error=not_configured"
    )


def test_caddy_and_browser_paths_keep_portal_and_platform_inside_testefdi():
    caddy = (
        ROOT / "deployment" / "Caddyfile.oracle-micro.example"
    ).read_text(encoding="utf-8")
    portal = (WEB_ROOT / "portal.html").read_text(encoding="utf-8")
    spa = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    browser = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "redir /testefdi /testefdi/ 308" in caddy
    assert "redir /testefdi/plataforma /testefdi/plataforma/ 308" in caddy
    assert "handle_path /testefdi/*" in caddy
    assert 'header X-Robots-Tag "noindex, nofollow"' in caddy

    # Relative URLs resolve correctly both at / and after Caddy strips /testefdi/.
    assert 'href="./portal-assets/portal.css"' in portal
    assert 'href="./plataforma/"' in portal
    assert 'href="../ui-assets/app.css"' in spa
    assert 'src="../ui-assets/app.js"' in spa
    assert 'location.pathname === "/testefdi"' in browser
    assert 'const PLATFORM_PATH = `${BASE_PATH}/plataforma/`' in browser
    assert "encodeURIComponent(PLATFORM_PATH)" in browser

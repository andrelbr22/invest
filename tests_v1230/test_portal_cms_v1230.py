from __future__ import annotations

import base64

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.api.app import _request_email, app, get_db
from investment_engine.core.repositories.portal import PortalRepository
from investment_engine.infrastructure.config import settings
from investment_engine.infrastructure.db.base import Base


def _client(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(settings, "app_auth_required", False)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_request_email] = lambda: "local-owner@localhost"
    return engine, TestClient(app, base_url="https://localhost")


def test_public_portal_seeds_complete_static_compatible_catalog(monkeypatch):
    engine, client = _client(monkeypatch)
    try:
        response = client.get("/public/portal")
        assert response.status_code == 200
        payload = response.json()
        assert payload["revision"] == 1
        assert payload["page"]["hero"]["title"]
        assert payload["page"]["brand"]["monogram"] == "FI"
        assert payload["page"]["navigation"]["admin"] == "Ajustes da página"
        assert payload["page"]["navigation"]["skip"] == "Ir para o conteúdo"
        assert len(payload["books"]) == 7
        with Session(engine) as session:
            assert len(PortalRepository(session).list_books(include_unpublished=True)) == 7
    finally:
        app.dependency_overrides.clear()


def test_owner_edits_page_books_cover_and_three_sales_links(monkeypatch):
    _engine, client = _client(monkeypatch)
    try:
        admin = client.get("/admin/portal")
        assert admin.status_code == 200, admin.text
        revision = admin.json()["revision"]
        changed = client.put("/admin/portal/page", json={
            "patch": {"hero": {"title": "Uma nova apresentação"}},
            "expected_revision": revision,
        })
        assert changed.status_code == 200, changed.text
        assert changed.json()["content"]["hero"]["title"] == "Uma nova apresentação"

        # One valid 1x1 PNG, stored in the database and served with immutable caching.
        png = base64.b64encode(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )).decode()
        media = client.post("/admin/portal/media", json={
            "filename": "capa.png", "data_url": f"data:image/png;base64,{png}",
        })
        assert media.status_code == 200, media.text
        media_id = media.json()["id"]
        # Upload is a private draft until a published book references it.
        assert client.get(f"/portal-media/{media_id}").status_code == 404

        created = client.post("/admin/portal/books", json={
            "values": {
                "slug": "livro-de-teste", "collection": "complementary",
                "title": "Livro de teste", "alt_text": "Capa do livro de teste",
                "summary": "Resumo", "description": "Descrição",
                "cover_media_id": media_id, "is_published": True,
            },
            "sales_links": [
                {"label": "Loja 1", "url": "https://example.com/1"},
                {"label": "Loja 2", "url": "https://example.com/2"},
                {"label": "Loja 3", "url": "https://example.com/3"},
            ],
        })
        assert created.status_code == 200, created.text
        assert len(created.json()["sales_links"]) == 3
        served = client.get(f"/portal-media/{media_id}")
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("image/png")
        assert "immutable" in served.headers["cache-control"]
        public = client.get("/public/portal").json()
        assert any(book["slug"] == "livro-de-teste" for book in public["books"])
    finally:
        app.dependency_overrides.clear()


def test_portal_rejects_stale_revision_unsafe_link_and_fourth_link(monkeypatch):
    _engine, client = _client(monkeypatch)
    try:
        admin = client.get("/admin/portal").json()
        assert client.put("/admin/portal/page", json={
            "patch": {"footer": {"platform": "Entrar"}},
            "expected_revision": admin["revision"],
        }).status_code == 200
        conflict = client.put("/admin/portal/page", json={
            "patch": {"footer": {"platform": "Antigo"}},
            "expected_revision": admin["revision"],
        })
        assert conflict.status_code == 409

        base_values = {
            "slug": "link-inseguro", "collection": "primary",
            "title": "Teste", "alt_text": "Capa",
        }
        unsafe = client.post("/admin/portal/books", json={
            "values": base_values,
            "sales_links": [{"label": "Loja", "url": "http://example.com"}],
        })
        assert unsafe.status_code == 422
        too_many = client.post("/admin/portal/books", json={
            "values": base_values,
            "sales_links": [
                {"label": f"Loja {index}", "url": f"https://example.com/{index}"}
                for index in range(4)
            ],
        })
        assert too_many.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_portal_interface_contains_dynamic_hydration_and_admin_controls():
    portal = open("investment_engine/web/portal.html", encoding="utf-8").read()
    portal_js = open("investment_engine/web/portal-assets/portal.js", encoding="utf-8").read()
    app_js = open("investment_engine/web/static/app.js", encoding="utf-8").read()
    assert "portal-assets/portal.js" in portal
    assert "/public/portal" in portal_js
    assert "figure.hidden = !book" in portal_js
    assert 'all(".brand-monogram")' in portal_js
    assert 'setText(".skip-link"' in portal_js
    assert "data-portal-book-form" in app_js
    assert 'navigation.admin","Link de ajustes"' in app_js
    assert "Links de venda — até três" in app_js
    assert "can_manage_portal" in app_js

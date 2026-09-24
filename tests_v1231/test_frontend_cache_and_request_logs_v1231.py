from __future__ import annotations

from pathlib import Path
import re

from fastapi.testclient import TestClient

from investment_engine.api.app import _is_quiet_successful_request, app


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "investment_engine" / "web"


def test_normal_navigation_only_ensures_stale_or_unavailable_market_data():
    script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'force?"/market-dashboard/refresh":"/market-dashboard/ensure"' in script
    assert 'const needsEnsure=requiredGroups.some' in script
    assert '["unavailable","stale","failed"].includes(envelope.updates?.[key]?.status)' in script
    assert '["unavailable","stale","failed"].includes(updatePayload.updates?.[group]?.status)' in script
    assert "/market-dashboard/groups/${encodeURIComponent(group)}/ensure" in script
    assert "Date.now()-state.analysisEnsureSentAt>300000" in script

    # Manual refresh, recovery fallback and polling of active work remain available.
    assert 'const endpoint=force?"/market-dashboard/refresh":"/market-dashboard/ensure"' in script
    assert 'api(endpoint, {method:"POST",invalidateCache:false}' in script
    assert "/market-dashboard/groups/${encodeURIComponent(group)}/refresh" in script
    assert '["queued","running"].includes(envelope.refresh_status)' in script
    assert "pollMarket()" in script


def test_static_references_are_versioned_and_receive_immutable_cache_headers():
    platform = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    portal = (WEB_ROOT / "portal.html").read_text(encoding="utf-8")
    portal_script = (WEB_ROOT / "portal-assets" / "portal.js").read_text(encoding="utf-8")
    app_script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "../ui-assets/app.css?v=1.23.1-r1" in platform
    assert "../ui-assets/app.js?v=1.23.1-r1" in platform
    assert "./portal-assets/portal.css?v=1.23.1-r1" in portal
    assert "./portal-assets/portal.js?v=1.23.1-r1" in portal
    portal_asset_references = [
        value for value in re.findall(r'(?:src|href)="([^"]+)"', portal)
        if "/portal-assets/" in value
    ]
    assert portal_asset_references
    assert all("?v=1.23.1-r1" in value for value in portal_asset_references)
    assert "?v=1.23.1-r1" in portal_script
    assert "?v=1.23.1-r1" in app_script

    client = TestClient(app, base_url="http://localhost")
    for path in (
        "/ui-assets/app.css?v=1.23.1-r1",
        "/ui-assets/app.js?v=1.23.1-r1",
        "/portal-assets/portal.css?v=1.23.1-r1",
        "/portal-assets/books/formacao-investidor-fundamentos.webp?v=1.23.1-r1",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_only_successful_health_and_static_requests_are_quiet():
    assert _is_quiet_successful_request("/health", 200)
    assert _is_quiet_successful_request("/ready", 200)
    assert _is_quiet_successful_request("/ui-assets/app.js", 304)
    assert _is_quiet_successful_request("/portal-assets/portal.css", 200)
    assert _is_quiet_successful_request("/portal-media/00000000-0000-0000-0000-000000000000", 200)

    # Failures on those same routes and normal business requests remain logged.
    assert not _is_quiet_successful_request("/health", 500)
    assert not _is_quiet_successful_request("/ui-assets/missing.js", 404)
    assert not _is_quiet_successful_request("/market-dashboard", 200)


def test_uvicorn_access_log_is_disabled_because_structured_middleware_logs_requests():
    startup = (ROOT / "deployment" / "start-api.sh").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "--no-access-log" in startup
    assert '"--no-access-log"' in dockerfile

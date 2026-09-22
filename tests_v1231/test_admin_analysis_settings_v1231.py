from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module, util
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.api.app import _request_email, app, get_db
from investment_engine.core.analysis_settings import (
    ANALYSIS_ASSET_TYPES,
    FACTORY_COLUMN_ORDERS,
    SYSTEM_PRESET_KEYS,
    AnalysisSettingsService,
)
from investment_engine.core.investor_events import service as investor_service_module
from investment_engine.core.investor_events.service import AlbUniverseMonitor
from investment_engine.infrastructure.config import settings
from investment_engine.infrastructure.db.base import Base


ROOT = Path(__file__).resolve().parents[1]
api_module = import_module("investment_engine.api.app")


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


def _stock_default(payload: dict) -> dict:
    return next(
        item for item in payload["presets"]
        if item["asset_type"] == "stock" and item["preset_id"] == "default"
    )


def test_migration_seeds_the_exact_factory_payload_exposed_by_r7():
    spec = util.spec_from_file_location(
        "migration_0027", ROOT / "alembic" / "versions" / "0027_v1_23_analysis_settings.py",
    )
    assert spec is not None and spec.loader is not None
    migration = util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    seeded = migration._factory_presets()
    assert migration.down_revision == "0026_v1_23_email_login"
    assert set(seeded) == {
        (asset_type, preset_id)
        for asset_type in ANALYSIS_ASSET_TYPES
        for preset_id in SYSTEM_PRESET_KEYS
    }
    for key, configuration in seeded.items():
        assert configuration == api_module._factory_preset_configuration(*key)
    assert migration.FACTORY_COLUMNS == {
        asset_type: list(columns) for asset_type, columns in FACTORY_COLUMN_ORDERS.items()
    }


def test_owner_variant_is_global_revisioned_and_reset_restores_factory(monkeypatch):
    _engine, client = _client(monkeypatch)
    try:
        admin = client.get("/admin/analysis-settings")
        assert admin.status_code == 200, admin.text
        original = _stock_default(admin.json())
        assert original["active_variant"] == "factory"
        assert original["factory_version"] == "v1.23.0-r7"

        owner_configuration = deepcopy(original["factory_configuration"])
        owner_configuration["fundamental_filters"]["pe"]["max"] = 12
        changed = client.put(
            "/admin/analysis-settings/presets/stock/default",
            json={
                "configuration": owner_configuration,
                "owner_enabled": True,
                "expected_revision": original["revision"],
            },
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["active_variant"] == "owner"
        assert changed.json()["configuration"]["fundamental_filters"]["pe"]["max"] == 12

        public = client.get("/screen/presets", params={"asset_type": "stock"})
        assert public.status_code == 200, public.text
        effective = next(item for item in public.json()["items"] if item["id"] == "default")
        assert effective["owner_enabled"] is True
        assert effective["configuration"]["fundamental_filters"]["pe"]["max"] == 12
        assert effective["factory_configuration"] == original["factory_configuration"]

        stale = client.put(
            "/admin/analysis-settings/presets/stock/default",
            json={
                "configuration": owner_configuration,
                "owner_enabled": True,
                "expected_revision": original["revision"],
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"] == "analysis_settings_revision_conflict"

        reset = client.post(
            "/admin/analysis-settings/presets/stock/default/reset",
            json={"expected_revision": changed.json()["revision"]},
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["active_variant"] == "factory"
        assert reset.json()["configuration"] == original["factory_configuration"]
        # Reset is reversible and does not discard the last owner document.
        assert reset.json()["owner_configuration"]["fundamental_filters"]["pe"]["max"] == 12
    finally:
        app.dependency_overrides.clear()


def test_column_order_is_validated_exposed_and_reset_without_hiding_catalog(monkeypatch):
    _engine, client = _client(monkeypatch)
    try:
        admin = client.get("/admin/analysis-settings").json()
        stock = next(item for item in admin["columns"] if item["asset_type"] == "stock")
        assert stock["available_columns"][0] == {"id": "ticker", "label": "Ativo", "always": True}
        assert all(isinstance(item["label"], str) for item in stock["available_columns"])

        order = ["ticker", "price", "sector", "dy"]
        changed = client.put(
            "/admin/analysis-settings/columns/stock",
            json={"columns": order, "owner_enabled": True, "expected_revision": stock["revision"]},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["columns"] == order
        assert len(changed.json()["available_columns"]) > len(order)

        public = client.get("/screen/presets", params={"asset_type": "stock"}).json()
        assert public["columns"]["columns"] == order

        duplicate = client.put(
            "/admin/analysis-settings/columns/stock",
            json={
                "columns": ["ticker", "price", "price"],
                "owner_enabled": True,
                "expected_revision": changed.json()["revision"],
            },
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["detail"] == "analysis_columns_duplicate"

        reset = client.post(
            "/admin/analysis-settings/columns/stock/reset",
            json={"expected_revision": changed.json()["revision"]},
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["columns"] == list(FACTORY_COLUMN_ORDERS["stock"])
        assert reset.json()["owner_columns"] == order
    finally:
        app.dependency_overrides.clear()


def test_analysis_settings_are_exclusive_to_the_real_owner(monkeypatch):
    _engine, client = _client(monkeypatch)
    try:
        app.dependency_overrides[_request_email] = lambda: "delegated-admin@example.com"
        response = client.get("/admin/analysis-settings")
        assert response.status_code == 403
        assert response.json()["detail"] == "owner_access_required"
    finally:
        app.dependency_overrides.clear()


def test_invalid_preset_fields_are_rejected_instead_of_silently_ignored(monkeypatch):
    _engine, client = _client(monkeypatch)
    try:
        current = _stock_default(client.get("/admin/analysis-settings").json())
        invalid = deepcopy(current["factory_configuration"])
        invalid["fundamental_filters"]["invented_metric"] = {"min": 1}
        response = client.put(
            "/admin/analysis-settings/presets/stock/default",
            json={
                "configuration": invalid,
                "owner_enabled": True,
                "expected_revision": current["revision"],
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "unsupported_fundamental_filter:invented_metric"
    finally:
        app.dependency_overrides.clear()


def test_alb_monitor_records_the_active_owner_revision_without_relaxation(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    captured = {}
    with Session(engine) as session:
        service = AnalysisSettingsService(session, api_module._factory_preset_configuration)
        current = service.preset_payload("stock", "alb", ensure=True)
        owner = deepcopy(current["factory_configuration"])
        owner["fundamental_filters"]["roe_pct"]["min"] = 18
        service.update_preset(
            "stock", "alb", configuration=owner, enabled=True,
            expected_revision=current["revision"], actor="owner@example.com",
        )
        session.commit()

        def fake_advanced(_repository, **kwargs):
            captured.update(kwargs)
            return {"rows": [{"ticker": "TEST3"}, {"ticker": "ABCD4"}], "meta": {}}

        monkeypatch.setattr(investor_service_module, "advanced_screen", fake_advanced)
        result = AlbUniverseMonitor(session).run(now=datetime(2026, 9, 21, tzinfo=timezone.utc))
        session.commit()

        assert result["preset_version"] == "alb-owner-r2"
        assert result["tickers"] == ["ABCD4", "TEST3"]
        assert captured["fundamental_filters"]["roe_pct"]["min"] == 18
        assert captured["limit"] == 1000

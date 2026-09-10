from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine import __version__
from investment_engine.api.app import app, get_db
from investment_engine.core.alert_policy import (
    B3_ALERT_INTERVAL_MINUTES,
    MARKET_ALERT_INTERVAL_MINUTES,
)
from investment_engine.core.alerts.catalog import market_alert_catalog
from investment_engine.core.jobs.schedules import REFRESH_SCHEDULES
from investment_engine.core.repositories.access import (
    PERMISSION_FIELDS,
    AccessLevelRepository,
    AccessPolicyRepository,
    policy_dict,
)
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import UserAccessPolicyORM
from investment_engine.infrastructure.config import settings


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "investment_engine" / "web" / "static" / "app.js"


def test_release_metadata_and_migration_are_v1213():
    assert __version__ == "1.22.0"
    assert (ROOT / "alembic" / "versions" / "0021_v1_21_access_levels.py").is_file()
    assert (ROOT / "V1_21_3.md").is_file()
    assert (ROOT / "PATCH_V1213.md").is_file()
    assert (ROOT / "INSTRUCOES_ORACLE_V1213.md").is_file()


def test_shared_level_changes_propagate_and_blocking_still_wins():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        levels = AccessLevelRepository(session)
        member = levels.create(
            slug="member",
            name="Membro",
            rules={"can_view_market": True, "can_view_portfolio": True},
        )
        policies = AccessPolicyRepository(session)
        first = policies.register("primeiro@example.com")
        second = policies.register("segundo@example.com")
        policies.assign_level(first.email, member)
        policies.assign_level(second.email, member)
        session.commit()

        assert policy_dict(first)["can_view_finances"] is False
        assert policy_dict(second)["can_view_finances"] is False
        levels.update("member", rules={
            "can_view_finances": True,
            "can_write_finances": True,
            "can_view_news_insights": True,
        })
        session.commit()
        assert policy_dict(first)["can_write_finances"] is True
        assert policy_dict(second)["can_view_news_insights"] is True

        second.status = "blocked"
        session.flush()
        assert policy_dict(second)["can_view_market"] is False
        assert policy_dict(first)["can_view_market"] is True


def test_legacy_account_is_not_silently_changed_until_level_assignment():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        legacy = UserAccessPolicyORM(
            email="legado@example.com",
            status="approved",
            can_view_market=True,
            can_use_fdi_analysis=True,
            can_view_portfolio=True,
        )
        session.add(legacy)
        session.commit()
        rendered = policy_dict(legacy)
        assert rendered["access_inheritance"] is False
        assert rendered["can_use_fdi_analysis"] is True
        assert rendered["can_view_portfolio"] is True


def test_administration_routes_cover_levels_users_and_background_jobs():
    paths = {route.path for route in app.routes}
    for path in (
        "/access/levels",
        "/access/levels/{level_slug}",
        "/access/users/manage",
        "/access/users/{email}/level",
        "/access/users/level/bulk",
        "/access/users/{email}/overrides",
        "/admin/jobs",
        "/admin/jobs/{job_id}/retry",
        "/alerts/monitor/run",
    ):
        assert path in paths


def test_owner_can_create_level_assign_it_and_list_effective_user_access(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        AccessPolicyRepository(session).register("membro@example.com", "Conta de teste")
        session.commit()

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(settings, "app_auth_required", False)
    try:
        # localhost belongs to every deployment allow-list.  Authentication is
        # disabled only inside this isolated test so the built-in local owner
        # can exercise the repository regardless of the staging environment.
        client = TestClient(app, base_url="http://localhost")
        created = client.post("/access/levels", json={
            "slug": "assinante",
            "name": "Assinante",
            "permissions": {
                "can_view_market": True,
                "can_view_portfolio": True,
                "can_use_price_alerts": True,
                "can_alert_price_above": True,
            },
            "limits": {"alert_asset_limit": 3},
        })
        assert created.status_code == 200, created.text
        assigned = client.put("/access/users/membro@example.com/level", json={
            "level_slug": "assinante",
            "clear_overrides": True,
        })
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["access_level_slug"] == "assinante"
        assert assigned.json()["alert_asset_limit"] == 3

        managed = client.get("/access/users/manage", params={"level": "assinante"})
        assert managed.status_code == 200, managed.text
        assert managed.json()["total"] == 1
        assert managed.json()["items"][0]["email"] == "membro@example.com"

        changed = client.put("/access/levels/assinante", json={
            "permissions": {"can_view_finances": True},
        })
        assert changed.status_code == 200, changed.text
        assert changed.json()["member_count"] == 1
        with Session(engine) as session:
            effective = policy_dict(AccessPolicyRepository(session).get("membro@example.com"))
            assert effective["can_view_finances"] is True
    finally:
        app.dependency_overrides.clear()


def test_admin_ui_exposes_every_permission_and_every_scheduled_update():
    script = SCRIPT.read_text(encoding="utf-8")
    for permission in PERMISSION_FIELDS:
        assert permission in script
    for refresh_key in REFRESH_SCHEDULES:
        assert f'key:"{refresh_key}"' in script
    assert "Atualizar todas as 13 rotinas" in script
    assert "Fila de trabalhos" in (ROOT / "investment_engine" / "web" / "index.html").read_text(encoding="utf-8")


def test_complete_alert_ui_and_exact_monitoring_intervals_are_exposed():
    script = SCRIPT.read_text(encoding="utf-8")
    assert B3_ALERT_INTERVAL_MINUTES == 5
    assert MARKET_ALERT_INTERVAL_MINUTES == 30
    for marker in (
        "price-alert-form",
        "alert-preference-form",
        "data-alert-test-email",
        "Histórico de alertas disparados",
        "Demais mercados: 30 minutos",
    ):
        assert marker in script
    keys = {item["key"] for item in market_alert_catalog()}
    assert {"IBRX100", "IBRX50", "IDIV", "SMLL", "SOLUSD", "XRPUSD", "BNBUSD"}.issubset(keys)


def test_recommendations_screen_and_first_authenticated_access_refresh_are_wired():
    script = SCRIPT.read_text(encoding="utf-8")
    initialize = script.split("async function initialize()", 1)[1]
    assert '/insights/news/refresh-daily' in initialize
    assert 'session.access?.can_view_news_insights' in initialize
    assert '/insights/news/cache/recommendations' in script
    assert "Notícias de recomendações" in script
    assert "Ativos da carteira" in script
    assert "Recomendações" in script

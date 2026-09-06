from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import Boolean, Column, MetaData, String, Table, create_engine, select
from sqlalchemy.orm import Session

from investment_engine.api.app import (
    AccessPolicyUpdateRequest,
    _require_valuation_access,
    update_access_user,
)
from investment_engine.core.repositories.access import (
    PERMISSION_FIELDS,
    AccessPolicyRepository,
    full_owner_policy,
    policy_dict,
)
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import UserAccessPolicyORM


ROOT = Path(__file__).resolve().parents[1]


def _load_migration():
    path = ROOT / "alembic" / "versions" / "0020_v1_21_valuation_permissions.py"
    spec = spec_from_file_location("migration_0020_v1_21_valuation_access", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_new_valuation_permissions_are_first_class_and_owner_enabled():
    expected = {"can_use_relative_valuation", "can_use_economic_valuation"}
    assert expected.issubset(PERMISSION_FIELDS)
    request = AccessPolicyUpdateRequest(
        can_use_relative_valuation=True,
        can_use_economic_valuation=False,
    )
    assert request.can_use_relative_valuation is True
    assert request.can_use_economic_valuation is False
    assert all(full_owner_policy("owner@example.com")[field] for field in expected)


def test_alb_inherits_all_four_valuation_permissions_in_policy_and_storage():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = UserAccessPolicyORM(
            email="investidor@example.com",
            status="approved",
            can_use_alb_analysis=False,
        )
        session.add(row)
        session.commit()

        updated = AccessPolicyRepository(session).update(
            row.email,
            can_use_alb_analysis=True,
        )
        assert updated is not None
        assert updated.can_use_relative_valuation is True
        assert updated.can_use_economic_valuation is True
        rendered = policy_dict(updated)
        assert all(rendered[field] is True for field in (
            "can_use_graham_valuation",
            "can_use_dividend_ceiling",
            "can_use_relative_valuation",
            "can_use_economic_valuation",
        ))


def test_admin_api_persists_individual_grants_and_market_revocation_clears_them():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        AccessPolicyRepository(session).register("investidor@example.com")
        session.commit()

        granted = update_access_user(
            "investidor@example.com",
            AccessPolicyUpdateRequest(
                can_use_relative_valuation=True,
                can_use_economic_valuation=True,
            ),
            _access={"is_owner": True},
            db=session,
        )
        assert granted["can_view_market"] is True
        assert granted["can_use_relative_valuation"] is True
        assert granted["can_use_economic_valuation"] is True

        revoked = update_access_user(
            "investidor@example.com",
            AccessPolicyUpdateRequest(can_view_market=False),
            _access={"is_owner": True},
            db=session,
        )
        assert revoked["can_use_relative_valuation"] is False
        assert revoked["can_use_economic_valuation"] is False


@pytest.mark.parametrize(
    ("flag", "permission"),
    (
        ("below_relative_value", "can_use_relative_valuation"),
        ("below_economic_value", "can_use_economic_valuation"),
    ),
)
def test_api_valuation_guard_requires_each_new_permission(flag, permission):
    with pytest.raises(HTTPException) as error:
        _require_valuation_access({flag: True}, {})
    assert error.value.status_code == 403
    assert error.value.detail == {"permission_required": permission}
    _require_valuation_access({flag: True}, {permission: True})
    _require_valuation_access({flag: True}, {"can_use_alb_analysis": True})


def test_migration_adds_columns_and_backfills_existing_alb_accounts(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    policies = Table(
        "user_access_policies",
        metadata,
        Column("email", String(320), primary_key=True),
        Column("can_use_alb_analysis", Boolean, nullable=False, default=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(policies.insert(), [
            {"email": "alb@example.com", "can_use_alb_analysis": True},
            {"email": "basic@example.com", "can_use_alb_analysis": False},
        ])
        migration = _load_migration()
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        monkeypatch.setattr(
            migration.op,
            "add_column",
            lambda table, column: connection.exec_driver_sql(
                f"ALTER TABLE {table} ADD COLUMN {column.name} BOOLEAN NOT NULL DEFAULT 0"
            ),
        )
        migration.upgrade()
        migrated = Table("user_access_policies", MetaData(), autoload_with=connection)
        rows = {
            row.email: row
            for row in connection.execute(select(migrated)).mappings()
        }
        assert rows["alb@example.com"]["can_use_relative_valuation"] is True
        assert rows["alb@example.com"]["can_use_economic_valuation"] is True
        assert rows["basic@example.com"]["can_use_relative_valuation"] is False
        assert rows["basic@example.com"]["can_use_economic_valuation"] is False

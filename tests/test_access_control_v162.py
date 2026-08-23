from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.repositories.access import AccessPolicyRepository, full_owner_policy, policy_dict
from investment_engine.infrastructure.db.base import Base


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_new_google_user_is_read_only_visitor():
    with make_session() as session:
        row = AccessPolicyRepository(session).register("Visitante@Example.com", "Visitante")
        policy = policy_dict(row)
        assert policy["email"] == "visitante@example.com"
        assert policy["can_view_market"] is True
        assert policy["can_use_advanced_filters"] is False
        assert policy["can_view_portfolio"] is False
        assert policy["can_write_portfolio"] is False
        assert policy["can_run_backtests"] is False
        assert policy["can_sync_market"] is False


def test_blocked_user_loses_every_permission():
    with make_session() as session:
        repo = AccessPolicyRepository(session)
        repo.register("blocked@example.com")
        row = repo.update("blocked@example.com", status="blocked", can_view_market=True, can_view_portfolio=True)
        policy = policy_dict(row)
        assert policy["can_view_market"] is False
        assert policy["can_view_portfolio"] is False


def test_owner_policy_is_always_full_access():
    policy = full_owner_policy("owner@example.com", "Proprietário")
    assert policy["is_owner"] is True
    assert policy["status"] == "approved"
    assert policy["can_manage_users"] is True
    assert policy["can_write_portfolio"] is True

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.repositories.screening_filters import SavedScreeningFilterRepository
from investment_engine.infrastructure.db.base import Base


def test_default_names_are_unique_per_user():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = SavedScreeningFilterRepository(session)
        first = repo.create(owner_email="user@example.com", asset_type="stock", filters={}, name=None, display_name="André")
        second = repo.create(owner_email="user@example.com", asset_type="stock", filters={}, name=None, display_name="André")
        other = repo.create(owner_email="other@example.com", asset_type="stock", filters={}, name=None, display_name="André")
        assert first.name == "André"
        assert second.name == "André (1)"
        assert other.name == "André"


def test_saved_filters_are_isolated_by_owner():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = SavedScreeningFilterRepository(session)
        row = repo.create(owner_email="one@example.com", asset_type="fii", filters={"pbv_max": 1}, name="Meu FII")
        assert repo.get(row.id, "one@example.com") is row
        assert repo.get(row.id, "two@example.com") is None

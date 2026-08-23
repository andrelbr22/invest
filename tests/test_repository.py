from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.infrastructure.db.base import Base


def test_asset_upsert_uses_ticker_identity():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = AssetRepository(session)
        a = repo.upsert_asset(ticker="abcd3", asset_type="stock", sector="Finance")
        b = repo.upsert_asset(ticker="ABCD3", asset_type="stock", name="Empresa")
        session.commit()
        assert a.id == b.id
        assert b.ticker == "ABCD3"
        assert b.name == "Empresa"
        assert b.sector == "Finance"

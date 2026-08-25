from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from investment_engine.core.instruments import is_supported_ticker, ticker_exclusion_reason
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.core.repositories.portfolio import PortfolioRepository
from investment_engine.data.ingestion.pipeline import MarketIngestionPipeline
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetORM


def test_b3_catalog_keeps_economic_assets_and_rejects_operational_duplicates():
    supported = (
        ("PETR4", "stock"), ("TAEE11", "stock"),
        ("MXRF11", "fii"), ("BOVA11", "etf"),
        ("NVDC34", "bdr"), ("SPYI39", "bdr"), ("WIN1!", "future"),
    )
    for ticker, asset_type in supported:
        assert is_supported_ticker(ticker, asset_type), (ticker, asset_type)

    excluded = {
        ("PETR4F", "stock"): "fractional_market_duplicate",
        ("BOVA11F", "etf"): "fractional_market_duplicate",
        ("NVDC34F", "bdr"): "fractional_market_duplicate",
        ("PETR4M", "stock"): "special_large_lot_book",
        ("PETR4R", "stock"): "special_large_lot_book",
        ("PETR4Q", "stock"): "special_large_lot_book",
        ("PETR4B", "stock"): "organized_otc_variant",
        ("ABCD1", "stock"): "subscription_right_or_receipt",
        ("ABCD10", "stock"): "subscription_right_or_receipt",
        ("WINQ26", "future"): "duplicate_future_maturity",
    }
    for (ticker, asset_type), reason in excluded.items():
        assert ticker_exclusion_reason(ticker, asset_type) == reason


def test_legacy_noise_is_hidden_and_deactivated_without_deleting_history():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        regular = AssetORM(ticker="PETR4", asset_type="stock")
        fractional = AssetORM(ticker="PETR4F", asset_type="stock")
        session.add_all([
            regular,
            fractional,
            AssetORM(ticker="ABCD1", asset_type="stock"),
            AssetORM(ticker="WIN1!", asset_type="future"),
            AssetORM(ticker="WINQ26", asset_type="future"),
        ])
        portfolio_repo = PortfolioRepository(session)
        portfolio = portfolio_repo.create_portfolio(owner_email="owner@example.com", name="Principal")
        portfolio_repo.upsert_position(portfolio, regular, quantity=100, average_price=10)
        portfolio_repo.upsert_position(portfolio, fractional, quantity=20, average_price=10)
        session.commit()
        repo = AssetRepository(session)
        assert [asset.ticker for asset in repo.list_assets(limit=100)] == ["PETR4", "WIN1!"]
        assert repo.get_by_ticker("PETR4F") is None
        assert [asset.ticker for _position, asset in portfolio_repo.positions(portfolio.id)] == ["PETR4"]
        removed = repo.deactivate_unsupported_assets()
        assert {item["ticker"] for item in removed} == {"PETR4F", "ABCD1", "WINQ26"}
        session.commit()
        all_rows = list(session.scalars(select(AssetORM)))
        assert len(all_rows) == 5
        assert all(not asset.is_active for asset in all_rows if asset.ticker in {"PETR4F", "ABCD1", "WINQ26"})


class _Provider:
    def __init__(self, rows):
        self.rows = rows

    def fetch(self, *_args, **_kwargs):
        return list(self.rows)


def _technical(ticker):
    return {
        "ticker": ticker, "name": ticker, "exchange": "BMFBOVESPA",
        "close": 10, "high": 11, "low": 9, "rsi14": 50,
    }


def test_pipeline_never_persists_fractional_or_duplicate_future_symbols():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        pipeline = MarketIngestionPipeline(
            session,
            stock_provider=_Provider([]), fii_provider=_Provider([]),
            technical_provider=_Provider([]),
        )
        groups = {
            "fund": [_technical("BOVA11"), _technical("BOVA11F")],
            "dr": [_technical("NVDC34"), _technical("NVDC34F")],
            "futures": [_technical("WIN1!"), _technical("WINQ26")],
        }
        pipeline.technical_provider = type("Grouped", (), {
            "fetch": lambda _self, asset_type, **_kwargs: groups[asset_type],
        })()
        summary = pipeline.ingest_other_b3()
        session.commit()
        assert summary.rows_received == 6
        assert summary.rows_valid == 3
        assert [asset.ticker for asset in AssetRepository(session).list_assets(limit=100)] == [
            "BOVA11", "NVDC34", "WIN1!",
        ]

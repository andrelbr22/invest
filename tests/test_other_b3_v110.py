from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from investment_engine.data.ingestion.pipeline import MarketIngestionPipeline
from investment_engine.data.providers.tradingview import TV_COLUMNS, TradingViewScannerProvider
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetORM, TechnicalSnapshotORM
from investment_engine.core.repositories.assets import AssetRepository


class OtherB3Provider:
    def fetch(self, asset_type="stock", *, type_specs=None):
        rows = {
            "fund": [{"ticker": "BOVA11", "name": "ETF Ibovespa", "close": 120, "daily_liquidity": 10_000_000}],
            "dr": [{"ticker": "NVDC34", "name": "NVIDIA BDR", "close": 15, "daily_liquidity": 5_000_000}],
            "futures": [{"ticker": "WIN1!", "name": "Mini Ibovespa futuro", "close": 130_000, "daily_liquidity": 20_000_000}],
        }
        assert type_specs == ["etf"] if asset_type == "fund" else type_specs is None
        return rows.get(asset_type, [])


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_other_b3_catalog_keeps_etf_bdr_and_future_as_separate_types():
    with make_session() as session:
        result = MarketIngestionPipeline(session, technical_provider=OtherB3Provider()).ingest_other_b3()
        session.commit()
        assets = list(session.scalars(select(AssetORM).order_by(AssetORM.ticker)))
        assert result.rows_valid == 3
        assert {row.ticker: row.asset_type for row in assets} == {"BOVA11": "etf", "NVDC34": "bdr", "WIN1!": "future"}
        assert len(list(session.scalars(select(TechnicalSnapshotORM)))) == 3
        assert len(AssetRepository(session).latest_universe("other_b3")) == 3


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class CaptureHttp:
    def __init__(self):
        self.request = None

    def post(self, url, json):
        self.request = {"url": url, "json": json}
        values = {column: None for column in TV_COLUMNS}
        values.update({"name": "BOVA11", "description": "ETF Ibovespa", "type": "fund", "typespecs": ["etf"], "close": 120})
        return FakeResponse({"data": [{"d": [values[column] for column in TV_COLUMNS]}]})


def test_tradingview_etf_query_uses_type_specs_and_preserves_instrument_metadata():
    http = CaptureHttp()
    rows = TradingViewScannerProvider(http).fetch("fund", type_specs=["etf"])
    assert http.request["json"]["filter"] == [
        {"left": "type", "operation": "equal", "right": "fund"},
        {"left": "typespecs", "operation": "has", "right": ["etf"]},
    ]
    assert rows[0]["ticker"] == "BOVA11"
    assert rows[0]["instrument_type"] == "fund"
    assert rows[0]["type_specs"] == ["etf"]

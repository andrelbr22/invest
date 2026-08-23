from datetime import datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from investment_engine.data.ingestion.pipeline import MarketIngestionPipeline
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetORM, FundamentalSnapshotORM, TechnicalSnapshotORM, IngestionRunORM


class FakeStockProvider:
    def fetch(self):
        return [
            {
                "ticker": "TEST3", "price": 20.0, "pe": 10.0, "pbv": 1.2, "dividend_yield_pct": 6.0,
                "ev_ebitda": 5.0, "ebit_margin_pct": 15.0, "net_margin_pct": 12.0, "current_ratio": 1.5,
                "roe_pct": 18.0, "gross_debt_to_equity": 0.4, "revenue_cagr_5y_pct": 7.0,
            }
        ]


class FakeFiiProvider:
    def fetch(self):
        return [
            {
                "ticker": "TEST11", "segment": "Logística", "price": 100.0, "pbv": 0.95,
                "dividend_yield_pct": 10.0, "ffo_yield_pct": 9.0, "cap_rate_pct": 8.0,
                "vacancy_pct": None, "daily_liquidity": 2_000_000.0,
            }
        ]


class FakeTechnicalProvider:
    def fetch(self, asset_type="stock"):
        ticker = "TEST3" if asset_type == "stock" else "TEST11"
        return [{
            "ticker": ticker, "score_tv": 0.55, "signal_tv": "strong_buy", "market_cap": 20_000_000_000,
            "daily_liquidity": 5_000_000, "sector": "Finance", "sma20": 19, "sma50": 18, "sma200": 17,
            "sma20_1w": 18, "sma50_1w": 17, "sma20_1m": 16, "sma50_1m": 15,
            "high": 21, "low": 19, "close": 20, "rsi14": 58, "bb_lower": 17, "bb_upper": 22,
        }]


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_full_pipeline_persists_assets_and_snapshots():
    with make_session() as session:
        pipeline = MarketIngestionPipeline(session, FakeStockProvider(), FakeFiiProvider(), FakeTechnicalProvider())
        ref = datetime(2026, 8, 21, tzinfo=timezone.utc)
        stock_summary = pipeline.ingest_stocks(reference_date=ref)
        tech_summary = pipeline.ingest_technicals("stock")
        fii_summary = pipeline.ingest_fiis(reference_date=ref)
        session.commit()

        assert stock_summary.rows_valid == 1
        assert tech_summary.rows_valid == 1
        assert fii_summary.rows_valid == 1
        assets = list(session.scalars(select(AssetORM).order_by(AssetORM.ticker)))
        assert [a.ticker for a in assets] == ["TEST11", "TEST3"]
        assert session.scalar(select(FundamentalSnapshotORM).where(FundamentalSnapshotORM.asset_id == assets[0].id)).vacancy_pct is None
        assert session.scalar(select(TechnicalSnapshotORM).where(TechnicalSnapshotORM.asset_id == assets[1].id)).signal_tv == "strong_buy"
        assert len(list(session.scalars(select(IngestionRunORM)))) == 3


def test_same_reference_date_is_upserted_not_duplicated():
    with make_session() as session:
        pipeline = MarketIngestionPipeline(session, FakeStockProvider(), FakeFiiProvider(), FakeTechnicalProvider())
        ref = datetime(2026, 8, 21, tzinfo=timezone.utc)
        pipeline.ingest_stocks(reference_date=ref)
        pipeline.ingest_stocks(reference_date=ref)
        session.commit()
        rows = list(session.scalars(select(FundamentalSnapshotORM)))
        assert len(rows) == 1

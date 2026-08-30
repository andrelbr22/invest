from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from investment_engine.api.app import MarketSyncRequest
from investment_engine.core.instruments import is_supported_ticker
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.data.ingestion.pipeline import MarketIngestionPipeline
from investment_engine.data.providers.fundamentus import FundamentusFiiProvider
from investment_engine.infrastructure.db.models import AssetORM, Base


ROOT = Path(__file__).resolve().parents[1]


class _Response:
    text = """<table id="tabelaResultado"><tr><th>Papel</th></tr>
    <tr><td>XPML11</td><td>Shoppings</td><td>99,00</td><td>8,27%</td><td>9,95%</td>
    <td>0,91</td><td>6.366.500.000</td><td>16.663.800</td><td>14</td><td>5.963,74</td>
    <td>591,65</td><td>9,92%</td><td>4,50%</td></tr></table>"""


class _Http:
    def get(self, _url):
        return _Response()


def test_xpml11_is_supported_and_fii_provider_imports_it():
    rows = FundamentusFiiProvider(http=_Http()).fetch()
    assert is_supported_ticker("XPML11", "fii")
    assert rows[0]["ticker"] == "XPML11"


def test_catalog_sync_can_skip_heavier_technical_enrichment():
    request = MarketSyncRequest(asset_type="fii", include_technicals=False)
    assert request.include_technicals is False


def test_owner_interface_exposes_catalog_counts_and_actions():
    index = (ROOT / "investment_engine" / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'data-tab="data">Dados de mercado' in index
    assert 'api("/data/catalog-summary")' in script
    assert 'data-refresh-groups="catalog">Atualizar catálogo' in script
    assert 'data-refresh-groups="fundamentals">Atualizar fundamentos e notas' in script


def test_other_b3_pipeline_reclassifies_legacy_aura33_without_duplicate():
    class Technicals:
        def fetch(self, asset_type, *, type_specs=None):
            if asset_type != "dr":
                return []
            return [{"ticker": "AURA33", "name": "Aura Minerals", "score_tv": .2,
                     "sma20": 30, "sma50": 29, "sma200": 25, "rsi14": 55,
                     "close": 31, "daily_liquidity": 100000}]

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    legacy = AssetORM(ticker="AURA33", asset_type="stock", is_active=False)
    session.add(legacy)
    session.commit()
    repo = AssetRepository(session)
    now = datetime.now(timezone.utc)
    repo.upsert_fundamentals(
        legacy, source="legacy", reference_date=now, retrieved_at=now,
        status="valid", quality_score=100, data={"price": 30}, raw_payload={},
    )
    session.commit()
    result = MarketIngestionPipeline(session, technical_provider=Technicals()).ingest_other_b3()
    session.commit()

    row = AssetRepository(session).get_by_ticker("AURA33")
    assert result.rows_valid == 1
    assert row.asset_type == "bdr"
    assert row.is_active is True
    assert session.scalar(select(func.count(AssetORM.id))) == 1

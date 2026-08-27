from pathlib import Path

from investment_engine.api.app import MarketSyncRequest
from investment_engine.core.instruments import is_supported_ticker
from investment_engine.data.providers.fundamentus import FundamentusFiiProvider


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
    assert 'data-market-sync="fii" data-technicals="false"' in script

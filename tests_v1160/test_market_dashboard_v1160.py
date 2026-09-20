from datetime import datetime, timezone

from investment_engine.data.providers.market_dashboard import MarketDashboardService


class Response:
    def __init__(self, *, payload=None, text=""):
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")

    def json(self):
        return self._payload


def test_focus_selic_returns_current_and_next_year():
    class Http:
        def get(self, url, params=None, **_kwargs):
            if "bcdata.sgs" in url:
                return Response(payload=[{"data": "26/08/2026", "valor": "14,00"}])
            assert params["$filter"] == "startswith(Indicador,'Sel')"
            return Response(payload={"value": [
                {"Indicador": "Selic", "Data": "2026-08-21", "DataReferencia": "2026", "Mediana": 13.75, "baseCalculo": 0},
                {"Indicador": "Selic", "Data": "2026-08-21", "DataReferencia": "2027", "Mediana": 12.0, "baseCalculo": 0},
            ]})

    result = MarketDashboardService(http=Http(), now=datetime(2026, 8, 26, tzinfo=timezone.utc)).selic()
    assert result["current"] == 14.0
    assert result["current_year"]["value"] == 13.75
    assert result["next_year"]["value"] == 12.0
    assert "CDI" in result["projection_note"]


def test_interest_curve_accepts_declared_encoding_in_decoded_page():
    html = """<?xml version="1.0" encoding="iso-8859-1"?>
    <html><body>26/08/2026<table><tr><th>Vértice</th><th>ETTJ PRE</th><th>ETTJ IPCA</th><th>Inflação</th></tr>
    <tr><td>252</td><td>14,20</td><td>7,10</td><td>6,63</td></tr></table></body></html>"""

    class Http:
        def get(self, *_args, **_kwargs):
            return Response(text=html)

    result = MarketDashboardService(http=Http()).interest_curve()
    assert result["as_of"] == "2026-08-26"
    assert result["points"] == [{
        "business_days": 252, "years": 1.0, "nominal_rate": 14.2,
        "real_rate": 7.1, "implied_inflation": 6.63,
    }]


def test_fixed_income_contract_has_only_monthly_and_annual_returns():
    xml = """<?xml version='1.0' encoding='ISO-8859-1'?>
    <IMA>
      <FAMILIA INDICE='IRF-M'><TOTAIS DT_REF='26/08/2026'><TOTAL T_Var_Mensal='1,1132' T_Var_Ult12M='12,4377'/></TOTAIS></FAMILIA>
      <FAMILIA INDICE='IMA-B'><TOTAIS DT_REF='26/08/2026'><TOTAL T_Var_Mensal='1,8099' T_Var_Ult12M='11,4086'/></TOTAIS></FAMILIA>
    </IMA>"""

    class Http:
        def get(self, *_args, **_kwargs):
            return Response(text=xml)

    service = MarketDashboardService(http=Http())
    service.cdi = lambda: {"label": "CDI", "monthly_return_pct": 1.0, "annual_return_pct": 13.0}
    rows = service.fixed_income()
    assert rows[1]["monthly_return_pct"] == 1.8099
    assert rows[1]["annual_return_pct"] == 11.4086
    assert rows[2]["monthly_return_pct"] == 1.1132
    assert rows[2]["annual_return_pct"] == 12.4377
    assert all(row["proxy"] is False for row in rows[1:])

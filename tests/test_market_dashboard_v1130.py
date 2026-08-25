from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from investment_engine.data.providers.market_dashboard import (
    MarketDashboardService,
    b3_holidays,
    compound_percentages,
    parse_number,
    series_snapshot,
    us_exchange_holidays,
)
from investment_engine.data.providers.prices import YahooPriceProvider
from investment_engine.core.repositories.news_cache import NewsCacheRepository
from investment_engine.infrastructure.db.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
import importlib


ROOT = Path(__file__).resolve().parents[1]


def test_market_number_and_compounding_helpers():
    assert parse_number("1.234,56%") == pytest.approx(1234.56)
    assert parse_number("1,234.56") == pytest.approx(1234.56)
    assert compound_percentages([1.0, 1.0], 2) == pytest.approx(2.01)
    assert compound_percentages([1.0], 2) is None


def test_market_snapshot_uses_standard_trading_windows():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars = [
        {"timestamp": start + timedelta(days=index), "adjusted_close": 100 + index}
        for index in range(260)
    ]
    snapshot = series_snapshot(bars)
    assert snapshot["current"] == 359
    assert snapshot["variations"]["1d"] == pytest.approx((359 / 358 - 1) * 100)
    assert snapshot["variations"]["1w"] == pytest.approx((359 / 354 - 1) * 100)
    assert snapshot["variations"]["1m"] == pytest.approx((359 / 338 - 1) * 100)
    assert snapshot["variations"]["1y"] == pytest.approx((359 / 107 - 1) * 100)


def test_crypto_symbols_are_not_mistaken_for_b3_tickers():
    assert YahooPriceProvider.symbol("BTC-USD") == "BTC-USD"
    assert YahooPriceProvider.symbol("ETH-BRL") == "ETH-BRL"
    assert YahooPriceProvider.symbol("IEUR") == "IEUR"
    assert YahooPriceProvider.symbol("PETR4") == "PETR4.SA"


def test_calculated_exchange_holidays_include_requested_markets():
    b3 = dict(b3_holidays(2026))
    nyse = dict(us_exchange_holidays(2026))
    assert b3[date(2026, 9, 7)] == "Independência do Brasil"
    assert b3[date(2026, 11, 20)] == "Consciência Negra"
    assert nyse[date(2026, 11, 26)] == "Thanksgiving"


def test_focus_accepts_numeric_years_and_exposes_cdi_reference_note():
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Http:
        def get(self, url, params=None):
            if "bcdata.sgs.432" in url:
                return Response([{"data": "24/08/2026", "valor": "12,50"}])
            return Response({"value": [
                {"Indicador": "Selic", "DataReferencia": 2026, "Mediana": 12.25, "Data": "2026-08-21", "baseCalculo": 0},
                {"Indicador": "Selic", "DataReferencia": "2027", "Mediana": 10.50, "Data": "2026-08-21", "baseCalculo": 0},
            ]})

    result = MarketDashboardService(http=Http(), now=datetime(2026, 8, 24, tzinfo=timezone.utc)).selic()

    assert result["current_year"]["value"] == pytest.approx(12.25)
    assert result["next_year"]["value"] == pytest.approx(10.50)
    assert "Focus pesquisa a Selic" in result["projection_note"]


def test_bls_calendar_has_official_fallback_for_cpi_and_payroll():
    class OfflineHttp:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("fonte temporariamente indisponível")

    service = MarketDashboardService(http=OfflineHttp(), now=datetime(2026, 8, 25, tzinfo=timezone.utc))
    events = service._bls_calendar()

    assert next(item for item in events if item["category"] == "Payroll dos EUA")["date"] == "2026-09-04"
    assert next(item for item in events if item["category"] == "CPI dos EUA")["date"] == "2026-09-11"


def test_super_wednesday_keeps_copom_and_fed_separate_and_highlighted():
    service = MarketDashboardService(now=datetime(2026, 8, 25, tzinfo=timezone.utc))
    service._bls_calendar = lambda: []

    events = service.calendar()
    same_day = [item for item in events if item["date"] == "2026-09-16"]

    assert {item["category"] for item in same_day} == {"Decisão do Copom", "Decisão do Fed"}
    assert all("SUPER QUARTA" in item["observation"] for item in same_day)
    assert all(item["highlight"] == "super_wednesday" for item in same_day)


def test_dashboard_build_is_resilient_when_one_source_fails():
    service = MarketDashboardService(now=datetime(2026, 8, 24, tzinfo=timezone.utc))
    service.selic = lambda: {"current": 10.0}
    service.interest_curve = lambda: {"points": [{"years": 1.0}]}
    service.fixed_income = lambda: [{"label": "CDI"}]
    service.quoted_markets = lambda: {"brazil": [{"label": "IBOV"}]}
    service.crypto = lambda: [{"label": "Bitcoin"}]
    service.fx = lambda: [{"label": "Dólar / Real"}]
    service.inflation = lambda: (_ for _ in ()).throw(RuntimeError("fonte fora do ar"))
    service.us_rates = lambda: {"ten_year": 4.0}
    service.calendar = lambda: [{"category": "Copom"}]

    result = service.build()

    assert result["status"] == "partial"
    assert result["quoted"]["brazil"][0]["label"] == "IBOV"
    assert result["inflation"] == []
    assert any("inflation" in warning for warning in result["warnings"])


def test_market_dashboard_is_a_first_class_compact_module():
    ui = (ROOT / "examples" / "streamlit_v15_integrated.py").read_text(encoding="utf-8")
    api = (ROOT / "investment_engine" / "api" / "app.py").read_text(encoding="utf-8")
    provider = (ROOT / "investment_engine" / "data" / "providers" / "market_dashboard.py").read_text(encoding="utf-8")
    assert '"dashboard":"🌐 Painel de Mercado"' in ui
    assert "Curva de juros brasileira" in ui
    assert "Ouro, prata e petróleo" in ui
    assert "CDI projetado" in ui
    assert "SUPER QUARTA" in ui
    assert '@app.post("/market-dashboard/ensure")' in api
    assert "MarketDashboardService" in provider


def test_shared_dashboard_worker_persists_the_snapshot(monkeypatch):
    api_app = importlib.import_module("investment_engine.api.app")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session(engine) as session:
        row, scheduled = NewsCacheRepository(session).request_refresh(
            owner_email="market-dashboard@system.local",
            cache_kind="market_dashboard", cache_key="main",
            trigger="automatic",
        )
        assert scheduled is True
        session.commit()
        cache_id = str(row.id)

    class _Dashboard:
        def build(self):
            return {"status": "complete", "selic": {"current": 10.5}}

    monkeypatch.setattr(api_app, "get_session_factory", lambda: factory)
    monkeypatch.setattr(api_app, "_MARKET_DASHBOARD", _Dashboard())
    api_app._run_market_dashboard_refresh(cache_id)

    with factory() as session:
        stored = NewsCacheRepository(session).get(
            owner_email="market-dashboard@system.local",
            cache_kind="market_dashboard", cache_key="main",
        )
        assert stored.status == "completed"
        assert stored.result_json["selic"]["current"] == 10.5

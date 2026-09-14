from __future__ import annotations

import io
import threading
import time as time_module
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from investment_engine.core.jobs import handlers
from investment_engine.core.jobs.schedules import REFRESH_SCHEDULES, refresh_status
from investment_engine.core.investor_events.service import DataQualityService
from investment_engine.core.repositories.investor_events import InvestorEventsRepository
from investment_engine.core.repositories.economic_series import SharedSnapshotRepository
from investment_engine.data.providers.official_events import (
    ANBIMA_IMA_RESULTS_URL,
    CVM_IPE_CKAN_API,
    AnbimaImaHistoryProvider,
    B3CorporateEventsProvider,
    CvmRelevantFactsProvider,
    OfficialCalendarProvider,
)
from investment_engine.infrastructure.config import settings
from investment_engine.infrastructure.db.models import (
    Base,
    AssetORM,
    EconomicSeriesORM,
    EconomicSeriesPointORM,
    SharedSnapshotORM,
)


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class ContentResponse:
    def __init__(self, content):
        self.content = content


class AnbimaHttp:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return JsonResponse({"access_token": "access-token-for-test", "expires_in": 3600})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        requested = (kwargs.get("params") or {}).get("data") or "2026-09-11"
        return JsonResponse({
            "content": [
                {
                    "indice": "IMA-B", "data_referencia": requested,
                    "numero_indice": "10500,123456", "variacao_diaria": "0,1234",
                },
                {
                    "indice": "IRF-M", "data_referencia": requested,
                    "numero_indice": "9876.543210", "variacao_ult12m": "12,45",
                },
                {"indice": "IMA-GERAL", "data_referencia": requested, "numero_indice": "1"},
            ]
        })


def test_cvm_annual_zip_is_iterated_without_materializing_the_csv():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "ipe_cia_aberta_2026.csv",
            "Categoria;CNPJ_Companhia;Data_Entrega;Link_Download\n"
            "Fato Relevante;00.000.000/0001-00;11/09/2026;https://dados.cvm.gov.br/doc.pdf\n",
        )

    rows = CvmRelevantFactsProvider._csv_rows(buffer.getvalue())
    assert iter(rows) is rows
    assert list(rows)[0]["Categoria"] == "Fato Relevante"


def _cvm_zip(year: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"ipe_cia_aberta_{year}.csv",
            "Categoria;CNPJ_Companhia;Nome_Companhia;Data_Entrega;Link_Download\n"
            f"Fato Relevante;00.000.000/0001-00;Companhia Teste;11/09/{year};"
            f"https://dados.cvm.gov.br/documento-{year}.pdf\n",
        )
    return buffer.getvalue()


def test_cvm_discovers_current_resources_from_the_official_ckan_catalog():
    class FakeHttp:
        def __init__(self):
            self.urls = []

        def get(self, url, **_kwargs):
            self.urls.append(url)
            if url == CVM_IPE_CKAN_API:
                return JsonResponse({
                    "success": True,
                    "result": {"resources": [{
                        "format": "ZIP",
                        "url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_2026.zip",
                    }]},
                })
            return ContentResponse(_cvm_zip(2026))

    http = FakeHttp()
    result = CvmRelevantFactsProvider(http=http).fetch(years=[2026])

    assert result["resource_catalog_discovered"] is True
    assert result["errors"] == []
    assert len(result["items"]) == 1
    assert http.urls[0] == CVM_IPE_CKAN_API


def test_cvm_reports_a_missing_current_resource_without_guessing_an_url():
    class FakeHttp:
        def __init__(self):
            self.urls = []

        def get(self, url, **_kwargs):
            self.urls.append(url)
            if url == CVM_IPE_CKAN_API:
                return JsonResponse({
                    "success": True,
                    "result": {"resources": [{
                        "format": "ZIP",
                        "url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_2025.zip",
                    }]},
                })
            return ContentResponse(_cvm_zip(2025))

    http = FakeHttp()
    result = CvmRelevantFactsProvider(http=http).fetch(years=[2025, 2026])

    assert len(result["items"]) == 1
    assert result["errors"] == [{"year": 2026, "error": "cvm_ipe_resource_not_published"}]
    assert all("ipe_cia_aberta_2026.zip" not in url for url in http.urls)


def test_b3_portfolio_batch_is_not_silently_limited_to_one_hundred(monkeypatch):
    provider = B3CorporateEventsProvider()
    requested = []

    def fetch_ticker(ticker):
        requested.append(ticker)
        return {"items": []}

    monkeypatch.setattr(provider, "fetch_ticker", fetch_ticker)
    tickers = [f"AT{i:04d}" for i in range(137)]
    result = provider.fetch(tickers, max_assets=150)

    assert requested == tickers
    assert result["requested_total"] == 137
    assert result["requested"] == 137
    assert result["truncated"] is False
    assert result["not_processed"] == 0


def test_b3_safety_limit_is_explicit_when_a_batch_is_truncated(monkeypatch):
    provider = B3CorporateEventsProvider()
    monkeypatch.setattr(provider, "fetch_ticker", lambda ticker: {"items": []})
    result = provider.fetch([f"AT{i:04d}" for i in range(12)], max_assets=5)

    assert result["requested_total"] == 12
    assert result["requested"] == 5
    assert result["safety_limit"] == 5
    assert result["truncated"] is True
    assert result["not_processed"] == 7


def test_b3_filters_issuer_events_by_share_class_and_never_assigns_ambiguous_rows():
    source = "https://sistemaswebb3-listados.b3.com.br/eventos"
    common = {
        "corporateAction": "Dividendo", "lastDatePrior": "04/09/2026",
        "datePayment": "30/09/2026", "valueCash": "1,25",
    }

    preferred = B3CorporateEventsProvider.normalize_record(
        {**common, "typeStock": "PN N2", "isinCode": "BRPETRACNPR6"},
        ticker="PETR4", source_url=source,
    )
    ordinary = B3CorporateEventsProvider.normalize_record(
        {**common, "typeStock": "ON NM", "isinCode": "BRPETRACNOR9"},
        ticker="PETR4", source_url=source,
    )
    ambiguous = B3CorporateEventsProvider.normalize_record(
        {key: value for key, value in common.items() if key != "typeStock"},
        ticker="PETR4", source_url=source,
    )

    assert preferred is not None
    assert preferred["event_type"] == "dividend"
    assert preferred["ticker"] == "PETR4"
    assert ordinary is None
    assert ambiguous is None


def test_b3_ex_date_uses_next_exchange_business_day_only_for_official_cum_field():
    source = "https://sistemaswebb3-listados.b3.com.br/eventos"
    official = B3CorporateEventsProvider.normalize_record(
        {
            "corporateAction": "Juros sobre Capital Próprio", "typeStock": "PN",
            # Friday followed by Independence Day on Monday.
            "lastDatePrior": "04/09/2026", "valueCash": "0,50",
        },
        ticker="PETR4", source_url=source,
    )
    generic = B3CorporateEventsProvider.normalize_record(
        {
            "corporateAction": "Dividendo", "typeStock": "PN",
            "negocios com ate": "04/09/2026", "valueCash": "0,50",
        },
        ticker="PETR4", source_url=source,
    )

    assert official["last_cum_date"] == date(2026, 9, 4)
    assert official["ex_date"] == date(2026, 9, 8)
    assert generic["last_cum_date"] == date(2026, 9, 4)
    assert generic["ex_date"] is None


def test_cvm_ticker_mapping_uses_cvm_code_when_catalog_has_no_cnpj():
    factory, _engine = _isolated_session_factory()
    with factory() as session:
        asset = AssetORM(
            ticker="PETR4", asset_type="stock", is_active=True,
            name="Petróleo Brasileiro Petrobras S.A.",
            metadata_json={},
        )
        session.add(asset)
        session.flush()
        # The B3 corporate-action adapter progressively supplies this strong
        # identifier even though the original catalog ingestion has no CNPJ.
        InvestorEventsRepository(session).update_asset_issuer_metadata(
            asset, {"cvm_code": "009512", "issuer_name": "Petrobras"},
        )
        session.commit()
        mapping = InvestorEventsRepository(session).asset_issuer_mapping()

    item = CvmRelevantFactsProvider.normalize_record(
        {
            "Categoria": "Fato Relevante", "CNPJ_Companhia": "",
            "Codigo_CVM": "9512", "Nome_Companhia": "PETROLEO BRASILEIRO S.A. PETROBRAS",
            "Data_Entrega": "11/09/2026", "Link_Download": "https://dados.cvm.gov.br/petr.pdf",
        },
        source_url="https://dados.cvm.gov.br/ipe.zip",
        issuer_mapping=mapping,
    )

    assert item is not None
    assert item["tickers"] == ["PETR4"]
    assert item["metadata"]["ticker_mapping_method"] == "cvm_code"


def test_anbima_provider_authenticates_once_and_normalizes_only_target_indices():
    http = AnbimaHttp()
    fixed_now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
    provider = AnbimaImaHistoryProvider(
        client_id="client-id", client_secret="client-secret", http=http, now=lambda: fixed_now,
    )

    first = provider.fetch_date(date(2026, 9, 11))
    second = provider.fetch_date(date(2026, 9, 10))

    assert len(http.posts) == 1
    assert len(http.gets) == 2
    assert all(call[0] == ANBIMA_IMA_RESULTS_URL for call in http.gets)
    assert http.gets[0][1]["headers"]["client_id"] == "client-id"
    assert http.gets[0][1]["headers"]["access_token"] == "access-token-for-test"
    assert {item["code"] for item in first["items"]} == {"IMAB", "IRFM"}
    assert {item["reference_period"] for item in second["items"]} == {"2026-09-10"}
    assert next(item for item in first["items"] if item["code"] == "IMAB")["metadata"]["daily_return_pct"] == pytest.approx(0.1234)


def test_anbima_provider_reports_missing_credentials_without_a_network_call():
    http = AnbimaHttp()
    provider = AnbimaImaHistoryProvider(client_id="", client_secret="", http=http)
    with pytest.raises(RuntimeError, match="anbima_credentials_not_configured"):
        provider.fetch_date()
    assert http.posts == []
    assert http.gets == []


def test_anbima_range_pins_cursor_to_first_gap_and_fetches_with_bounded_parallelism():
    class GapHttp(AnbimaHttp):
        def __init__(self):
            super().__init__()
            self.lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def get(self, url, **kwargs):
            requested = (kwargs.get("params") or {}).get("data")
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                time_module.sleep(0.02)
                if requested == "2026-09-09":
                    raise ConnectionError("temporary official source failure")
                return super().get(url, **kwargs)
            finally:
                with self.lock:
                    self.active -= 1

    http = GapHttp()
    provider = AnbimaImaHistoryProvider(
        client_id="client-id", client_secret="client-secret", http=http,
        now=lambda: datetime(2026, 9, 14, tzinfo=timezone.utc), range_workers=3,
    )
    result = provider.fetch_range(date(2026, 9, 8), date(2026, 9, 11), max_calendar_days=10)

    assert result["next_date"] == "2026-09-09"
    assert result["complete_through"] == "2026-09-08"
    assert result["attempted_through"] == "2026-09-11"
    assert result["successful_trading_days"] == 3
    assert result["errors"][0]["date"] == "2026-09-09"
    assert http.max_active > 1
    assert http.max_active <= 3


def test_anbima_range_treats_a_missing_target_index_as_a_gap():
    class IncompleteHttp(AnbimaHttp):
        def get(self, url, **kwargs):
            response = super().get(url, **kwargs)
            requested = (kwargs.get("params") or {}).get("data")
            if requested == "2026-09-10":
                response.payload["content"] = [response.payload["content"][0]]
            return response

    provider = AnbimaImaHistoryProvider(
        client_id="client-id", client_secret="client-secret",
        http=IncompleteHttp(), range_workers=2,
    )
    result = provider.fetch_range(date(2026, 9, 9), date(2026, 9, 11), max_calendar_days=10)

    assert result["next_date"] == "2026-09-10"
    assert result["complete_through"] == "2026-09-09"
    assert result["errors"] == [{
        "date": "2026-09-10",
        "error": "anbima_expected_indices_missing",
        "missing_codes": ["IRFM"],
    }]


def test_anbima_history_has_an_asynchronous_schedule():
    schedule = REFRESH_SCHEDULES["ima_history"]
    assert schedule.job_type == "anbima_ima_history_refresh"
    assert schedule.snapshot_key == "official-history:anbima-ima"
    assert schedule.weekdays_only is True


def _isolated_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine), engine


def test_anbima_history_handler_persists_transparent_unavailable_state(monkeypatch):
    factory, engine = _isolated_session_factory()
    monkeypatch.setattr(handlers, "get_session_factory", lambda: factory)
    monkeypatch.setattr(settings, "anbima_client_id", "")
    monkeypatch.setattr(settings, "anbima_client_secret", "")

    result = handlers.handle_anbima_ima_history_refresh({})

    assert result["status"] == "unavailable"
    assert result["reason"] == "anbima_credentials_not_configured"
    with Session(engine) as session:
        snapshot = session.scalar(select(SharedSnapshotORM).where(
            SharedSnapshotORM.snapshot_key == "official-history:anbima-ima",
        ))
        assert snapshot.payload_json["status"] == "unavailable"
        status = refresh_status(session, "ima_history", snapshot.as_of + timedelta(minutes=1))
        assert status["status"] == "unavailable"
        assert status["last_error_code"] == "anbima_credentials_not_configured"


def test_anbima_history_handler_incrementally_upserts_official_levels(monkeypatch):
    factory, engine = _isolated_session_factory()
    monkeypatch.setattr(handlers, "get_session_factory", lambda: factory)
    monkeypatch.setattr(settings, "anbima_client_id", "configured-client")
    monkeypatch.setattr(settings, "anbima_client_secret", "configured-secret")

    observed = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)

    def item(code, name, value):
        return {
            "code": code, "name": name, "observed_at": observed,
            "reference_period": observed.date().isoformat(), "value": value,
            "source_payload_hash": f"hash-{code}", "metadata": {"official": True},
        }

    class FakeProvider:
        def __init__(self, **kwargs):
            assert kwargs["client_id"] == "configured-client"

        def fetch_range(self, start, end, *, max_calendar_days):
            return {
                "items": [item("IMAB", "IMA-B", "10500.25")], "errors": [],
                "start": start.isoformat(), "end": end.isoformat(),
                "next_date": (end + timedelta(days=1)).isoformat(),
            }

        def fetch_date(self, reference_date=None):
            return {"items": [item("IRFM", "IRF-M", "9988.75")]}

    monkeypatch.setattr(handlers, "AnbimaImaHistoryProvider", FakeProvider)
    result = handlers.handle_anbima_ima_history_refresh({
        "start_date": date.today().isoformat(), "batch_days": 5,
    })

    assert result["status"] == "complete"
    assert result["created"] == 2
    assert result["received_by_series"] == {"IMAB": 1, "IRFM": 1}
    with Session(engine) as session:
        assert session.scalar(select(func.count(EconomicSeriesORM.id))) == 2
        assert session.scalar(select(func.count(EconomicSeriesPointORM.id))) == 2


def test_anbima_history_handler_does_not_claim_complete_or_advance_after_a_gap(monkeypatch):
    factory, _engine = _isolated_session_factory()
    monkeypatch.setattr(handlers, "get_session_factory", lambda: factory)
    monkeypatch.setattr(settings, "anbima_client_id", "configured-client")
    monkeypatch.setattr(settings, "anbima_client_secret", "configured-secret")
    today = date.today()
    failed_day = today - timedelta(days=2)

    class FakeProvider:
        def __init__(self, **_kwargs):
            pass

        def fetch_range(self, start, end, *, max_calendar_days):
            return {
                "items": [],
                "errors": [{"date": failed_day.isoformat(), "error": "Timeout"}],
                "start": start.isoformat(), "end": end.isoformat(),
                "attempted_through": end.isoformat(),
                "complete_through": (failed_day - timedelta(days=1)).isoformat(),
                "next_date": failed_day.isoformat(),
                "attempted_trading_days": 3, "successful_trading_days": 2,
            }

        def fetch_date(self, reference_date=None):
            return {"items": []}

    monkeypatch.setattr(handlers, "AnbimaImaHistoryProvider", FakeProvider)
    result = handlers.handle_anbima_ima_history_refresh({
        "start_date": (today - timedelta(days=5)).isoformat(), "batch_days": 10,
    })

    assert result["status"] == "partial"
    assert result["history_complete"] is False
    assert result["next_date"] == failed_day.isoformat()
    assert result["history_through"] == (failed_day - timedelta(days=1)).isoformat()
    assert result["attempted_through"] == today.isoformat()


def test_quality_report_preserves_transparent_unavailable_payload_status():
    factory, _engine = _isolated_session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        SharedSnapshotRepository(session).save_valid(
            snapshot_key="official-history:anbima-ima",
            snapshot_kind="official_history",
            payload={
                "status": "unavailable",
                "reason": "anbima_credentials_not_configured",
                "available_series": 0,
            },
            source="ANBIMA Feed • Índices",
            as_of=now,
        )
        session.commit()
        row = next(item for item in DataQualityService(session)._snapshot_sources(now) if item["key"] == "snapshot:ima_history")

    assert row["status"] == "unavailable"
    assert row["last_error_code"] == "anbima_credentials_not_configured"
    assert row["item_count"] == 0


def test_official_calendar_does_not_duplicate_rule_generated_elections_or_holidays():
    class FakeMarketService:
        def calendar(self):
            return [
                {
                    "category": "Eleições", "event": "Evento legado duplicado",
                    "date": "2026-10-04", "source": "Tribunal Superior Eleitoral",
                    "url": "https://www.tse.jus.br/eleicoes/calendario-eleitoral",
                },
                {
                    "category": "Feriado B3", "event": "Feriado legado duplicado",
                    "date": "2026-12-25", "source": "B3", "url": "https://www.b3.com.br/",
                },
                {
                    "category": "Decisão do Fed", "event": "Decisão do FOMC",
                    "date": "2026-09-16", "source": "Federal Reserve",
                    "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                },
            ]

    result = OfficialCalendarProvider(FakeMarketService()).fetch(start_year=2026, years=1)
    titles = [item["title"] for item in result["items"]]

    assert "Evento legado duplicado" not in titles
    assert "Feriado legado duplicado" not in titles
    assert titles.count("Decisão do FOMC") == 1
    assert sum(item["category"] == "Eleições" for item in result["items"]) == 3


def test_official_calendar_preserves_a_merged_super_wednesday_event():
    class FakeMarketService:
        def calendar(self):
            return [{
                "category": "Super Quarta",
                "event": "Super Quarta • decisões de juros no Brasil e nos EUA",
                "date": "2026-09-16",
                "source": "Banco Central do Brasil e Federal Reserve",
                "url": "https://www.bcb.gov.br/controleinflacao/copom",
                "observation": "Copom e FOMC divulgam suas decisões na mesma data.",
            }]

    result = OfficialCalendarProvider(FakeMarketService()).fetch(start_year=2026, years=1)
    super_wednesdays = [item for item in result["items"] if item["category"] == "Super Quarta"]

    assert len(super_wednesdays) == 1
    assert super_wednesdays[0]["official"] is True
    assert super_wednesdays[0]["metadata"]["generation"] == "official_source_adapter"

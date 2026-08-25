from datetime import datetime, timezone
import importlib

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.core.repositories.news_cache import (
    NewsCacheRepository,
    news_cache_dict,
    news_market_date,
)
from investment_engine.core.repositories.portfolio import PortfolioRepository
from investment_engine.infrastructure.db.base import Base


def test_news_market_date_uses_sao_paulo_day():
    assert news_market_date(datetime(2026, 8, 25, 1, 30, tzinfo=timezone.utc)).isoformat() == "2026-08-24"


def test_automatic_news_refresh_is_queued_only_once_per_day_and_manual_can_retry():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = NewsCacheRepository(session)
        first, first_scheduled = repo.request_refresh(
            owner_email="owner@example.com", cache_kind="recommendations",
            cache_key="all", trigger="automatic",
        )
        second, second_scheduled = repo.request_refresh(
            owner_email="owner@example.com", cache_kind="recommendations",
            cache_key="all", trigger="automatic",
        )
        assert first.id == second.id
        assert first_scheduled is True
        assert second_scheduled is False

        repo.mark_running(first)
        repo.mark_completed(first, {"items": [{"title": "Notícia salva"}]})
        manual, manual_scheduled = repo.request_refresh(
            owner_email="owner@example.com", cache_kind="recommendations",
            cache_key="all", trigger="manual", force=True,
        )
        assert manual_scheduled is True
        assert news_cache_dict(manual)["has_data"] is True
        assert manual.result_json["items"][0]["title"] == "Notícia salva"


def test_news_cache_is_isolated_by_user_and_category():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = NewsCacheRepository(session)
        owner_all, _ = repo.request_refresh(
            owner_email="owner@example.com", cache_kind="recommendations",
            cache_key="all", trigger="automatic",
        )
        owner_brazil, _ = repo.request_refresh(
            owner_email="owner@example.com", cache_kind="recommendations",
            cache_key="brazil", trigger="manual",
        )
        other_all, _ = repo.request_refresh(
            owner_email="other@example.com", cache_kind="recommendations",
            cache_key="all", trigger="automatic",
        )
        assert len({owner_all.id, owner_brazil.id, other_all.id}) == 3


def test_background_worker_saves_serializable_portfolio_news_without_blocking_request(monkeypatch):
    api_app = importlib.import_module("investment_engine.api.app")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        asset = AssetRepository(session).upsert_asset(ticker="ABCD3", asset_type="stock", name="Empresa ABCD")
        portfolio = PortfolioRepository(session).create_portfolio(owner_email="owner@example.com", name="Principal")
        PortfolioRepository(session).upsert_position(portfolio, asset, quantity=100, average_price=10)
        row, _ = NewsCacheRepository(session).request_refresh(
            owner_email="owner@example.com", cache_kind="portfolio",
            cache_key=str(portfolio.id), trigger="automatic",
        )
        session.commit()
        cache_id = str(row.id)

    class _News:
        def portfolio_news(self, assets, *, limit_per_asset):
            assert assets == [{"ticker": "ABCD3", "name": "Empresa ABCD"}]
            assert limit_per_asset == 3
            return {
                "assets": [{"ticker": "ABCD3", "items": []}],
                "generated_at": datetime.now(timezone.utc),
            }

    monkeypatch.setattr(api_app, "get_session_factory", lambda: factory)
    monkeypatch.setattr(api_app, "_MARKET_NEWS", _News())
    api_app._run_daily_news_refresh(cache_id)

    with factory() as session:
        stored = NewsCacheRepository(session).get(
            owner_email="owner@example.com", cache_kind="portfolio",
            cache_key=str(portfolio.id),
        )
        assert stored.status == "completed"
        assert stored.result_json["assets"][0]["ticker"] == "ABCD3"
        assert isinstance(stored.result_json["generated_at"], str)

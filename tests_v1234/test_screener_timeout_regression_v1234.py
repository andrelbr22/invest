from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.core.current_metrics import AssetCurrentMetricsService
from investment_engine.core.models.strategy import StockFilterSet
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.infrastructure.db.base import Base


def test_current_stock_screener_pages_narrow_rows_and_avoids_like_explosion():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    statements = []

    with Session(engine) as session:
        repository = AssetRepository(session)
        now = datetime(2026, 9, 29, tzinfo=timezone.utc)
        for index, ticker in enumerate(("ABEV3", "PETR4", "VALE3"), start=1):
            asset = repository.upsert_asset(
                ticker=ticker, asset_type="stock", is_active=True,
            )
            repository.upsert_fundamentals(
                asset,
                source="test",
                reference_date=now,
                retrieved_at=now,
                status="valid",
                quality_score=100,
                data={
                    "price": 10 + index,
                    "pe": 5 + index,
                    "pbv": 1,
                    "roe_pct": 15,
                    "ebit_margin_pct": 12,
                    "current_ratio": 2,
                    "daily_liquidity": 2_000_000,
                },
                raw_payload={"large_provider_payload": "x" * 1000},
            )
            repository.upsert_scores(
                asset,
                as_of=now,
                model_version="test",
                scores={"alb_score": 100 - index},
                coverage_pct=100,
                data_quality_score=100,
            )
            AssetCurrentMetricsService(session).sync_asset(asset)
        session.commit()

        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture)
        try:
            rows = repository.screen_latest_stocks(
                StockFilterSet(
                    roe_min=8,
                    ebit_margin_min=5,
                    pe_min=0.1,
                    pe_max=20,
                    pbv_max=5,
                    current_ratio_min=1,
                    daily_liquidity_min=1_000_000,
                ),
                limit=2,
            )
        finally:
            event.remove(engine, "before_cursor_execute", capture)

    assert [row[0].ticker for row in rows] == ["ABEV3", "PETR4"]
    screener_sql = next(
        statement for statement in statements
        if "current_metrics_page" in statement.lower()
    )
    assert "from (select assets.id as asset_id" in " ".join(screener_sql.lower().split())
    assert " like " not in screener_sql.lower()
    assert "substr(" in screener_sql.lower()
    assert "length(" in screener_sql.lower()

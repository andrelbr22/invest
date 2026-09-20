from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.repositories.economic_series import InterestCurveHistoryRepository
from investment_engine.infrastructure.db.base import Base


ROOT = Path(__file__).resolve().parents[1]


def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_interest_curve_history_is_daily_and_updates_same_reference():
    with database_session() as session:
        repository = InterestCurveHistoryRepository(session)
        first = repository.save({
            "as_of": "2026-08-28", "curve_type": "di_pre", "title": "Curva DI",
            "source": "B3", "url": "https://example.test", "points": [{"years": 1, "nominal_rate": 12.0}],
        })
        repository.save({
            "as_of": "2026-08-28", "curve_type": "di_pre", "title": "Curva DI",
            "source": "B3", "points": [{"years": 1, "nominal_rate": 12.1}],
        })
        second = repository.save({
            "as_of": "2026-08-29", "curve_type": "di_pre", "title": "Curva DI",
            "source": "B3", "points": [{"years": 1, "nominal_rate": 11.9}],
        })
        session.commit()
        rows = repository.list_recent()
        assert len(rows) == 2
        assert rows[0].id == second.id
        assert rows[1].id == first.id
        assert rows[1].points_json[0]["nominal_rate"] == 12.1


def test_market_ui_supports_curve_overlays_common_base_and_risk_metrics():
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for text in (
        "interest-curve/history", "Somente atual", "+ 3 anteriores",
        "Início comum", "Histórico próprio", "annualizedVolatility",
        "Volatilidade anual", "readableApiError",
    ):
        assert text in script

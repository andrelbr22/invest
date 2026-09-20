from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.portfolio.custom_investments import (
    CustomInvestmentRepository,
    custom_investment_dict,
)
from investment_engine.core.repositories.portfolio import PortfolioRepository
from investment_engine.infrastructure.db.base import Base


ROOT = Path(__file__).resolve().parents[1]


def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_custom_investment_preserves_value_history_and_variation():
    with database_session() as session:
        portfolio = PortfolioRepository(session).create_portfolio(
            owner_email="owner@example.com", name="Principal",
        )
        repository = CustomInvestmentRepository(session)
        row = repository.create(
            portfolio.id, category="cdb", name="CDB 110% CDI", institution="Banco X",
            application_date=date(2025, 1, 10), maturity_date=date(2027, 1, 10),
            invested_value=10000, current_value=10500,
            current_value_as_of=date(2025, 6, 30), benchmark="110% do CDI",
            liquidity="No vencimento", notes=None,
        )
        repository.update(
            row, current_value=11000, current_value_as_of=date(2025, 12, 31),
        )
        session.commit()
        history = repository.history(row.id)
        payload = custom_investment_dict(row, history=history)
        assert [item["value"] for item in payload["history"]] == [10500, 11000]
        assert payload["variation_pct"] == 10
        assert payload["allocation_group"] == "Renda Fixa"


def test_custom_investment_archive_is_recoverable_in_database():
    with database_session() as session:
        portfolio = PortfolioRepository(session).create_portfolio(
            owner_email="owner@example.com", name="Principal",
        )
        repository = CustomInvestmentRepository(session)
        row = repository.create(
            portfolio.id, category="multimarket_fund", name="Fundo Macro",
            institution=None, application_date=date(2025, 1, 1), maturity_date=None,
            invested_value=5000, current_value=5200, current_value_as_of=date(2025, 2, 1),
            benchmark=None, liquidity="D+15", notes=None,
        )
        repository.deactivate(row)
        session.commit()
        assert repository.list(portfolio.id) == []
        assert repository.get(row.id, portfolio.id).is_active is False
        assert len(repository.history(row.id)) == 1


def test_portfolio_ui_has_consolidated_allocation_and_manual_investment_form():
    html = (ROOT / "investment_engine" / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    catalog = (ROOT / "investment_engine" / "core" / "portfolio" / "custom_investments.py").read_text(encoding="utf-8")
    assert 'data-tab="allocation"' in html
    for text in (
        "Investimentos e alocação", "Composição consolidada", "Adicionar investimento sem ticker",
        "Fundo de renda fixa", "Atualizar valor", "allocationDonut",
    ):
        assert text in html + script + catalog

from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.finance.service import FinanceRepository
from investment_engine.infrastructure.db.base import Base


ROOT = Path(__file__).resolve().parents[1]


def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_finances_are_isolated_and_monthly_summary_is_consistent():
    with database_session() as session:
        owner = FinanceRepository(session, "one@example.com")
        owner.create_transaction(
            transaction_date=date(2026, 8, 5), competence_month="2026-08",
            kind="income", category="Salário", description="Salário", amount=10000,
            status="received", institution=None, payment_method=None, notes=None,
        )
        expense = owner.create_transaction(
            transaction_date=date(2026, 8, 10), competence_month="2026-08",
            kind="expense", category="Moradia", description="Aluguel", amount=2500,
            status="paid", institution=None, payment_method="PIX", notes=None,
        )
        owner.create_transaction(
            transaction_date=date(2026, 8, 15), competence_month="2026-08",
            kind="expense", category="Alimentação", description="Mercado", amount=800,
            status="planned", institution=None, payment_method="Cartão", notes=None,
        )
        owner.replace_budgets("2026-08", {"Moradia": 3000, "Alimentação": 1000})
        session.commit()

        summary = owner.summary("2026-08")
        assert summary["realized"] == {"income": 10000, "expense": 2500, "balance": 7500}
        assert summary["forecast"] == {"income": 10000, "expense": 3300, "balance": 6700}
        assert {row["category"]: row["used_pct"] for row in summary["budgets"]} == {
            "Alimentação": 80.0, "Moradia": 83.33,
        }
        assert FinanceRepository(session, "other@example.com").summary("2026-08")["transactions"] == []

        owner.archive_transaction(expense)
        session.commit()
        assert len(owner.summary("2026-08")["transactions"]) == 2


def test_finance_rejects_category_or_status_incompatible_with_kind():
    with database_session() as session:
        repository = FinanceRepository(session, "owner@example.com")
        base = dict(
            transaction_date=date(2026, 8, 1), competence_month="2026-08",
            description="Inválido", amount=10, institution=None, payment_method=None, notes=None,
        )
        try:
            repository.create_transaction(kind="income", category="Moradia", status="received", **base)
            assert False, "category should be rejected"
        except ValueError as exc:
            assert str(exc) == "invalid_finance_category"
        try:
            repository.create_transaction(kind="income", category="Salário", status="paid", **base)
            assert False, "status should be rejected"
        except ValueError as exc:
            assert str(exc) == "invalid_finance_status"


def test_finance_navigation_and_forms_are_present():
    html = (ROOT / "investment_engine" / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for text in (
        'data-view="finances"', "Minhas Finanças", 'data-tabs="finances"',
        "Visão mensal", "Planilha mensal", "finance-transaction-form",
        "finance-budget-form", "can_view_finances", "can_write_finances",
    ):
        assert text in html + script

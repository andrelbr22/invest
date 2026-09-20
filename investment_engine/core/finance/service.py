from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from ...infrastructure.db.models import FinanceMonthlyBudgetORM, FinanceTransactionORM


FINANCE_CATEGORIES = {
    "income": (
        "Salário", "Pró-labore", "Rendimentos", "Dividendos", "Aluguel recebido",
        "Venda", "Reembolso", "Outras receitas",
    ),
    "expense": (
        "Moradia", "Alimentação", "Transporte", "Saúde", "Educação", "Seguros",
        "Impostos", "Lazer", "Assinaturas", "Dívidas", "Investimentos", "Outras despesas",
    ),
}


def month_start(value: str | date) -> date:
    if isinstance(value, date):
        return value.replace(day=1)
    clean = str(value or "").strip()
    try:
        parsed = datetime.strptime(clean, "%Y-%m").date()
    except ValueError as exc:
        raise ValueError("invalid_competence_month") from exc
    return parsed.replace(day=1)


def transaction_dict(row: FinanceTransactionORM) -> dict:
    return {
        "id": str(row.id), "transaction_date": row.transaction_date,
        "competence_month": row.competence_month.strftime("%Y-%m"),
        "kind": row.kind, "category": row.category, "description": row.description,
        "amount": float(row.amount), "status": row.status,
        "institution": row.institution, "payment_method": row.payment_method,
        "notes": row.notes, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _validate_status(kind: str, status: str) -> None:
    allowed = {"income": {"planned", "received", "overdue"}, "expense": {"planned", "paid", "overdue"}}
    if status not in allowed[kind]:
        raise ValueError("invalid_finance_status")


class FinanceRepository:
    def __init__(self, session, owner_email: str):
        self.session = session
        self.owner_email = str(owner_email or "").strip().lower()

    def list_transactions(self, competence_month: str | date):
        month = month_start(competence_month)
        return list(self.session.scalars(select(FinanceTransactionORM).where(
            FinanceTransactionORM.owner_email == self.owner_email,
            FinanceTransactionORM.competence_month == month,
            FinanceTransactionORM.is_active.is_(True),
        ).order_by(FinanceTransactionORM.transaction_date.desc(), FinanceTransactionORM.created_at.desc())))

    def get_transaction(self, transaction_id):
        return self.session.scalar(select(FinanceTransactionORM).where(
            FinanceTransactionORM.id == transaction_id,
            FinanceTransactionORM.owner_email == self.owner_email,
        ))

    def create_transaction(self, **values):
        kind = str(values["kind"])
        category = str(values["category"]).strip()
        if category not in FINANCE_CATEGORIES[kind]:
            raise ValueError("invalid_finance_category")
        status = str(values.get("status") or "planned")
        _validate_status(kind, status)
        row = FinanceTransactionORM(
            owner_email=self.owner_email,
            transaction_date=values["transaction_date"],
            competence_month=month_start(values.get("competence_month") or values["transaction_date"]),
            kind=kind, category=category, description=str(values["description"]).strip(),
            amount=Decimal(str(values["amount"])), status=status,
            institution=values.get("institution"), payment_method=values.get("payment_method"),
            notes=values.get("notes"),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_transaction(self, row: FinanceTransactionORM, **changes):
        if "kind" in changes or "category" in changes:
            kind = str(changes.get("kind", row.kind))
            category = str(changes.get("category", row.category)).strip()
            if category not in FINANCE_CATEGORIES[kind]:
                raise ValueError("invalid_finance_category")
        target_kind = str(changes.get("kind", row.kind))
        target_status = str(changes.get("status", row.status))
        _validate_status(target_kind, target_status)
        for field in (
            "transaction_date", "kind", "category", "description", "status",
            "institution", "payment_method", "notes",
        ):
            if field in changes:
                setattr(row, field, changes[field])
        if "amount" in changes:
            row.amount = Decimal(str(changes["amount"]))
        if "competence_month" in changes:
            row.competence_month = month_start(changes["competence_month"])
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def archive_transaction(self, row: FinanceTransactionORM):
        row.is_active = False
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    def budgets(self, competence_month: str | date):
        month = month_start(competence_month)
        return list(self.session.scalars(select(FinanceMonthlyBudgetORM).where(
            FinanceMonthlyBudgetORM.owner_email == self.owner_email,
            FinanceMonthlyBudgetORM.competence_month == month,
        ).order_by(FinanceMonthlyBudgetORM.category)))

    def replace_budgets(self, competence_month: str | date, values: dict[str, float]):
        month = month_start(competence_month)
        existing = {row.category: row for row in self.budgets(month)}
        allowed = set(FINANCE_CATEGORIES["expense"])
        for category, raw_value in values.items():
            if category not in allowed:
                raise ValueError("invalid_finance_category")
            value = Decimal(str(raw_value))
            if value < 0:
                raise ValueError("invalid_budget_value")
            row = existing.pop(category, None)
            if value == 0:
                if row is not None:
                    self.session.delete(row)
                continue
            if row is None:
                row = FinanceMonthlyBudgetORM(
                    owner_email=self.owner_email, competence_month=month,
                    category=category, limit_value=value,
                )
                self.session.add(row)
            else:
                row.limit_value = value
                row.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    def summary(self, competence_month: str | date) -> dict:
        month = month_start(competence_month)
        rows = self.list_transactions(month)
        realized_statuses = {"paid", "received"}
        income = sum(float(row.amount) for row in rows if row.kind == "income" and row.status in realized_statuses)
        expense = sum(float(row.amount) for row in rows if row.kind == "expense" and row.status in realized_statuses)
        forecast_income = sum(float(row.amount) for row in rows if row.kind == "income")
        forecast_expense = sum(float(row.amount) for row in rows if row.kind == "expense")
        expense_by_category: dict[str, float] = {}
        for row in rows:
            if row.kind == "expense":
                expense_by_category[row.category] = expense_by_category.get(row.category, 0.0) + float(row.amount)
        budget_rows = self.budgets(month)
        budgets = [{
            "category": row.category, "limit_value": float(row.limit_value),
            "used_value": expense_by_category.get(row.category, 0.0),
            "used_pct": round(expense_by_category.get(row.category, 0.0) / float(row.limit_value) * 100, 2)
            if float(row.limit_value) > 0 else None,
        } for row in budget_rows]
        return {
            "competence_month": month.strftime("%Y-%m"),
            "period_start": month,
            "period_end": date(month.year, month.month, monthrange(month.year, month.month)[1]),
            "realized": {"income": income, "expense": expense, "balance": income - expense},
            "forecast": {
                "income": forecast_income, "expense": forecast_expense,
                "balance": forecast_income - forecast_expense,
            },
            "expense_by_category": [
                {"category": category, "value": value}
                for category, value in sorted(expense_by_category.items(), key=lambda item: item[1], reverse=True)
            ],
            "budgets": budgets,
            "transactions": [transaction_dict(row) for row in rows],
            "updated_at": max((row.updated_at for row in rows), default=None),
        }

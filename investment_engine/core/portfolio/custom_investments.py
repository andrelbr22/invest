from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from ...infrastructure.db.models import (
    PortfolioCustomInvestmentORM,
    PortfolioCustomInvestmentValueORM,
)


CUSTOM_INVESTMENT_CATEGORIES = {
    "fixed_income_fund": ("Fundo de renda fixa", "Fundos"),
    "multimarket_fund": ("Fundo multimercado", "Fundos"),
    "equity_fund": ("Fundo de renda variável", "Fundos"),
    "cdb": ("CDB", "Renda Fixa"),
    "lci": ("LCI", "Renda Fixa"),
    "lca": ("LCA", "Renda Fixa"),
    "treasury": ("Tesouro Direto", "Renda Fixa"),
    "debenture": ("Debênture", "Renda Fixa"),
    "cri": ("CRI", "Renda Fixa"),
    "cra": ("CRA", "Renda Fixa"),
    "private_pension": ("Previdência privada", "Previdência"),
    "other_fixed_income": ("Outra renda fixa", "Renda Fixa"),
    "other_fund": ("Outro fundo", "Fundos"),
    "other": ("Outro investimento", "Outros"),
}


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def custom_investment_dict(row: PortfolioCustomInvestmentORM, *, history: list | None = None) -> dict:
    invested = float(row.invested_value)
    current = float(row.current_value)
    variation = round(((current / invested) - 1.0) * 100.0, 8) if invested > 0 else None
    label, group = CUSTOM_INVESTMENT_CATEGORIES.get(row.category, (row.category, "Outros"))
    payload = {
        "id": str(row.id), "portfolio_id": str(row.portfolio_id),
        "category": row.category, "category_label": label, "allocation_group": group,
        "name": row.name, "institution": row.institution,
        "sector": row.sector, "segment": row.segment,
        "application_date": row.application_date, "maturity_date": row.maturity_date,
        "invested_value": invested, "current_value": current,
        "current_value_as_of": row.current_value_as_of,
        "variation_pct": variation, "benchmark": row.benchmark,
        "liquidity": row.liquidity, "notes": row.notes, "is_active": row.is_active,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }
    if history is not None:
        payload["history"] = [{
            "reference_date": item.reference_date, "value": float(item.value), "source": item.source,
        } for item in history]
    return payload


class CustomInvestmentRepository:
    def __init__(self, session):
        self.session = session

    def list(self, portfolio_id, *, active_only: bool = True):
        statement = select(PortfolioCustomInvestmentORM).where(
            PortfolioCustomInvestmentORM.portfolio_id == portfolio_id,
        )
        if active_only:
            statement = statement.where(PortfolioCustomInvestmentORM.is_active.is_(True))
        return list(self.session.scalars(statement.order_by(
            PortfolioCustomInvestmentORM.category, PortfolioCustomInvestmentORM.name,
        )))

    def get(self, investment_id, portfolio_id):
        return self.session.scalar(select(PortfolioCustomInvestmentORM).where(
            PortfolioCustomInvestmentORM.id == investment_id,
            PortfolioCustomInvestmentORM.portfolio_id == portfolio_id,
        ))

    def history(self, investment_id):
        return list(self.session.scalars(select(PortfolioCustomInvestmentValueORM).where(
            PortfolioCustomInvestmentValueORM.investment_id == investment_id,
        ).order_by(PortfolioCustomInvestmentValueORM.reference_date)))

    def _record_value(self, row, reference_date: date, value) -> None:
        existing = self.session.scalar(select(PortfolioCustomInvestmentValueORM).where(
            PortfolioCustomInvestmentValueORM.investment_id == row.id,
            PortfolioCustomInvestmentValueORM.reference_date == reference_date,
        ))
        if existing is None:
            existing = PortfolioCustomInvestmentValueORM(
                investment_id=row.id, reference_date=reference_date,
            )
            self.session.add(existing)
        existing.value = _decimal(value)
        existing.source = "manual"

    def create(self, portfolio_id, **values):
        category = str(values["category"])
        if category not in CUSTOM_INVESTMENT_CATEGORIES:
            raise ValueError("invalid_custom_investment_category")
        row = PortfolioCustomInvestmentORM(
            portfolio_id=portfolio_id, category=category,
            name=str(values["name"]).strip(),
            institution=str(values.get("institution") or "").strip() or None,
            sector=str(values.get("sector") or "").strip() or None,
            segment=str(values.get("segment") or "").strip() or None,
            application_date=values["application_date"],
            maturity_date=values.get("maturity_date"),
            invested_value=_decimal(values["invested_value"]),
            current_value=_decimal(values["current_value"]),
            current_value_as_of=values["current_value_as_of"],
            benchmark=str(values.get("benchmark") or "").strip() or None,
            liquidity=str(values.get("liquidity") or "").strip() or None,
            notes=values.get("notes"), is_active=True,
        )
        self.session.add(row)
        self.session.flush()
        self._record_value(row, row.current_value_as_of, row.current_value)
        self.session.flush()
        return row

    def update(self, row, **changes):
        for field in (
            "name", "institution", "sector", "segment", "application_date", "maturity_date", "benchmark",
            "liquidity", "notes",
        ):
            if field in changes:
                value = changes[field]
                if field in {"name", "institution", "sector", "segment", "benchmark", "liquidity"} and isinstance(value, str):
                    value = value.strip() or None
                setattr(row, field, value)
        if "category" in changes:
            if changes["category"] not in CUSTOM_INVESTMENT_CATEGORIES:
                raise ValueError("invalid_custom_investment_category")
            row.category = changes["category"]
        if "invested_value" in changes:
            row.invested_value = _decimal(changes["invested_value"])
        if "current_value" in changes or "current_value_as_of" in changes:
            current_value = _decimal(changes.get("current_value", row.current_value))
            reference_date = changes.get("current_value_as_of", row.current_value_as_of)
            row.current_value = current_value
            row.current_value_as_of = reference_date
            self._record_value(row, reference_date, current_value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def deactivate(self, row):
        row.is_active = False
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()

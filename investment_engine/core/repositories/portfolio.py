from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..instruments import is_supported_ticker

from ...infrastructure.db.models import (
    AssetORM,
    FundamentalSnapshotORM,
    PortfolioORM,
    PortfolioPositionORM,
    PriceBarORM,
)


def _d(value):
    if value is None:
        return None
    return Decimal(str(value))


class PortfolioRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_portfolios(self, owner_email: str) -> list[PortfolioORM]:
        return list(self.session.scalars(
            select(PortfolioORM)
            .where(PortfolioORM.owner_email == owner_email.strip().lower())
            .order_by(PortfolioORM.created_at, PortfolioORM.name)
        ))

    def get_portfolio(self, portfolio_id, owner_email: str) -> PortfolioORM | None:
        return self.session.scalar(select(PortfolioORM).where(
            PortfolioORM.id == portfolio_id,
            PortfolioORM.owner_email == owner_email.strip().lower(),
        ))

    def create_portfolio(self, *, owner_email: str, name: str, base_currency: str = "BRL", cash_balance=0, target_cash_pct=0, notes=None) -> PortfolioORM:
        p = PortfolioORM(
            owner_email=owner_email.strip().lower(),
            name=name.strip() or "Carteira Principal",
            base_currency=base_currency,
            cash_balance=_d(cash_balance) or Decimal("0"),
            target_cash_pct=_d(target_cash_pct) or Decimal("0"),
            notes=notes,
        )
        self.session.add(p)
        self.session.flush()
        return p

    def update_portfolio(self, portfolio: PortfolioORM, *, name=None, cash_balance=None, target_cash_pct=None, notes=None) -> PortfolioORM:
        if name is not None:
            portfolio.name = name.strip() or portfolio.name
        if cash_balance is not None:
            portfolio.cash_balance = _d(cash_balance) or Decimal("0")
        if target_cash_pct is not None:
            portfolio.target_cash_pct = _d(target_cash_pct) or Decimal("0")
        if notes is not None:
            portfolio.notes = notes
        portfolio.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return portfolio

    def positions(self, portfolio_id) -> list[tuple[PortfolioPositionORM, AssetORM]]:
        stmt = (
            select(PortfolioPositionORM, AssetORM)
            .join(AssetORM, AssetORM.id == PortfolioPositionORM.asset_id)
            .where(PortfolioPositionORM.portfolio_id == portfolio_id)
            .order_by(AssetORM.asset_type, AssetORM.ticker)
        )
        return [
            (position, asset)
            for position, asset in self.session.execute(stmt).all()
            if is_supported_ticker(asset.ticker, asset.asset_type)
        ]

    def get_position(self, portfolio_id, asset_id) -> PortfolioPositionORM | None:
        return self.session.scalar(
            select(PortfolioPositionORM).where(
                PortfolioPositionORM.portfolio_id == portfolio_id,
                PortfolioPositionORM.asset_id == asset_id,
            )
        )

    def upsert_position(self, portfolio: PortfolioORM, asset: AssetORM, *, stage="position", quantity=0, average_price=None, target_weight_pct=0, classification_override=None, sector_override=None, segment_override=None, notes=None) -> PortfolioPositionORM:
        row = self.get_position(portfolio.id, asset.id)
        if row is None:
            row = PortfolioPositionORM(portfolio_id=portfolio.id, asset_id=asset.id)
            self.session.add(row)
        row.stage = stage
        row.quantity = _d(quantity) or Decimal("0")
        row.average_price = _d(average_price)
        row.target_weight_pct = _d(target_weight_pct) or Decimal("0")
        row.classification_override = classification_override.strip() if isinstance(classification_override, str) and classification_override.strip() else None
        row.sector_override = sector_override.strip() if isinstance(sector_override, str) and sector_override.strip() else None
        row.segment_override = segment_override.strip() if isinstance(segment_override, str) and segment_override.strip() else None
        row.notes = notes
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def add_purchase(self, portfolio: PortfolioORM, asset: AssetORM, *, quantity, unit_price,
                     stage="position", target_weight_pct=None, classification_override=None,
                     sector_override=None, segment_override=None, notes=None) -> PortfolioPositionORM:
        """Add a purchase and preserve a weighted average acquisition price."""
        purchase_qty = _d(quantity) or Decimal("0")
        purchase_price = _d(unit_price)
        if purchase_qty <= 0 or purchase_price is None or purchase_price < 0:
            raise ValueError("invalid_purchase")
        row = self.get_position(portfolio.id, asset.id)
        if row is None:
            row = PortfolioPositionORM(portfolio_id=portfolio.id, asset_id=asset.id)
            self.session.add(row)
            old_qty = Decimal("0")
            old_average = Decimal("0")
        else:
            old_qty = _d(row.quantity) or Decimal("0")
            old_average = _d(row.average_price)
            if old_average is None:
                old_average = purchase_price
        new_qty = old_qty + purchase_qty
        row.quantity = new_qty
        row.average_price = ((old_qty * old_average) + (purchase_qty * purchase_price)) / new_qty
        row.stage = stage
        if target_weight_pct is not None:
            row.target_weight_pct = _d(target_weight_pct) or Decimal("0")
        elif row.target_weight_pct is None:
            row.target_weight_pct = Decimal("0")
        if classification_override is not None:
            row.classification_override = classification_override.strip() or None
        if sector_override is not None:
            row.sector_override = sector_override.strip() or None
        if segment_override is not None:
            row.segment_override = segment_override.strip() or None
        if notes is not None:
            row.notes = notes
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def delete_position(self, portfolio_id, asset_id) -> bool:
        row = self.get_position(portfolio_id, asset_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    def latest_price_info(self, asset_id) -> dict:
        bar = self.session.scalar(
            select(PriceBarORM)
            .where(PriceBarORM.asset_id == asset_id, PriceBarORM.timeframe == "1D")
            .order_by(PriceBarORM.timestamp.desc())
            .limit(1)
        )
        if bar is not None:
            value = bar.adjusted_close if bar.adjusted_close is not None else bar.close
            if value is not None:
                return {"price": float(value), "as_of": bar.timestamp, "source": bar.source}
        fund = self.session.scalar(
            select(FundamentalSnapshotORM)
            .where(FundamentalSnapshotORM.asset_id == asset_id)
            .order_by(FundamentalSnapshotORM.reference_date.desc(), FundamentalSnapshotORM.retrieved_at.desc())
            .limit(1)
        )
        if fund is not None and fund.price is not None:
            return {"price": float(fund.price), "as_of": fund.reference_date, "source": fund.source}
        return {"price": None, "as_of": None, "source": None}

    def latest_price(self, asset_id) -> float | None:
        return self.latest_price_info(asset_id)["price"]

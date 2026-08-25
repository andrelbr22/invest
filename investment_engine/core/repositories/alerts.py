from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import PriceAlertEventORM, PriceAlertORM, UserAlertPreferenceORM


def _number(value):
    return float(value) if isinstance(value, Decimal) else value


def alert_dict(row: PriceAlertORM) -> dict:
    return {
        "id": str(row.id), "owner_email": row.owner_email, "symbol": row.symbol,
        "provider_symbol": row.provider_symbol, "display_name": row.display_name,
        "market_scope": row.market_scope, "status": row.status,
        "price_above": _number(row.price_above), "price_below": _number(row.price_below),
        "change_positive_pct": _number(row.change_positive_pct),
        "change_negative_pct": _number(row.change_negative_pct),
        "last_checked_at": row.last_checked_at, "last_quote_at": row.last_quote_at,
        "last_price": _number(row.last_price), "last_change_pct": _number(row.last_change_pct),
        "triggered_at": row.triggered_at, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def event_dict(row: PriceAlertEventORM) -> dict:
    return {
        "id": str(row.id), "alert_id": str(row.alert_id), "symbol": row.symbol,
        "display_name": row.display_name, "triggered_rules": row.triggered_rules_json or [],
        "configured_values": row.configured_values_json or {}, "observed": row.observed_json or {},
        "recipients": row.recipients_json or [], "delivery_status": row.delivery_status,
        "delivery_attempts": row.delivery_attempts, "last_error": row.last_error,
        "quote_at": row.quote_at, "sent_at": row.sent_at, "created_at": row.created_at,
    }


class AlertRepository:
    def __init__(self, session: Session):
        self.session = session

    def preference(self, owner_email: str, *, create: bool = False) -> UserAlertPreferenceORM | None:
        clean = str(owner_email or "").strip().lower()
        row = self.session.scalar(select(UserAlertPreferenceORM).where(UserAlertPreferenceORM.owner_email == clean))
        if row is None and create:
            row = UserAlertPreferenceORM(owner_email=clean)
            self.session.add(row)
            self.session.flush()
        return row

    def update_preference(self, owner_email: str, secondary_email: str | None) -> UserAlertPreferenceORM:
        row = self.preference(owner_email, create=True)
        row.secondary_email = str(secondary_email or "").strip().lower() or None
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def list_for_owner(self, owner_email: str) -> list[PriceAlertORM]:
        clean = str(owner_email or "").strip().lower()
        return list(self.session.scalars(
            select(PriceAlertORM).where(PriceAlertORM.owner_email == clean)
            .order_by(PriceAlertORM.status, PriceAlertORM.symbol)
        ))

    def get_for_owner(self, alert_id, owner_email: str) -> PriceAlertORM | None:
        return self.session.scalar(select(PriceAlertORM).where(
            PriceAlertORM.id == alert_id,
            PriceAlertORM.owner_email == str(owner_email or "").strip().lower(),
        ))

    def get_by_symbol(self, owner_email: str, symbol: str) -> PriceAlertORM | None:
        return self.session.scalar(select(PriceAlertORM).where(
            PriceAlertORM.owner_email == str(owner_email or "").strip().lower(),
            PriceAlertORM.symbol == str(symbol or "").strip().upper(),
        ))

    def active_count(self, owner_email: str) -> int:
        return sum(1 for row in self.list_for_owner(owner_email) if row.status == "active")

    def upsert(self, *, owner_email: str, symbol: str, provider_symbol: str, display_name: str,
               market_scope: str, rules: dict) -> PriceAlertORM:
        row = self.get_by_symbol(owner_email, symbol)
        if row is None:
            row = PriceAlertORM(owner_email=str(owner_email).strip().lower(), symbol=str(symbol).strip().upper())
            self.session.add(row)
        row.provider_symbol = provider_symbol
        row.display_name = display_name
        row.market_scope = market_scope
        row.price_above = rules.get("price_above")
        row.price_below = rules.get("price_below")
        row.change_positive_pct = rules.get("change_positive_pct")
        row.change_negative_pct = rules.get("change_negative_pct")
        row.status = "active"
        row.triggered_at = None
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def set_status(self, row: PriceAlertORM, status: str) -> PriceAlertORM:
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
        if status == "active":
            row.triggered_at = None
        self.session.flush()
        return row

    def enforce_policy(self, owner_email: str, *, limit: int, permissions: dict) -> None:
        """Apply a permission reduction immediately to previously saved alerts."""
        rows = self.list_for_owner(owner_email)
        field_permissions = {
            "price_above": "price_above",
            "price_below": "price_below",
            "change_positive_pct": "change_positive_pct",
            "change_negative_pct": "change_negative_pct",
        }
        now = datetime.now(timezone.utc)
        for row in rows:
            for field, permission in field_permissions.items():
                if not permissions.get(permission, False):
                    setattr(row, field, None)
            if all(getattr(row, field) is None for field in field_permissions):
                row.status = "disabled"
            row.updated_at = now

        active = sorted(
            (row for row in rows if row.status == "active"),
            key=lambda row: row.updated_at or row.created_at,
            reverse=True,
        )
        for row in active[max(0, int(limit)):]:
            row.status = "disabled"
            row.updated_at = now
        self.session.flush()

    def due_alerts(self, now: datetime) -> list[PriceAlertORM]:
        market_cutoff = now - timedelta(minutes=30)
        b3_cutoff = now - timedelta(minutes=5)
        stmt = select(PriceAlertORM).where(
            PriceAlertORM.status == "active",
            or_(
                (PriceAlertORM.market_scope == "b3") & or_(PriceAlertORM.last_checked_at.is_(None), PriceAlertORM.last_checked_at <= b3_cutoff),
                (PriceAlertORM.market_scope == "market") & or_(PriceAlertORM.last_checked_at.is_(None), PriceAlertORM.last_checked_at <= market_cutoff),
            ),
        ).order_by(PriceAlertORM.market_scope, PriceAlertORM.provider_symbol)
        return list(self.session.scalars(stmt))

    def mark_checked(self, row: PriceAlertORM, now: datetime) -> None:
        row.last_checked_at = now
        row.updated_at = now
        self.session.flush()

    def record_observation(self, row: PriceAlertORM, quote: dict) -> None:
        row.last_quote_at = quote["quote_at"]
        row.last_price = quote.get("price")
        row.last_change_pct = quote.get("change_pct")
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    def trigger(self, row: PriceAlertORM, *, rules: list[str], configured_values: dict,
                observed: dict, recipients: list[str]) -> PriceAlertEventORM:
        now = datetime.now(timezone.utc)
        quote_at = observed["quote_at"]
        if isinstance(quote_at, str):
            quote_at = datetime.fromisoformat(quote_at.replace("Z", "+00:00"))
        row.status = "triggered"
        row.triggered_at = now
        row.updated_at = now
        event = PriceAlertEventORM(
            alert_id=row.id, owner_email=row.owner_email, symbol=row.symbol,
            display_name=row.display_name, triggered_rules_json=list(rules),
            configured_values_json=dict(configured_values), observed_json=dict(observed),
            recipients_json=list(recipients), quote_at=quote_at,
            delivery_status="pending", next_attempt_at=now,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def history(self, owner_email: str, limit: int = 100) -> list[PriceAlertEventORM]:
        return list(self.session.scalars(
            select(PriceAlertEventORM)
            .where(PriceAlertEventORM.owner_email == str(owner_email or "").strip().lower())
            .order_by(PriceAlertEventORM.created_at.desc()).limit(max(1, min(int(limit), 500)))
        ))

    def pending_deliveries(self, now: datetime, limit: int = 20) -> list[PriceAlertEventORM]:
        return list(self.session.scalars(
            select(PriceAlertEventORM).where(
                PriceAlertEventORM.delivery_status == "pending",
                or_(PriceAlertEventORM.next_attempt_at.is_(None), PriceAlertEventORM.next_attempt_at <= now),
            ).order_by(PriceAlertEventORM.created_at).limit(limit)
        ))

    def delivery_sent(self, event: PriceAlertEventORM) -> None:
        event.delivery_status = "sent"
        event.delivery_attempts += 1
        event.sent_at = datetime.now(timezone.utc)
        event.last_error = None
        event.next_attempt_at = None
        self.session.flush()

    def delivery_failed(self, event: PriceAlertEventORM, error: str) -> None:
        event.delivery_attempts += 1
        event.last_error = str(error or "email_delivery_failed")[:800]
        if event.delivery_attempts >= 5:
            event.delivery_status = "failed"
            event.next_attempt_at = None
        else:
            delay = (5, 15, 60, 180)[min(event.delivery_attempts - 1, 3)]
            event.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=delay)
        self.session.flush()

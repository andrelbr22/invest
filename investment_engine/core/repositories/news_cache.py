from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import UserNewsCacheORM


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
MANUAL_REFRESH_COOLDOWN = timedelta(minutes=5)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def news_market_date(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(SAO_PAULO).date()


class NewsCacheRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, *, owner_email: str, cache_kind: str, cache_key: str,
            market_date: date | None = None) -> UserNewsCacheORM | None:
        return self.session.scalar(select(UserNewsCacheORM).where(
            UserNewsCacheORM.owner_email == owner_email.strip().lower(),
            UserNewsCacheORM.cache_kind == cache_kind,
            UserNewsCacheORM.cache_key == str(cache_key),
            UserNewsCacheORM.market_date == (market_date or news_market_date()),
        ))

    def latest(self, *, owner_email: str, cache_kind: str,
               cache_key: str) -> UserNewsCacheORM | None:
        """Return the newest cache, allowing a screen to show yesterday while refreshing."""
        return self.session.scalar(
            select(UserNewsCacheORM).where(
                UserNewsCacheORM.owner_email == owner_email.strip().lower(),
                UserNewsCacheORM.cache_kind == cache_kind,
                UserNewsCacheORM.cache_key == str(cache_key),
            ).order_by(UserNewsCacheORM.market_date.desc(), UserNewsCacheORM.updated_at.desc())
        )

    def latest_completed(self, *, owner_email: str, cache_kind: str,
                         cache_key: str) -> UserNewsCacheORM | None:
        return self.session.scalar(
            select(UserNewsCacheORM).where(
                UserNewsCacheORM.owner_email == owner_email.strip().lower(),
                UserNewsCacheORM.cache_kind == cache_kind,
                UserNewsCacheORM.cache_key == str(cache_key),
                UserNewsCacheORM.status == "completed",
            ).order_by(UserNewsCacheORM.market_date.desc(), UserNewsCacheORM.updated_at.desc())
        )

    def request_refresh(self, *, owner_email: str, cache_kind: str, cache_key: str,
                        trigger: str, force: bool = False,
                        market_date: date | None = None) -> tuple[UserNewsCacheORM, bool]:
        now = datetime.now(timezone.utc)
        row = self.get(
            owner_email=owner_email, cache_kind=cache_kind, cache_key=cache_key,
            market_date=market_date,
        )
        if row is not None and not force:
            # The existence of the daily row is the once-a-day automatic lock,
            # including a failed attempt. Only the user can retry that day.
            return row, False
        if row is not None and force and trigger == "manual":
            activity = _aware(row.requested_at or row.updated_at)
            if activity and now - activity < MANUAL_REFRESH_COOLDOWN:
                return row, False
        if row is not None and row.status in {"queued", "running"}:
            activity = _aware(row.started_at or row.requested_at)
            if activity and now - activity < timedelta(minutes=20):
                return row, False
        if row is None:
            row = UserNewsCacheORM(
                owner_email=owner_email.strip().lower(),
                cache_kind=cache_kind,
                cache_key=str(cache_key),
                market_date=market_date or news_market_date(),
            )
            self.session.add(row)
        row.status = "queued"
        row.trigger = trigger
        row.error_message = None
        row.requested_at = now
        row.started_at = None
        row.finished_at = None
        row.updated_at = now
        # Keep result_json while a manual refresh runs. The screen can continue
        # showing the last successful data instead of becoming empty.
        self.session.flush()
        return row, True

    def mark_running(self, row: UserNewsCacheORM) -> None:
        now = datetime.now(timezone.utc)
        row.status = "running"
        row.started_at = now
        row.updated_at = now
        self.session.flush()

    def mark_completed(self, row: UserNewsCacheORM, result: dict) -> None:
        now = datetime.now(timezone.utc)
        row.status = "completed"
        row.result_json = result or {}
        row.error_message = None
        row.finished_at = now
        row.updated_at = now
        self.session.flush()

    def mark_failed(self, row: UserNewsCacheORM, error_message: str) -> None:
        now = datetime.now(timezone.utc)
        row.status = "failed"
        row.error_message = str(error_message or "news_refresh_failed")[:800]
        row.finished_at = now
        row.updated_at = now
        self.session.flush()


def news_cache_dict(row: UserNewsCacheORM | None) -> dict:
    if row is None:
        return {
            "status": "not_requested", "has_data": False,
            "market_date": news_market_date(), "data": {},
        }
    return {
        "id": str(row.id),
        "status": row.status,
        "has_data": bool(row.result_json),
        "cache_kind": row.cache_kind,
        "cache_key": row.cache_key,
        "market_date": row.market_date,
        "trigger": row.trigger,
        "data": row.result_json or {},
        "error": row.error_message,
        "requested_at": row.requested_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }

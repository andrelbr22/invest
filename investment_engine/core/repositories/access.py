from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import UserAccessPolicyORM


PERMISSION_FIELDS = (
    "can_view_market",
    "can_use_advanced_filters",
    "can_view_portfolio",
    "can_write_portfolio",
    "can_view_backtests",
    "can_run_backtests",
    "can_sync_market",
    "can_manage_users",
)


def normalized_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def full_owner_policy(email: str, display_name: str | None = None) -> dict:
    return {
        "email": normalized_email(email),
        "display_name": display_name,
        "role": "owner",
        "status": "approved",
        **{field: True for field in PERMISSION_FIELDS},
        "custom_filter_limit": 3,
        "is_owner": True,
    }


def policy_dict(row: UserAccessPolicyORM, *, is_owner: bool = False) -> dict:
    if is_owner:
        return full_owner_policy(row.email, row.display_name)
    blocked = row.status == "blocked"
    return {
        "email": row.email,
        "display_name": row.display_name,
        "role": row.role,
        "status": row.status,
        **{field: False if blocked else bool(getattr(row, field)) for field in PERMISSION_FIELDS},
        "custom_filter_limit": 0 if blocked else max(0, min(3, int(row.custom_filter_limit or 0))),
        "is_owner": False,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_seen_at": row.last_seen_at,
    }


class AccessPolicyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, email: str) -> UserAccessPolicyORM | None:
        clean = normalized_email(email)
        if not clean:
            return None
        return self.session.scalar(select(UserAccessPolicyORM).where(UserAccessPolicyORM.email == clean))

    def register(self, email: str, display_name: str | None = None, *, is_owner: bool = False) -> UserAccessPolicyORM:
        clean = normalized_email(email)
        if not clean:
            raise ValueError("email_required")
        row = self.get(clean)
        now = datetime.now(timezone.utc)
        if row is None:
            row = UserAccessPolicyORM(email=clean, display_name=display_name, last_seen_at=now)
            self.session.add(row)
        elif display_name:
            row.display_name = display_name
        row.last_seen_at = now
        if is_owner:
            row.role = "owner"
            row.status = "approved"
            for field in PERMISSION_FIELDS:
                setattr(row, field, True)
            row.custom_filter_limit = 3
        self.session.flush()
        return row

    def list_all(self) -> list[UserAccessPolicyORM]:
        return list(self.session.scalars(select(UserAccessPolicyORM).order_by(UserAccessPolicyORM.email)))

    def update(self, email: str, **changes) -> UserAccessPolicyORM | None:
        row = self.get(email)
        if row is None:
            return None
        for field in ("display_name", "role", "status", "custom_filter_limit", *PERMISSION_FIELDS):
            if field in changes and changes[field] is not None:
                value = max(0, min(3, int(changes[field]))) if field == "custom_filter_limit" else changes[field]
                setattr(row, field, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

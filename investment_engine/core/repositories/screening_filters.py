from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import SavedScreeningFilterORM


class SavedScreeningFilterRepository:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _owner(email: str) -> str:
        return email.strip().lower()

    def list_for_owner(self, owner_email: str, asset_type: str | None = None):
        stmt = select(SavedScreeningFilterORM).where(
            SavedScreeningFilterORM.owner_email == self._owner(owner_email)
        )
        if asset_type:
            stmt = stmt.where(SavedScreeningFilterORM.asset_type == asset_type)
        return list(self.session.scalars(stmt.order_by(SavedScreeningFilterORM.created_at, SavedScreeningFilterORM.name)))

    def count_for_owner(self, owner_email: str) -> int:
        return int(self.session.scalar(select(func.count()).select_from(SavedScreeningFilterORM).where(
            SavedScreeningFilterORM.owner_email == self._owner(owner_email)
        )) or 0)

    def get(self, filter_id, owner_email: str):
        return self.session.scalar(select(SavedScreeningFilterORM).where(
            SavedScreeningFilterORM.id == filter_id,
            SavedScreeningFilterORM.owner_email == self._owner(owner_email),
        ))

    def unique_name(self, owner_email: str, requested: str | None, display_name: str | None = None, *, exclude_id=None) -> str:
        base = str(requested or display_name or "Minha análise").strip()[:120] or "Minha análise"
        existing = {row.name.casefold() for row in self.list_for_owner(owner_email) if row.id != exclude_id}
        if base.casefold() not in existing:
            return base
        number = 1
        while True:
            suffix = f" ({number})"
            candidate = f"{base[:120-len(suffix)]}{suffix}"
            if candidate.casefold() not in existing:
                return candidate
            number += 1

    def create(self, *, owner_email: str, asset_type: str, filters: dict, name: str | None, display_name: str | None = None):
        row = SavedScreeningFilterORM(
            owner_email=self._owner(owner_email),
            asset_type=asset_type,
            name=self.unique_name(owner_email, name, display_name),
            filters_json=filters,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row, *, name=None, filters=None):
        if name is not None:
            row.name = self.unique_name(row.owner_email, name, exclude_id=row.id)
        if filters is not None:
            row.filters_json = filters
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def delete(self, row):
        self.session.delete(row)
        self.session.flush()

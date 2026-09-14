from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, load_only, selectinload

from ..portal.service import (
    DEFAULT_PORTAL_BOOKS,
    DEFAULT_PORTAL_PAGE,
    PortalImageUpload,
    merge_portal_page,
    normalize_book,
    normalize_sales_links,
    validate_portal_page,
)
from ...infrastructure.db.models import (
    PortalBookLinkORM,
    PortalBookORM,
    PortalMediaORM,
    PortalPageORM,
)


PORTAL_PAGE_KEY = "home"
# Transaction-scoped PostgreSQL advisory lock used only while the initial
# page/book catalog may need to be created.  A fixed, application-specific
# signed bigint keeps concurrent first requests from inserting the same
# defaults twice without introducing a permanent lock row.
PORTAL_INITIALIZATION_LOCK_ID = 0x464449504F525441


def portal_media_dict(row: PortalMediaORM) -> dict:
    return {
        "id": str(row.id),
        "filename": row.filename,
        "content_type": row.content_type,
        "sha256": row.sha256,
        "size_bytes": int(row.size_bytes),
        "created_by": row.created_by,
        "created_at": row.created_at,
    }


def portal_book_dict(row: PortalBookORM, *, include_audit: bool = False) -> dict:
    links = sorted(row.sales_links or [], key=lambda item: item.position)
    result = {
        "id": str(row.id),
        "slug": row.slug,
        "collection": row.collection,
        "kicker": row.kicker,
        "title": row.title,
        "summary": row.summary,
        "description": row.description,
        "alt_text": row.alt_text,
        "fallback_cover_path": row.fallback_cover_path,
        "cover_media_id": str(row.cover_media_id) if row.cover_media_id else None,
        "position": int(row.position),
        "hero_position": int(row.hero_position) if row.hero_position is not None else None,
        "is_published": bool(row.is_published),
        "sales_links": [
            {"id": str(link.id), "label": link.label, "url": link.url, "position": int(link.position)}
            for link in links
        ],
    }
    if include_audit:
        result.update({
            "created_by": row.created_by,
            "updated_by": row.updated_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "cover_media": portal_media_dict(row.cover_media) if row.cover_media else None,
        })
    return result


def portal_page_dict(row: PortalPageORM) -> dict:
    return {
        "page_key": row.page_key,
        # Older persisted documents are transparently completed when a new
        # editable text field is introduced in the fixed page schema.
        "content": validate_portal_page(row.content_json or {}),
        "revision": int(row.revision),
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class PortalRepository:
    """Persistence boundary for the public portal; it never commits implicitly."""

    def __init__(self, session: Session):
        self.session = session

    def get_page(self, page_key: str = PORTAL_PAGE_KEY) -> PortalPageORM | None:
        return self.session.get(PortalPageORM, str(page_key or "").strip().lower())

    def _acquire_initialization_lock(self) -> None:
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            self.session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": PORTAL_INITIALIZATION_LOCK_ID},
            )

    def _page_for_update(self, page_key: str = PORTAL_PAGE_KEY) -> PortalPageORM | None:
        statement = (
            select(PortalPageORM)
            .where(PortalPageORM.page_key == str(page_key or "").strip().lower())
            .with_for_update()
        )
        return self.session.scalar(statement)

    def ensure_defaults(self, *, actor: str = "system:migration") -> tuple[PortalPageORM, int]:
        """Create the static-compatible initial content once; return page and added book count."""
        self._acquire_initialization_lock()
        # Re-read after acquiring the PostgreSQL lock: another request may
        # have committed the defaults while this transaction was waiting.
        page = self.get_page()
        now = datetime.now(timezone.utc)
        if page is None:
            page = PortalPageORM(
                page_key=PORTAL_PAGE_KEY,
                content_json=validate_portal_page(DEFAULT_PORTAL_PAGE),
                revision=1,
                updated_by=actor,
                created_at=now,
                updated_at=now,
            )
            self.session.add(page)
            self.session.flush()

        existing = int(self.session.scalar(select(func.count()).select_from(PortalBookORM)) or 0)
        added = 0
        if existing == 0:
            for defaults in DEFAULT_PORTAL_BOOKS:
                values = dict(defaults)
                links = values.pop("sales_links", [])
                self.create_book(values, sales_links=links, actor=actor)
                added += 1
        return page, added

    def update_page(
        self,
        patch: dict,
        *,
        actor: str,
        expected_revision: int | None = None,
    ) -> PortalPageORM:
        # Lock the row before checking the revision and computing the merged
        # document.  This makes the revision check and increment atomic on
        # PostgreSQL and prevents a silent last-writer-wins overwrite.
        page = self._page_for_update()
        if page is None:
            page, _ = self.ensure_defaults(actor=actor)
        if expected_revision is not None and int(page.revision) != int(expected_revision):
            raise ValueError("portal_page_revision_conflict")
        page.content_json = merge_portal_page(page.content_json, patch)
        page.revision = int(page.revision) + 1
        page.updated_by = str(actor or "").strip().lower()[:320] or None
        page.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return page

    @staticmethod
    def _cover_metadata_option():
        return selectinload(PortalBookORM.cover_media).load_only(
            PortalMediaORM.id,
            PortalMediaORM.filename,
            PortalMediaORM.content_type,
            PortalMediaORM.sha256,
            PortalMediaORM.size_bytes,
            PortalMediaORM.created_by,
            PortalMediaORM.created_at,
        )

    def list_books(
        self,
        *,
        include_unpublished: bool = False,
        include_media_metadata: bool = False,
    ) -> list[PortalBookORM]:
        options = [selectinload(PortalBookORM.sales_links)]
        if include_media_metadata:
            options.append(self._cover_metadata_option())
        statement = select(PortalBookORM).options(*options)
        if not include_unpublished:
            statement = statement.where(PortalBookORM.is_published.is_(True))
        statement = statement.order_by(PortalBookORM.position, PortalBookORM.title, PortalBookORM.id)
        return list(self.session.scalars(statement))

    def get_book(
        self,
        identifier: UUID | str,
        *,
        include_media_metadata: bool = False,
    ) -> PortalBookORM | None:
        options = [selectinload(PortalBookORM.sales_links)]
        if include_media_metadata:
            options.append(self._cover_metadata_option())
        statement = select(PortalBookORM).options(*options)
        try:
            book_id = identifier if isinstance(identifier, UUID) else UUID(str(identifier))
            statement = statement.where(PortalBookORM.id == book_id)
        except (TypeError, ValueError):
            statement = statement.where(PortalBookORM.slug == str(identifier or "").strip().lower())
        return self.session.scalar(statement)

    def _assert_media_exists(self, media_id: UUID | None) -> None:
        if media_id is not None and self.session.get(PortalMediaORM, media_id) is None:
            raise ValueError("portal_media_not_found")

    def _delete_media_if_orphaned(self, media_id: UUID | None) -> bool:
        if media_id is None:
            return False
        referenced = int(self.session.scalar(
            select(func.count()).select_from(PortalBookORM).where(PortalBookORM.cover_media_id == media_id)
        ) or 0)
        if referenced:
            return False
        media = self.session.get(PortalMediaORM, media_id)
        if media is None:
            return False
        self.session.delete(media)
        self.session.flush()
        return True

    def _release_hero_position(self, position: int | None, *, except_book_id: UUID | None = None) -> None:
        if position is None:
            return
        statement = select(PortalBookORM).where(PortalBookORM.hero_position == position)
        if except_book_id is not None:
            statement = statement.where(PortalBookORM.id != except_book_id)
        for other in self.session.scalars(statement):
            other.hero_position = None
            other.updated_at = datetime.now(timezone.utc)

    def create_book(
        self,
        values: dict,
        *,
        sales_links: list[dict] | None = None,
        actor: str,
    ) -> PortalBookORM:
        clean = normalize_book(values, partial=False)
        if self.get_book(clean["slug"]) is not None:
            raise ValueError("portal_book_slug_exists")
        clean.setdefault("kicker", "")
        clean.setdefault("summary", "")
        clean.setdefault("description", "")
        clean.setdefault("fallback_cover_path", None)
        clean.setdefault("cover_media_id", None)
        clean.setdefault("position", 100)
        clean.setdefault("hero_position", None)
        clean.setdefault("is_published", True)
        self._assert_media_exists(clean["cover_media_id"])
        self._release_hero_position(clean["hero_position"])
        now = datetime.now(timezone.utc)
        row = PortalBookORM(
            **clean,
            created_by=str(actor or "").strip().lower()[:320] or None,
            updated_by=str(actor or "").strip().lower()[:320] or None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        self.replace_sales_links(row, sales_links or [])
        self.session.refresh(row, attribute_names=["sales_links"])
        return row

    def update_book(
        self,
        identifier: UUID | str,
        values: dict,
        *,
        sales_links: list[dict] | None = None,
        actor: str,
    ) -> PortalBookORM | None:
        row = self.get_book(identifier, include_media_metadata=True)
        if row is None:
            return None
        previous_cover_media_id = row.cover_media_id
        clean = normalize_book(values, partial=True)
        if "slug" in clean and clean["slug"] != row.slug:
            duplicate = self.get_book(clean["slug"])
            if duplicate is not None and duplicate.id != row.id:
                raise ValueError("portal_book_slug_exists")
        if "cover_media_id" in clean:
            self._assert_media_exists(clean["cover_media_id"])
        if "hero_position" in clean:
            self._release_hero_position(clean["hero_position"], except_book_id=row.id)
        for field, value in clean.items():
            setattr(row, field, value)
        row.updated_by = str(actor or "").strip().lower()[:320] or None
        row.updated_at = datetime.now(timezone.utc)
        if sales_links is not None:
            self.replace_sales_links(row, sales_links)
        self.session.flush()
        if previous_cover_media_id != row.cover_media_id:
            self._delete_media_if_orphaned(previous_cover_media_id)
        self.session.refresh(row, attribute_names=["sales_links", "cover_media"])
        return row

    def replace_sales_links(self, book: PortalBookORM, values: list[dict]) -> list[PortalBookLinkORM]:
        clean = normalize_sales_links(values)
        book.sales_links.clear()
        self.session.flush()
        now = datetime.now(timezone.utc)
        for item in clean:
            book.sales_links.append(PortalBookLinkORM(**item, created_at=now, updated_at=now))
        self.session.flush()
        return list(book.sales_links)

    def reorder_books(self, ordered_ids: list[UUID | str], *, actor: str) -> list[PortalBookORM]:
        parsed = []
        for value in ordered_ids:
            try:
                book_id = value if isinstance(value, UUID) else UUID(str(value))
            except (TypeError, ValueError):
                raise ValueError("portal_book_order_invalid")
            if book_id in parsed:
                raise ValueError("portal_book_order_duplicate")
            parsed.append(book_id)
        books = self.list_books(include_unpublished=True, include_media_metadata=True)
        by_id = {book.id: book for book in books}
        if set(parsed) != set(by_id):
            raise ValueError("portal_book_order_must_include_all")
        now = datetime.now(timezone.utc)
        for position, book_id in enumerate(parsed, start=1):
            row = by_id[book_id]
            row.position = position * 10
            row.updated_by = str(actor or "").strip().lower()[:320] or None
            row.updated_at = now
        self.session.flush()
        return self.list_books(include_unpublished=True, include_media_metadata=True)

    def delete_book(self, identifier: UUID | str) -> bool:
        row = self.get_book(identifier)
        if row is None:
            return False
        cover_media_id = row.cover_media_id
        self.session.delete(row)
        self.session.flush()
        self._delete_media_if_orphaned(cover_media_id)
        return True

    def save_media(self, upload: PortalImageUpload, *, actor: str) -> tuple[PortalMediaORM, bool]:
        existing = self.session.scalar(select(PortalMediaORM).where(PortalMediaORM.sha256 == upload.sha256))
        if existing is not None:
            return existing, False
        row = PortalMediaORM(
            filename=upload.filename,
            content_type=upload.content_type,
            content=upload.content,
            sha256=upload.sha256,
            size_bytes=upload.size_bytes,
            created_by=str(actor or "").strip().lower()[:320] or None,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def get_media(self, media_id: UUID | str) -> PortalMediaORM | None:
        try:
            clean = media_id if isinstance(media_id, UUID) else UUID(str(media_id))
        except (TypeError, ValueError):
            return None
        return self.session.get(PortalMediaORM, clean)

    def get_public_media(self, media_id: UUID | str) -> PortalMediaORM | None:
        """Return media only while at least one published book uses it.

        Uploading a cover is an administrative draft action.  A UUID is not an
        authorization boundary, so unattached images and covers used only by
        hidden books must not be retrievable from the public endpoint.
        """
        try:
            clean = media_id if isinstance(media_id, UUID) else UUID(str(media_id))
        except (TypeError, ValueError):
            return None
        return self.session.scalar(
            select(PortalMediaORM).where(
                PortalMediaORM.id == clean,
                PortalMediaORM.books.any(PortalBookORM.is_published.is_(True)),
            )
        )

    def delete_media(self, media_id: UUID | str) -> bool:
        row = self.get_media(media_id)
        if row is None:
            return False
        referenced = int(self.session.scalar(
            select(func.count()).select_from(PortalBookORM).where(PortalBookORM.cover_media_id == row.id)
        ) or 0)
        if referenced:
            raise ValueError("portal_media_in_use")
        self.session.delete(row)
        self.session.flush()
        return True

    def public_payload(self) -> dict:
        page = self.get_page()
        if page is None:
            page, _ = self.ensure_defaults()
        books = self.list_books(include_unpublished=False)
        return {
            "page": validate_portal_page(page.content_json or {}),
            "revision": int(page.revision),
            "updated_at": page.updated_at,
            "books": [portal_book_dict(book) for book in books],
        }

    def admin_payload(self) -> dict:
        page = self.get_page()
        if page is None:
            page, _ = self.ensure_defaults()
        return {
            **portal_page_dict(page),
            "books": [
                portal_book_dict(book, include_audit=True)
                for book in self.list_books(include_unpublished=True, include_media_metadata=True)
            ],
        }

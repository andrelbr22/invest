from __future__ import annotations

import hashlib

from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from investment_engine.core.portal.service import PortalImageUpload
from investment_engine.core.repositories.portal import (
    PORTAL_INITIALIZATION_LOCK_ID,
    PortalRepository,
)
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import PortalMediaORM


def _upload(name: str, content: bytes) -> PortalImageUpload:
    return PortalImageUpload(
        filename=name,
        content_type="image/png",
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def _book_values(slug: str, media_id) -> dict:
    return {
        "slug": slug,
        "collection": "complementary",
        "title": slug.replace("-", " ").title(),
        "alt_text": f"Capa de {slug}",
        "cover_media_id": media_id,
        "is_published": True,
    }


def test_public_catalog_does_not_fetch_cover_metadata_or_binary_content():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = PortalRepository(session)
        media, _ = repo.save_media(_upload("large.png", b"large-cover-bytes"), actor="owner@example.com")
        repo.create_book(_book_values("large-cover", media.id), actor="owner@example.com")
        session.commit()

    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as session:
            public_book = next(
                item for item in PortalRepository(session).list_books() if item.slug == "large-cover"
            )
            assert "cover_media" in inspect(public_book).unloaded
            assert not any("from portal_media" in statement for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    with Session(engine) as session:
        admin_book = next(
            item
            for item in PortalRepository(session).list_books(
                include_unpublished=True,
                include_media_metadata=True,
            )
            if item.slug == "large-cover"
        )
        assert admin_book.cover_media is not None
        assert admin_book.cover_media.filename == "large.png"
        assert "content" in inspect(admin_book.cover_media).unloaded


def test_media_body_remains_available_through_lazy_binary_load():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        media, _ = PortalRepository(session).save_media(
            _upload("cover.png", b"binary-body"), actor="owner@example.com",
        )
        media_id = media.id
        session.commit()

    with Session(engine) as session:
        media = PortalRepository(session).get_media(media_id)
        assert media is not None
        assert "content" in inspect(media).unloaded
        assert media.content == b"binary-body"
        assert "content" not in inspect(media).unloaded


def test_only_covers_referenced_by_a_published_book_are_public():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = PortalRepository(session)
        draft, _ = repo.save_media(_upload("draft.png", b"draft"), actor="owner@example.com")
        published, _ = repo.save_media(
            _upload("published.png", b"published"), actor="owner@example.com",
        )
        hidden = repo.create_book(_book_values("hidden-book", draft.id), actor="owner@example.com")
        hidden.is_published = False
        repo.create_book(_book_values("published-book", published.id), actor="owner@example.com")
        draft_id, published_id = draft.id, published.id
        session.commit()

    with Session(engine) as session:
        repo = PortalRepository(session)
        assert repo.get_public_media(draft_id) is None
        assert repo.get_public_media(published_id) is not None


def test_replaced_and_deleted_covers_are_removed_only_when_orphaned():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = PortalRepository(session)
        shared, _ = repo.save_media(_upload("shared.png", b"shared"), actor="owner@example.com")
        replacement, _ = repo.save_media(_upload("new.png", b"replacement"), actor="owner@example.com")
        first = repo.create_book(_book_values("first-book", shared.id), actor="owner@example.com")
        second = repo.create_book(_book_values("second-book", shared.id), actor="owner@example.com")
        shared_id, replacement_id, first_id, second_id = shared.id, replacement.id, first.id, second.id
        session.commit()

    with Session(engine) as session:
        repo = PortalRepository(session)
        repo.update_book(
            first_id,
            {"cover_media_id": replacement_id},
            actor="owner@example.com",
        )
        assert session.get(PortalMediaORM, shared_id) is not None
        repo.delete_book(second_id)
        assert session.get(PortalMediaORM, shared_id) is None
        repo.delete_book(first_id)
        assert session.get(PortalMediaORM, replacement_id) is None


def test_page_revision_query_uses_a_database_row_lock():
    class ScalarRecorder:
        statement = None

        def scalar(self, statement):
            self.statement = statement
            return None

    session = ScalarRecorder()
    assert PortalRepository(session)._page_for_update() is None
    compiled = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in compiled.upper()


def test_postgresql_initialization_uses_transaction_scoped_advisory_lock():
    class PostgreSQLBind:
        class dialect:
            name = "postgresql"

    class ExecuteRecorder:
        calls = []

        @staticmethod
        def get_bind():
            return PostgreSQLBind()

        @classmethod
        def execute(cls, statement, parameters):
            cls.calls.append((str(statement), parameters))

    PortalRepository(ExecuteRecorder())._acquire_initialization_lock()
    assert ExecuteRecorder.calls == [
        ("SELECT pg_advisory_xact_lock(:lock_id)", {"lock_id": PORTAL_INITIALIZATION_LOCK_ID})
    ]


def test_default_catalog_initialization_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = PortalRepository(session)
        first_page, first_added = repo.ensure_defaults()
        second_page, second_added = repo.ensure_defaults()
        assert first_page.page_key == second_page.page_key == "home"
        assert first_added == 7
        assert second_added == 0
        assert len(list(session.scalars(select(PortalMediaORM)))) == 0


def test_old_page_documents_receive_new_editable_text_defaults_on_read():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = PortalRepository(session)
        page, _ = repo.ensure_defaults()
        content = dict(page.content_json)
        content["brand"] = {"primary": "Formação", "secondary": "do Investidor"}
        content["navigation"] = {
            "books": "Livros", "purpose": "Nossa proposta", "platform": "Plataforma",
        }
        page.content_json = content
        session.commit()

    with Session(engine) as session:
        payload = PortalRepository(session).admin_payload()
        assert payload["content"]["brand"]["monogram"] == "FI"
        assert payload["content"]["navigation"]["skip"] == "Ir para o conteúdo"
        assert payload["content"]["navigation"]["admin"] == "Ajustes da página"

"""V1.23 editable public portal, books, sales links and persistent covers.

Revision ID: 0025_v1_23_portal_cms
Revises: 0024_v1_23_investor_events
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_v1_23_portal_cms"
down_revision = "0024_v1_23_investor_events"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    tables = _tables()

    if "access_levels" in tables and "can_manage_portal" not in _columns("access_levels"):
        op.add_column(
            "access_levels",
            sa.Column("can_manage_portal", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.execute("UPDATE access_levels SET can_manage_portal = TRUE WHERE slug = 'owner'")

    if "user_access_policies" in tables and "can_manage_portal" not in _columns("user_access_policies"):
        op.add_column(
            "user_access_policies",
            sa.Column("can_manage_portal", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.execute(
            "UPDATE user_access_policies SET can_manage_portal = TRUE "
            "WHERE role = 'owner' OR access_level_id IN "
            "(SELECT id FROM access_levels WHERE slug = 'owner')"
        )

    if "portal_pages" not in tables:
        op.create_table(
            "portal_pages",
            sa.Column("page_key", sa.String(length=32), nullable=False),
            sa.Column("content_json", sa.JSON(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_by", sa.String(length=320)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("page_key"),
            sa.CheckConstraint("revision >= 1", name="ck_portal_pages_revision_positive"),
        )

    if "portal_media" not in tables:
        op.create_table(
            "portal_media",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=40), nullable=False),
            sa.Column("content", sa.LargeBinary(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.String(length=320)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sha256", name="uq_portal_media_sha256"),
            sa.CheckConstraint(
                "size_bytes > 0 AND size_bytes <= 4194304",
                name="ck_portal_media_safe_size",
            ),
        )
        op.create_index("ix_portal_media_created_at", "portal_media", ["created_at"])

    if "portal_books" not in tables:
        op.create_table(
            "portal_books",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("slug", sa.String(length=100), nullable=False),
            sa.Column("collection", sa.String(length=40), nullable=False, server_default="complementary"),
            sa.Column("kicker", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("alt_text", sa.String(length=500), nullable=False),
            sa.Column("fallback_cover_path", sa.String(length=500)),
            sa.Column("cover_media_id", sa.Uuid()),
            sa.Column("position", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("hero_position", sa.Integer()),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(length=320)),
            sa.Column("updated_by", sa.String(length=320)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["cover_media_id"], ["portal_media.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug", name="uq_portal_books_slug"),
            sa.CheckConstraint("position >= 0", name="ck_portal_books_position_nonnegative"),
            sa.CheckConstraint(
                "hero_position IS NULL OR (hero_position >= 1 AND hero_position <= 3)",
                name="ck_portal_books_hero_position",
            ),
        )
        op.create_index("ix_portal_books_slug", "portal_books", ["slug"], unique=True)
        op.create_index("ix_portal_books_cover_media_id", "portal_books", ["cover_media_id"])
        op.create_index(
            "ix_portal_books_published_position",
            "portal_books", ["is_published", "collection", "position"],
        )
        op.create_index("ix_portal_books_hero_position", "portal_books", ["hero_position"])

    if "portal_book_links" not in tables:
        op.create_table(
            "portal_book_links",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("book_id", sa.Uuid(), nullable=False),
            sa.Column("label", sa.String(length=100), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["book_id"], ["portal_books.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("book_id", "position", name="uq_portal_book_link_position"),
            sa.CheckConstraint(
                "position >= 1 AND position <= 3",
                name="ck_portal_book_links_position",
            ),
        )
        op.create_index("ix_portal_book_links_book", "portal_book_links", ["book_id"])


def downgrade():
    tables = _tables()
    if "portal_book_links" in tables:
        op.drop_index("ix_portal_book_links_book", table_name="portal_book_links")
        op.drop_table("portal_book_links")
    if "portal_books" in tables:
        op.drop_index("ix_portal_books_hero_position", table_name="portal_books")
        op.drop_index("ix_portal_books_published_position", table_name="portal_books")
        op.drop_index("ix_portal_books_cover_media_id", table_name="portal_books")
        op.drop_index("ix_portal_books_slug", table_name="portal_books")
        op.drop_table("portal_books")
    if "portal_media" in tables:
        op.drop_index("ix_portal_media_created_at", table_name="portal_media")
        op.drop_table("portal_media")
    if "portal_pages" in tables:
        op.drop_table("portal_pages")
    if "user_access_policies" in tables and "can_manage_portal" in _columns("user_access_policies"):
        op.drop_column("user_access_policies", "can_manage_portal")
    if "access_levels" in tables and "can_manage_portal" in _columns("access_levels"):
        op.drop_column("access_levels", "can_manage_portal")

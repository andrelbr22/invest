"""V1.23.1 R2 safe archive for queue and operational retention.

Revision ID: 0028_v1_23_operational_retention
Revises: 0027_v1_23_analysis_settings
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_v1_23_operational_retention"
down_revision = "0027_v1_23_analysis_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "operational_archive" not in tables:
        op.create_table(
            "operational_archive",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("entity_type", sa.String(length=40), nullable=False),
            sa.Column("source_id", sa.String(length=320), nullable=False),
            sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1"),
            sa.Column("checksum", sa.String(length=64), nullable=False),
            sa.Column("record_json", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("entity_type", "source_id", name="uq_operational_archive_source"),
        )
        op.create_index(
            "ix_operational_archive_type_archived",
            "operational_archive", ["entity_type", "archived_at"], unique=False,
        )
        op.create_index(
            "ix_operational_archive_source_updated",
            "operational_archive", ["source_updated_at"], unique=False,
        )
    background_indexes = {
        item["name"] for item in sa.inspect(op.get_bind()).get_indexes("background_jobs")
    }
    if "ix_background_jobs_retention_scan" not in background_indexes:
        op.create_index(
            "ix_background_jobs_retention_scan",
            "background_jobs", ["finished_at", "id"], unique=False,
            postgresql_where=sa.text(
                "status = 'succeeded' AND requested_by IS NULL AND finished_at IS NOT NULL"
            ),
            sqlite_where=sa.text(
                "status = 'succeeded' AND requested_by IS NULL AND finished_at IS NOT NULL"
            ),
        )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_operational_archive_mutation()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'operational_archive is append-only';
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("DROP TRIGGER IF EXISTS operational_archive_immutable ON operational_archive"))
        op.execute(sa.text("""
            CREATE TRIGGER operational_archive_immutable
            BEFORE UPDATE OR DELETE ON operational_archive
            FOR EACH ROW EXECUTE FUNCTION prevent_operational_archive_mutation()
        """))


def downgrade() -> None:
    if "operational_archive" in set(sa.inspect(op.get_bind()).get_table_names()):
        archived_rows = op.get_bind().execute(
            sa.text("SELECT COUNT(*) FROM operational_archive"),
        ).scalar_one()
        if archived_rows:
            # The table is additive and unknown to the previous application.
            # Keep it intact rather than destroying the only archived copies;
            # a later re-upgrade detects and reuses the existing table.
            return
        if op.get_bind().dialect.name == "postgresql":
            op.execute(sa.text("DROP TRIGGER IF EXISTS operational_archive_immutable ON operational_archive"))
            op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_operational_archive_mutation()"))
        op.drop_index("ix_operational_archive_source_updated", table_name="operational_archive")
        op.drop_index("ix_operational_archive_type_archived", table_name="operational_archive")
        op.drop_table("operational_archive")
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("background_jobs")}
    if "ix_background_jobs_retention_scan" in indexes:
        op.drop_index("ix_background_jobs_retention_scan", table_name="background_jobs")

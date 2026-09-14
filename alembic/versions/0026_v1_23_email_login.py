"""V1.23 passwordless e-mail authentication.

Revision ID: 0026_v1_23_email_login
Revises: 0025_v1_23_portal_cms
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_v1_23_email_login"
down_revision = "0025_v1_23_portal_cms"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "email_login_codes" in inspector.get_table_names():
        return
    op.create_table(
        "email_login_codes",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("salt", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("email"),
    )
    op.create_index("ix_email_login_codes_expires_at", "email_login_codes", ["expires_at"])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if "email_login_codes" not in inspector.get_table_names():
        return
    op.drop_index("ix_email_login_codes_expires_at", table_name="email_login_codes")
    op.drop_table("email_login_codes")

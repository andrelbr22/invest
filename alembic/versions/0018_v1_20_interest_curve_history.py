"""V1.20 interest curve history.

Revision ID: 0018_v1_20_curve_history
Revises: 0017_v1_20_personal_finances
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_v1_20_curve_history"
down_revision = "0017_v1_20_personal_finances"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interest_curve_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("curve_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("source", sa.String(length=160)),
        sa.Column("source_url", sa.String(length=500)),
        sa.Column("points_json", sa.JSON(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_date", "curve_type", name="uq_interest_curve_reference_type"),
    )
    op.create_index("ix_interest_curve_reference", "interest_curve_snapshots", ["reference_date"])


def downgrade():
    op.drop_table("interest_curve_snapshots")

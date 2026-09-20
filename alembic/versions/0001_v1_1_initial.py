"""V1.1 initial persistence schema.

Revision ID: 0001_v1_1
Revises: 
Create Date: 2026-08-21
"""
from alembic import op
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db import models  # noqa: F401

revision = "0001_v1_1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

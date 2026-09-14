"""V1.23 official investor events and data-quality foundation.

Revision ID: 0024_v1_23_investor_events
Revises: 0023_v1_22_screener_performance
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_v1_23_investor_events"
down_revision = "0023_v1_22_screener_performance"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    tables = _tables()
    if "corporate_events" not in tables:
        op.create_table(
            "corporate_events",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("asset_id", sa.Uuid(), nullable=True),
            sa.Column("ticker", sa.String(length=24), nullable=True),
            sa.Column("external_id", sa.String(length=160), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("isin", sa.String(length=24), nullable=True),
            sa.Column("announced_on", sa.Date(), nullable=True),
            sa.Column("last_cum_date", sa.Date(), nullable=True),
            sa.Column("ex_date", sa.Date(), nullable=True),
            sa.Column("payment_date", sa.Date(), nullable=True),
            sa.Column("amount", sa.Numeric(24, 10), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="BRL"),
            sa.Column("related_period", sa.String(length=80), nullable=True),
            sa.Column("source", sa.String(length=80), nullable=False, server_default="B3"),
            sa.Column("source_url", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="confirmed"),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "external_id", name="uq_corporate_event_source_external"),
        )
        op.create_index("ix_corporate_events_asset_id", "corporate_events", ["asset_id"])
        op.create_index("ix_corporate_events_ticker", "corporate_events", ["ticker"])
        op.create_index("ix_corporate_events_event_type", "corporate_events", ["event_type"])
        op.create_index("ix_corporate_events_isin", "corporate_events", ["isin"])
        op.create_index("ix_corporate_events_asset_payment", "corporate_events", ["asset_id", "payment_date"])
        op.create_index("ix_corporate_events_ex_date", "corporate_events", ["ex_date"])

    if "relevant_facts" not in tables:
        op.create_table(
            "relevant_facts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("external_id", sa.String(length=160), nullable=False),
            sa.Column("issuer_cnpj", sa.String(length=24), nullable=True),
            sa.Column("issuer_name", sa.String(length=255), nullable=False),
            sa.Column("cvm_code", sa.String(length=24), nullable=True),
            sa.Column("reference_date", sa.Date(), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("subject", sa.String(length=500), nullable=True),
            sa.Column("document_url", sa.String(length=1000), nullable=False),
            sa.Column("protocol", sa.String(length=80), nullable=True),
            sa.Column("version", sa.String(length=24), nullable=True),
            sa.Column("tickers_json", sa.JSON(), nullable=False),
            sa.Column("source", sa.String(length=80), nullable=False, server_default="CVM IPE"),
            sa.Column("source_url", sa.String(length=500), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "external_id", name="uq_relevant_fact_source_external"),
        )
        op.create_index("ix_relevant_facts_issuer_cnpj", "relevant_facts", ["issuer_cnpj"])
        op.create_index("ix_relevant_facts_cvm_code", "relevant_facts", ["cvm_code"])
        op.create_index("ix_relevant_facts_delivered", "relevant_facts", ["delivered_at"])
        op.create_index("ix_relevant_facts_cnpj_delivered", "relevant_facts", ["issuer_cnpj", "delivered_at"])

    if "official_calendar_events" not in tables:
        op.create_table(
            "official_calendar_events",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("external_id", sa.String(length=160), nullable=False),
            sa.Column("calendar_year", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("event_date", sa.Date(), nullable=False),
            sa.Column("time_label", sa.String(length=80), nullable=True),
            sa.Column("region", sa.String(length=80), nullable=True),
            sa.Column("source", sa.String(length=120), nullable=False),
            sa.Column("source_url", sa.String(length=500), nullable=False),
            sa.Column("official", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "external_id", name="uq_official_calendar_source_external"),
        )
        op.create_index("ix_official_calendar_events_calendar_year", "official_calendar_events", ["calendar_year"])
        op.create_index("ix_official_calendar_events_category", "official_calendar_events", ["category"])
        op.create_index("ix_official_calendar_date_category", "official_calendar_events", ["event_date", "category"])

    if "alb_universe_observations" not in tables:
        op.create_table(
            "alb_universe_observations",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("reference_date", sa.Date(), nullable=False),
            sa.Column("preset_version", sa.String(length=40), nullable=False),
            sa.Column("filters_hash", sa.String(length=64), nullable=False),
            sa.Column("asset_count", sa.Integer(), nullable=False),
            sa.Column("target_min", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("target_max", sa.Integer(), nullable=False, server_default="20"),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("tickers_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("reference_date", "preset_version", name="uq_alb_observation_date_version"),
        )
        op.create_index("ix_alb_observations_created", "alb_universe_observations", ["created_at"])


def downgrade():
    tables = _tables()
    if "alb_universe_observations" in tables:
        op.drop_index("ix_alb_observations_created", table_name="alb_universe_observations")
        op.drop_table("alb_universe_observations")
    if "official_calendar_events" in tables:
        op.drop_index("ix_official_calendar_date_category", table_name="official_calendar_events")
        op.drop_index("ix_official_calendar_events_category", table_name="official_calendar_events")
        op.drop_index("ix_official_calendar_events_calendar_year", table_name="official_calendar_events")
        op.drop_table("official_calendar_events")
    if "relevant_facts" in tables:
        op.drop_index("ix_relevant_facts_cnpj_delivered", table_name="relevant_facts")
        op.drop_index("ix_relevant_facts_delivered", table_name="relevant_facts")
        op.drop_index("ix_relevant_facts_cvm_code", table_name="relevant_facts")
        op.drop_index("ix_relevant_facts_issuer_cnpj", table_name="relevant_facts")
        op.drop_table("relevant_facts")
    if "corporate_events" in tables:
        op.drop_index("ix_corporate_events_ex_date", table_name="corporate_events")
        op.drop_index("ix_corporate_events_asset_payment", table_name="corporate_events")
        op.drop_index("ix_corporate_events_isin", table_name="corporate_events")
        op.drop_index("ix_corporate_events_event_type", table_name="corporate_events")
        op.drop_index("ix_corporate_events_ticker", table_name="corporate_events")
        op.drop_index("ix_corporate_events_asset_id", table_name="corporate_events")
        op.drop_table("corporate_events")

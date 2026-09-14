from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import (
    AlbUniverseObservationORM,
    AssetORM,
    CorporateEventORM,
    OfficialCalendarEventORM,
    PortfolioORM,
    PortfolioPositionORM,
    RelevantFactORM,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _code(value: object) -> str:
    clean = _digits(value)
    return clean.lstrip("0") or clean


def _issuer_name_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in normalized if not unicodedata.combining(char)).lower()
    removable = {
        "sa", "s", "a", "companhia", "cia", "aberta", "sociedade",
        "anonima", "ltda", "holding", "holdings",
    }
    words = [word for word in re.findall(r"[a-z0-9]+", plain) if word not in removable]
    return " ".join(words)


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def corporate_event_dict(row: CorporateEventORM, *, quantity: object = None,
                         portfolio_name: str | None = None) -> dict:
    amount = float(row.amount) if row.amount is not None else None
    units = float(quantity) if quantity is not None else None
    return {
        "id": str(row.id), "ticker": row.ticker, "event_type": row.event_type,
        "isin": row.isin, "announced_on": row.announced_on,
        "last_cum_date": row.last_cum_date, "ex_date": row.ex_date,
        "payment_date": row.payment_date, "amount": amount,
        "currency": row.currency, "related_period": row.related_period,
        "status": row.status, "source": row.source, "source_url": row.source_url,
        "retrieved_at": row.retrieved_at, "quantity": units,
        "estimated_gross_amount": round(amount * units, 2) if amount is not None and units is not None else None,
        "portfolio_name": portfolio_name, "metadata": dict(row.metadata_json or {}),
    }


def relevant_fact_dict(row: RelevantFactORM) -> dict:
    return {
        "id": str(row.id), "issuer_cnpj": row.issuer_cnpj,
        "issuer_name": row.issuer_name, "cvm_code": row.cvm_code,
        "reference_date": row.reference_date, "delivered_at": row.delivered_at,
        "subject": row.subject, "document_url": row.document_url,
        "protocol": row.protocol, "version": row.version,
        "tickers": list(row.tickers_json or []), "source": row.source,
        "source_url": row.source_url, "retrieved_at": row.retrieved_at,
    }


def official_calendar_event_dict(row: OfficialCalendarEventORM) -> dict:
    return {
        "id": str(row.id), "calendar_year": row.calendar_year,
        "category": row.category, "title": row.title, "date": row.event_date,
        "time": row.time_label, "region": row.region, "source": row.source,
        "source_url": row.source_url, "official": bool(row.official),
        "metadata": dict(row.metadata_json or {}), "retrieved_at": row.retrieved_at,
    }


def alb_observation_dict(row: AlbUniverseObservationORM) -> dict:
    return {
        "id": str(row.id), "reference_date": row.reference_date,
        "preset_version": row.preset_version, "asset_count": row.asset_count,
        "target_min": row.target_min, "target_max": row.target_max,
        "status": row.status, "tickers": list(row.tickers_json or []),
        "filters_hash": row.filters_hash, "updated_at": row.updated_at,
    }


class InvestorEventsRepository:
    def __init__(self, session: Session):
        self.session = session

    def asset_issuer_mapping(self) -> dict[str, dict[str, list[str]]]:
        """Map assets through strong issuer IDs, with exact legal-name fallback.

        Current catalog providers store additional identifiers in
        ``metadata_json`` as they become available.  This keeps the CVM feed
        useful while older rows are progressively enriched and avoids making
        CNPJ the only possible join path.
        """
        collected: dict[str, dict[str, set[str]]] = {
            "by_cnpj": {}, "by_cvm_code": {}, "by_name": {},
        }

        def add(group: str, key: str, ticker: str) -> None:
            if key:
                collected[group].setdefault(key, set()).add(ticker)

        for row in self.session.scalars(select(AssetORM).where(AssetORM.is_active.is_(True))):
            metadata = dict(row.metadata_json or {})
            cnpj = _digits(
                metadata.get("issuer_cnpj") or metadata.get("cnpj")
                or metadata.get("company_cnpj") or metadata.get("cnpj_company")
            )
            cvm_code = _code(
                metadata.get("cvm_code") or metadata.get("code_cvm")
                or metadata.get("codeCVM") or metadata.get("codigo_cvm")
            )
            add("by_cnpj", cnpj, row.ticker)
            add("by_cvm_code", cvm_code, row.ticker)
            for value in (
                metadata.get("issuer_name"), metadata.get("legal_name"),
                metadata.get("company_name"), metadata.get("trading_name"), row.name,
            ):
                add("by_name", _issuer_name_key(value), row.ticker)
        return {
            group: {key: sorted(values) for key, values in mapping.items()}
            for group, mapping in collected.items()
        }

    def asset_tickers_by_cnpj(self) -> dict[str, list[str]]:
        """Compatibility view for callers that only know the old CNPJ map."""
        return self.asset_issuer_mapping()["by_cnpj"]

    def update_asset_issuer_metadata(self, asset: AssetORM, identity: dict) -> dict:
        """Progressively enrich an asset with normalized official identifiers."""
        current = dict(asset.metadata_json or {})
        values = {
            "issuer_cnpj": _digits(identity.get("issuer_cnpj")) or None,
            "cvm_code": _code(identity.get("cvm_code")) or None,
            "issuing_company": str(identity.get("issuing_company") or "").strip().upper() or None,
            "issuer_name": str(identity.get("issuer_name") or "").strip() or None,
            "isin": str(identity.get("isin") or "").strip().upper() or None,
        }
        for key, value in values.items():
            if value and not current.get(key):
                current[key] = value
        asset.metadata_json = current
        asset.updated_at = utcnow()
        self.session.flush()
        return current

    def upsert_corporate_event(self, item: dict, *, asset: AssetORM | None = None) -> tuple[CorporateEventORM, bool]:
        source = str(item.get("source") or "B3")[:80]
        external_id = str(item.get("external_id") or "").strip()[:160]
        if not external_id:
            raise ValueError("corporate_event_external_id_required")
        row = self.session.scalar(select(CorporateEventORM).where(
            CorporateEventORM.source == source,
            CorporateEventORM.external_id == external_id,
        ))
        created = row is None
        if row is None:
            row = CorporateEventORM(source=source, external_id=external_id)
            self.session.add(row)
        row.asset_id = asset.id if asset is not None else item.get("asset_id")
        row.ticker = (asset.ticker if asset is not None else str(item.get("ticker") or "").upper()) or None
        row.event_type = str(item.get("event_type") or "cash_distribution")[:40]
        row.isin = str(item.get("isin") or "")[:24] or None
        row.announced_on = item.get("announced_on")
        row.last_cum_date = item.get("last_cum_date")
        row.ex_date = item.get("ex_date")
        row.payment_date = item.get("payment_date")
        row.amount = _decimal(item.get("amount"))
        row.currency = str(item.get("currency") or "BRL")[:8]
        row.related_period = str(item.get("related_period") or "")[:80] or None
        row.source_url = str(item.get("source_url") or "")[:500]
        row.status = str(item.get("status") or "confirmed")[:24]
        row.metadata_json = dict(item.get("metadata") or {})
        row.retrieved_at = item.get("retrieved_at") or utcnow()
        row.updated_at = utcnow()
        self.session.flush()
        return row, created

    def upsert_relevant_fact(self, item: dict) -> tuple[RelevantFactORM, bool]:
        source = str(item.get("source") or "CVM IPE")[:80]
        external_id = str(item.get("external_id") or "").strip()[:160]
        if not external_id:
            raise ValueError("relevant_fact_external_id_required")
        row = self.session.scalar(select(RelevantFactORM).where(
            RelevantFactORM.source == source,
            RelevantFactORM.external_id == external_id,
        ))
        created = row is None
        if row is None:
            row = RelevantFactORM(source=source, external_id=external_id)
            self.session.add(row)
        cnpj = _digits(item.get("issuer_cnpj")) or None
        row.issuer_cnpj = cnpj
        row.issuer_name = str(item.get("issuer_name") or "Emissor não identificado")[:255]
        row.cvm_code = str(item.get("cvm_code") or "")[:24] or None
        row.reference_date = item.get("reference_date")
        row.delivered_at = item.get("delivered_at") or utcnow()
        row.subject = str(item.get("subject") or "")[:500] or None
        row.document_url = str(item.get("document_url") or "")[:1000]
        row.protocol = str(item.get("protocol") or "")[:80] or None
        row.version = str(item.get("version") or "")[:24] or None
        row.tickers_json = sorted(set(str(value).upper() for value in item.get("tickers") or [] if value))
        row.source_url = str(item.get("source_url") or "")[:500]
        row.metadata_json = dict(item.get("metadata") or {})
        row.retrieved_at = item.get("retrieved_at") or utcnow()
        row.updated_at = utcnow()
        self.session.flush()
        return row, created

    def upsert_calendar_event(self, item: dict) -> tuple[OfficialCalendarEventORM, bool]:
        source = str(item.get("source") or "Fonte oficial")[:120]
        external_id = str(item.get("external_id") or "").strip()[:160]
        event_date = item.get("event_date") or item.get("date")
        if not external_id or not isinstance(event_date, date):
            raise ValueError("official_calendar_identity_required")
        row = self.session.scalar(select(OfficialCalendarEventORM).where(
            OfficialCalendarEventORM.source == source,
            OfficialCalendarEventORM.external_id == external_id,
        ))
        created = row is None
        if row is None:
            row = OfficialCalendarEventORM(source=source, external_id=external_id)
            self.session.add(row)
        row.calendar_year = event_date.year
        row.category = str(item.get("category") or "Evento")[:80]
        row.title = str(item.get("title") or item.get("event") or "Evento oficial")[:255]
        row.event_date = event_date
        row.time_label = str(item.get("time_label") or item.get("time") or "")[:80] or None
        row.region = str(item.get("region") or "")[:80] or None
        row.source_url = str(item.get("source_url") or item.get("url") or "")[:500]
        row.official = bool(item.get("official", True))
        row.metadata_json = dict(item.get("metadata") or {})
        row.retrieved_at = item.get("retrieved_at") or utcnow()
        row.updated_at = utcnow()
        self.session.flush()
        return row, created

    def list_portfolio_dividends(
        self, owner_email: str, *, portfolio_id: UUID | None = None,
        start: date | None = None, end: date | None = None, limit: int = 500,
    ) -> list[dict]:
        statement = (
            select(CorporateEventORM, PortfolioPositionORM, PortfolioORM)
            .join(AssetORM, AssetORM.id == CorporateEventORM.asset_id)
            .join(PortfolioPositionORM, PortfolioPositionORM.asset_id == AssetORM.id)
            .join(PortfolioORM, PortfolioORM.id == PortfolioPositionORM.portfolio_id)
            .where(PortfolioORM.owner_email == str(owner_email or "").strip().lower())
        )
        if portfolio_id is not None:
            statement = statement.where(PortfolioORM.id == portfolio_id)
        if start is not None:
            statement = statement.where(or_(
                CorporateEventORM.payment_date >= start,
                and_(CorporateEventORM.payment_date.is_(None), CorporateEventORM.ex_date >= start),
            ))
        if end is not None:
            statement = statement.where(or_(
                CorporateEventORM.payment_date <= end,
                and_(CorporateEventORM.payment_date.is_(None), CorporateEventORM.ex_date <= end),
            ))
        rows = self.session.execute(statement.order_by(
            CorporateEventORM.payment_date.asc().nullslast(),
            CorporateEventORM.ex_date.asc().nullslast(), CorporateEventORM.ticker,
        ).limit(max(1, min(2000, int(limit))))).all()
        return [corporate_event_dict(event, quantity=position.quantity, portfolio_name=portfolio.name)
                for event, position, portfolio in rows]

    def list_relevant_facts(self, *, ticker: str | None = None, limit: int = 100) -> list[RelevantFactORM]:
        # JSON membership differs between PostgreSQL and SQLite. Read a bounded
        # newest window and apply the optional ticker consistently in Python.
        bounded = max(1, min(500, int(limit)))
        scan_limit = min(2500, bounded * 20 if ticker else bounded)
        rows = list(self.session.scalars(select(RelevantFactORM).order_by(
            RelevantFactORM.delivered_at.desc(), RelevantFactORM.id,
        ).limit(scan_limit)))
        if ticker:
            clean = str(ticker).strip().upper()
            rows = [row for row in rows if clean in set(row.tickers_json or [])]
        return rows[:bounded]

    def list_calendar(self, *, start: date, end: date, limit: int = 500) -> list[OfficialCalendarEventORM]:
        return list(self.session.scalars(select(OfficialCalendarEventORM).where(
            OfficialCalendarEventORM.event_date >= start,
            OfficialCalendarEventORM.event_date <= end,
        ).order_by(OfficialCalendarEventORM.event_date, OfficialCalendarEventORM.category).limit(
            max(1, min(2000, int(limit))),
        )))

    def save_alb_observation(
        self, *, reference_date: date, preset_version: str, filters: dict,
        tickers: list[str], target_min: int = 5, target_max: int = 20,
    ) -> AlbUniverseObservationORM:
        encoded = json.dumps(filters, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        filters_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        row = self.session.scalar(select(AlbUniverseObservationORM).where(
            AlbUniverseObservationORM.reference_date == reference_date,
            AlbUniverseObservationORM.preset_version == str(preset_version)[:40],
        ))
        if row is None:
            row = AlbUniverseObservationORM(
                reference_date=reference_date, preset_version=str(preset_version)[:40],
                filters_hash=filters_hash, asset_count=0, status="unknown",
            )
            self.session.add(row)
        clean = sorted(set(str(value).strip().upper() for value in tickers if str(value).strip()))
        row.filters_hash = filters_hash
        row.asset_count = len(clean)
        row.target_min = max(0, int(target_min))
        row.target_max = max(row.target_min, int(target_max))
        row.status = "within_range" if row.target_min <= row.asset_count <= row.target_max else "outside_range"
        row.tickers_json = clean
        row.updated_at = utcnow()
        self.session.flush()
        return row

    def latest_alb_observation(self) -> AlbUniverseObservationORM | None:
        return self.session.scalar(select(AlbUniverseObservationORM).order_by(
            AlbUniverseObservationORM.reference_date.desc(),
            AlbUniverseObservationORM.updated_at.desc(),
        ).limit(1))

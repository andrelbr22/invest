from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ...core.repositories.assets import AssetRepository
from ...core.screening.universe import company_size_from_market_cap
from ...infrastructure.db.models import IngestionRunORM
from ..providers.fundamentus import FundamentusStockProvider, FundamentusFiiProvider
from ..providers.tradingview import TradingViewScannerProvider
from .validation import validate_stock, validate_fii, validate_technical


@dataclass
class PipelineSummary:
    pipeline: str
    rows_received: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    warnings: int = 0


class MarketIngestionPipeline:
    def __init__(
        self,
        session: Session,
        stock_provider=None,
        fii_provider=None,
        technical_provider=None,
    ):
        self.session = session
        self.repo = AssetRepository(session)
        self.stock_provider = stock_provider or FundamentusStockProvider()
        self.fii_provider = fii_provider or FundamentusFiiProvider()
        self.technical_provider = technical_provider or TradingViewScannerProvider()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _new_run(self, name: str) -> IngestionRunORM:
        run = IngestionRunORM(pipeline=name, started_at=self._now(), status="running")
        self.session.add(run)
        self.session.flush()
        return run

    def _finish_run(self, run: IngestionRunORM, summary: PipelineSummary, details: dict | None = None):
        run.finished_at = self._now()
        run.status = "success" if summary.rows_rejected == 0 else "partial"
        run.rows_received = summary.rows_received
        run.rows_valid = summary.rows_valid
        run.rows_rejected = summary.rows_rejected
        run.details = {"warnings": summary.warnings, **(details or {})}
        self.session.flush()

    def ingest_stocks(self, *, reference_date: datetime | None = None) -> PipelineSummary:
        run = self._new_run("fundamentus_stocks")
        rows = self.stock_provider.fetch()
        now = self._now()
        ref = reference_date or now
        summary = PipelineSummary("fundamentus_stocks", rows_received=len(rows))
        rejected: list[dict] = []
        for raw in rows:
            result = validate_stock(raw)
            summary.warnings += len(result.warnings)
            if not result.valid:
                summary.rows_rejected += 1
                rejected.append({"ticker": raw.get("ticker"), "errors": result.errors})
                continue
            asset = self.repo.upsert_asset(ticker=raw["ticker"], asset_type="stock")
            self.repo.upsert_fundamentals(
                asset,
                source="fundamentus",
                reference_date=ref,
                retrieved_at=now,
                status="valid",
                quality_score=result.quality_score,
                data=raw,
                raw_payload=raw,
            )
            summary.rows_valid += 1
        self._finish_run(run, summary, {"rejected": rejected[:100]})
        return summary

    def ingest_fiis(self, *, reference_date: datetime | None = None) -> PipelineSummary:
        run = self._new_run("fundamentus_fiis")
        rows = self.fii_provider.fetch()
        now = self._now()
        ref = reference_date or now
        summary = PipelineSummary("fundamentus_fiis", rows_received=len(rows))
        rejected: list[dict] = []
        for raw in rows:
            result = validate_fii(raw)
            summary.warnings += len(result.warnings)
            if not result.valid:
                summary.rows_rejected += 1
                rejected.append({"ticker": raw.get("ticker"), "errors": result.errors})
                continue
            asset = self.repo.upsert_asset(
                ticker=raw["ticker"],
                asset_type="fii",
                segment=raw.get("segment"),
            )
            self.repo.upsert_fundamentals(
                asset,
                source="fundamentus",
                reference_date=ref,
                retrieved_at=now,
                status="valid",
                quality_score=result.quality_score,
                data=raw,
                raw_payload=raw,
            )
            summary.rows_valid += 1
        self._finish_run(run, summary, {"rejected": rejected[:100]})
        return summary

    def ingest_technicals(self, asset_type: str) -> PipelineSummary:
        tv_type = "stock" if asset_type == "stock" else "fund"
        run = self._new_run(f"tradingview_{asset_type}")
        rows = self.technical_provider.fetch(tv_type)
        now = self._now()
        summary = PipelineSummary(f"tradingview_{asset_type}", rows_received=len(rows))
        rejected: list[dict] = []
        for raw in rows:
            result = validate_technical(raw)
            summary.warnings += len(result.warnings)
            if not result.valid:
                summary.rows_rejected += 1
                rejected.append({"ticker": raw.get("ticker"), "errors": result.errors})
                continue
            asset = self.repo.upsert_asset(
                ticker=raw["ticker"],
                asset_type=asset_type,
                name=raw.get("name"),
                exchange=raw.get("exchange"),
                sector=raw.get("sector"),
                industry=raw.get("industry"),
            )
            if raw.get("market_cap") is not None:
                asset.metadata_json = {**(asset.metadata_json or {}), "last_market_cap": raw.get("market_cap")}
                asset.market_cap_category = company_size_from_market_cap(raw.get("market_cap"))
            self.repo.upsert_technical(
                asset,
                source="tradingview",
                timeframe="1D",
                as_of=now,
                retrieved_at=now,
                status="valid",
                quality_score=result.quality_score,
                data=raw,
                raw_payload=raw,
            )
            summary.rows_valid += 1
        self._finish_run(run, summary, {"rejected": rejected[:100]})
        return summary

    def run_full(self) -> dict[str, PipelineSummary]:
        return {
            "stocks": self.ingest_stocks(),
            "stock_technicals": self.ingest_technicals("stock"),
            "fiis": self.ingest_fiis(),
            "fii_technicals": self.ingest_technicals("fii"),
        }

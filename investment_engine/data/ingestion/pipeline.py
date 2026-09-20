from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ...core.repositories.assets import AssetRepository
from ...core.repositories.economic_series import SharedSnapshotRepository
from ...core.screening.universe import company_size_from_market_cap
from ...core.instruments import is_supported_ticker, ticker_exclusion_reason
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

    def _current_selic_carry_rate(self) -> tuple[float | None, str | None]:
        snapshot = SharedSnapshotRepository(self.session).get("market:selic-current")
        payload = snapshot.payload_json if snapshot is not None and isinstance(snapshot.payload_json, dict) else {}
        selic = payload.get("selic") if isinstance(payload.get("selic"), dict) else {}
        try:
            value = float(selic.get("current"))
        except (TypeError, ValueError):
            return None, None
        return value, "Banco Central do Brasil • meta Selic vigente"

    def _current_di_curve(self) -> tuple[list[dict], str | None]:
        snapshot = SharedSnapshotRepository(self.session).get("market:rates-calendar")
        payload = snapshot.payload_json if snapshot is not None and isinstance(snapshot.payload_json, dict) else {}
        curve = payload.get("curve") if isinstance(payload.get("curve"), dict) else {}
        points = curve.get("points") if isinstance(curve.get("points"), list) else []
        return points, str(curve.get("source") or "").strip() or None

    @staticmethod
    def _carry_rate_for_days(points: list[dict], calendar_days) -> float | None:
        try:
            target = float(calendar_days) * 252.0 / 365.0
        except (TypeError, ValueError):
            return None
        clean = []
        for point in points or []:
            if not isinstance(point, dict):
                continue
            try:
                days = float(point.get("business_days"))
                rate = float(point.get("di_rate") if point.get("di_rate") is not None else point.get("nominal_rate"))
            except (TypeError, ValueError):
                continue
            if days > 0:
                clean.append((days, rate))
        clean.sort()
        if not clean:
            return None
        if target <= clean[0][0]:
            return clean[0][1]
        if target >= clean[-1][0]:
            return clean[-1][1]
        for (left_days, left_rate), (right_days, right_rate) in zip(clean, clean[1:]):
            if left_days <= target <= right_days:
                weight = (target - left_days) / (right_days - left_days)
                return left_rate + (right_rate - left_rate) * weight
        return None

    @staticmethod
    def _valuation_metadata(raw: dict, asset_type: str, as_of: datetime) -> dict:
        keys_by_type = {
            "etf": ("nav_discount_premium_pct", "expense_ratio_pct", "fundamental_currency_code"),
            "bdr": ("price_book_fq", "book_value_per_share", "fundamental_currency_code"),
            "future": (
                "root_symbol", "front_contract", "front_contract_price", "expiration_date", "days_to_expiry",
                "front_open_interest", "underlying_ticker", "underlying_spot_price",
                "underlying_income_yield_pct", "carry_rate_pct", "carry_rate_source",
            ),
        }
        return {
            **{key: raw.get(key) for key in keys_by_type.get(asset_type, ()) if raw.get(key) is not None},
            "valuation_inputs_as_of": as_of.isoformat(),
            "valuation_source": raw.get("valuation_source") or "TradingView scanner",
        }

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
        filtered: list[dict] = []
        for raw in rows:
            if not is_supported_ticker(raw.get("ticker"), "stock"):
                filtered.append({"ticker": raw.get("ticker"), "reason": ticker_exclusion_reason(raw.get("ticker"), "stock")})
                continue
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
        self._finish_run(run, summary, {"rejected": rejected[:100], "filtered_out": filtered[:100], "filtered_count": len(filtered)})
        return summary

    def ingest_fiis(self, *, reference_date: datetime | None = None) -> PipelineSummary:
        run = self._new_run("fundamentus_fiis")
        rows = self.fii_provider.fetch()
        now = self._now()
        ref = reference_date or now
        summary = PipelineSummary("fundamentus_fiis", rows_received=len(rows))
        rejected: list[dict] = []
        filtered: list[dict] = []
        for raw in rows:
            if not is_supported_ticker(raw.get("ticker"), "fii"):
                filtered.append({"ticker": raw.get("ticker"), "reason": ticker_exclusion_reason(raw.get("ticker"), "fii")})
                continue
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
        self._finish_run(run, summary, {"rejected": rejected[:100], "filtered_out": filtered[:100], "filtered_count": len(filtered)})
        return summary

    def ingest_technicals(self, asset_type: str) -> PipelineSummary:
        tv_type = "stock" if asset_type == "stock" else "fund"
        run = self._new_run(f"tradingview_{asset_type}")
        rows = self.technical_provider.fetch(tv_type)
        now = self._now()
        summary = PipelineSummary(f"tradingview_{asset_type}", rows_received=len(rows))
        rejected: list[dict] = []
        filtered: list[dict] = []
        for raw in rows:
            if not is_supported_ticker(raw.get("ticker"), asset_type):
                filtered.append({"ticker": raw.get("ticker"), "reason": ticker_exclusion_reason(raw.get("ticker"), asset_type)})
                continue
            existing = self.repo.get_by_ticker(str(raw.get("ticker") or "").upper())
            # Fundamentus is the authority for the stock and FII catalogs.
            # TradingView supplies technicals only for those existing assets;
            # this prevents broad provider scans from filling the database with
            # operational variants or unrelated instruments.
            if asset_type in {"stock", "fii"} and (existing is None or existing.asset_type != asset_type):
                continue
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
        self._finish_run(run, summary, {"rejected": rejected[:100], "filtered_out": filtered[:100], "filtered_count": len(filtered)})
        return summary

    def ingest_other_b3(self) -> PipelineSummary:
        """Import technical catalogs that do not use company/FII fundamentals."""
        run = self._new_run("tradingview_other_b3")
        now = self._now()
        summary = PipelineSummary("tradingview_other_b3")
        rejected: list[dict] = []
        filtered: list[dict] = []
        source_errors: list[dict] = []
        groups = (
            ("etf", "fund", ["etf"], "ETF"),
            ("bdr", "dr", None, "BDR"),
            ("future", "futures", None, "Futuro / derivativo"),
        )
        for saved_type, provider_type, type_specs, segment_label in groups:
            try:
                rows = self.technical_provider.fetch(provider_type, type_specs=type_specs)
            except Exception as exc:
                summary.warnings += 1
                source_errors.append({"asset_type": saved_type, "error": str(exc)})
                continue
            if saved_type == "future":
                references = self.repo.latest_market_references_by_ticker(
                    [row.get("underlying_ticker") for row in rows]
                )
                curve_points, curve_source = self._current_di_curve()
                selic_rate, selic_source = self._current_selic_carry_rate()
                for row in rows:
                    reference = references.get(str(row.get("underlying_ticker") or "").upper()) or {}
                    row["underlying_spot_price"] = reference.get("price")
                    row["underlying_income_yield_pct"] = reference.get("dividend_yield_pct")
                    curve_rate = self._carry_rate_for_days(curve_points, row.get("days_to_expiry"))
                    row["carry_rate_pct"] = curve_rate if curve_rate is not None else selic_rate
                    row["carry_rate_source"] = curve_source if curve_rate is not None else selic_source
            for row in rows:
                row["valuation_inputs_as_of"] = now.isoformat()
            summary.rows_received += len(rows)
            for raw in rows:
                if not is_supported_ticker(raw.get("ticker"), saved_type):
                    filtered.append({"ticker": raw.get("ticker"), "asset_type": saved_type, "reason": ticker_exclusion_reason(raw.get("ticker"), saved_type)})
                    continue
                result = validate_technical(raw)
                summary.warnings += len(result.warnings)
                if not result.valid:
                    summary.rows_rejected += 1
                    rejected.append({"ticker": raw.get("ticker"), "asset_type": saved_type, "errors": result.errors})
                    continue
                ticker = str(raw.get("ticker") or "").strip().upper()
                existing = self.repo.get_any_by_ticker(ticker)
                if existing is not None and existing.asset_type in {"stock", "fii"}:
                    # Repair ETFs that an older broad "fund" scan may have
                    # labeled as FII, but never reclassify a genuine asset that
                    # already has fundamental history.
                    unambiguous_code_repair = (
                        not is_supported_ticker(ticker, existing.asset_type)
                        and is_supported_ticker(ticker, saved_type)
                    )
                    can_repair = (
                        unambiguous_code_repair
                        or self.repo.latest_fundamentals(existing.id) is None
                    )
                    if not can_repair:
                        continue
                    existing.asset_type = saved_type
                asset = self.repo.upsert_asset(
                    ticker=ticker,
                    asset_type=saved_type,
                    is_active=True,
                    name=raw.get("name"), exchange=raw.get("exchange"),
                    sector=raw.get("sector"), industry=raw.get("industry"), segment=segment_label,
                    metadata_json={
                        "b3_category": saved_type,
                        "instrument_type": raw.get("instrument_type") or provider_type,
                        "type_specs": raw.get("type_specs") or [],
                        **self._valuation_metadata(raw, saved_type, now),
                    },
                )
                self.repo.upsert_technical(
                    asset, source="tradingview", timeframe="1D", as_of=now, retrieved_at=now,
                    status="valid", quality_score=result.quality_score, data=raw, raw_payload=raw,
                )
                summary.rows_valid += 1
        self._finish_run(run, summary, {
            "rejected": rejected[:100], "source_errors": source_errors,
            "filtered_out": filtered[:100], "filtered_count": len(filtered),
        })
        return summary

    def run_full(self) -> dict[str, PipelineSummary]:
        self.repo.deactivate_unsupported_assets()
        return {
            "stocks": self.ingest_stocks(),
            "stock_technicals": self.ingest_technicals("stock"),
            "fiis": self.ingest_fiis(),
            "fii_technicals": self.ingest_technicals("fii"),
            "other_b3": self.ingest_other_b3(),
        }

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from sqlalchemy import select, and_, or_, false, func, desc, case
from sqlalchemy.orm import Session, aliased
from ...infrastructure.db.models import (
    AssetCurrentMetricsORM, AssetORM, FundamentalSnapshotORM, TechnicalSnapshotORM,
    PriceBarORM, ValuationSnapshotORM, ScoreSnapshotORM,
)
from ...core.instruments import B3_CATALOG_TYPES, is_supported_ticker, require_supported_ticker, ticker_exclusion_reason
from .current_metrics import AssetCurrentMetricsRepository


_CURRENT_FUNDAMENTAL_FIELDS = (
    "pe", "pbv", "dividend_yield_pct", "ev_ebitda", "ebit_margin_pct",
    "net_margin_pct", "current_ratio", "roe_pct", "roic_pct",
    "gross_debt_to_equity", "net_debt_to_ebitda", "revenue_cagr_5y_pct",
    "earnings_cagr_5y_pct", "ffo_yield_pct", "cap_rate_pct", "vacancy_pct",
    "financial_vacancy_pct", "ltv_pct", "wale_years",
)
_CURRENT_TECHNICAL_FIELDS = (
    "score_tv", "signal_tv", "market_cap", "daily_liquidity", "sma20",
    "sma50", "sma200", "sma20_1w", "sma50_1w", "sma20_1m", "sma50_1m",
    "rsi14", "macd", "atr14", "volatility_annual_pct",
    "max_drawdown_1y_pct", "return_1m_pct", "return_3m_pct", "return_12m_pct",
)
_CURRENT_SCORE_FIELDS = (
    "quality_score", "value_score", "growth_score", "technical_score",
    "risk_score", "liquidity_score", "alb_score", "coverage_pct",
    "data_quality_score",
)

# The ETF/BDR/future navigation table renders only these promoted fields.  Keep
# this separate from ``_CURRENT_TECHNICAL_FIELDS``: advanced screening and the
# worker still need the complete current snapshot, including its audited raw
# inputs, while a normal tab change must not transfer those large JSON mirrors.
_NAVIGATION_TECHNICAL_FIELDS = (
    "daily_liquidity", "signal_tv", "rsi14", "sma20", "sma50", "sma200",
)


def _decimal_or_none(value):
    if value is None:
        return None
    return Decimal(str(value))


def _current_component(row: AssetCurrentMetricsORM, component: str):
    """Expose a current-metrics component through the historical snapshot shape."""
    if component == "fundamental":
        if row.fundamental_snapshot_id is None:
            return None
        values = dict(row.fundamental_json or {})
        for field in (
            "price", "pe", "pbv", "dividend_yield_pct", "ev_ebitda",
            "ebit_margin_pct", "net_margin_pct", "current_ratio", "roe_pct", "roic_pct",
            "gross_debt_to_equity", "net_debt_to_ebitda", "revenue_cagr_5y_pct",
            "earnings_cagr_5y_pct", "ffo_yield_pct", "cap_rate_pct", "vacancy_pct",
            "financial_vacancy_pct", "ltv_pct", "wale_years", "daily_liquidity",
        ):
            if field == "price":
                values[field] = (row.fundamental_json or {}).get("price")
            elif field == "daily_liquidity":
                values[field] = row.fundamental_daily_liquidity
            else:
                values[field] = getattr(row, field)
        values.update({
            "id": row.fundamental_snapshot_id,
            "asset_id": row.asset_id,
            "reference_date": row.fundamental_as_of,
            "retrieved_at": row.fundamental_retrieved_at,
            "source": ((row.source_refs_json or {}).get("fundamental") or {}).get("source"),
            "raw_payload": dict((row.fundamental_json or {}).get("raw_payload") or {}),
        })
        return SimpleNamespace(**values)
    if component == "technical":
        if row.technical_snapshot_id is None and row.price_bar_id is None:
            return None
        values = dict(row.technical_json or {})
        for field in (
            "score_tv", "signal_tv", "market_cap", "daily_liquidity", "sma20", "sma50",
            "sma200", "sma20_1w", "sma50_1w", "sma20_1m", "sma50_1m", "rsi14",
            "macd", "atr14", "volatility_annual_pct", "max_drawdown_1y_pct",
            "return_1m_pct", "return_3m_pct", "return_12m_pct",
        ):
            values[field] = getattr(row, field)
        if row.technical_snapshot_id is None and row.price is not None:
            values["close"] = row.price
        values.update({
            "id": row.technical_snapshot_id or row.price_bar_id,
            "asset_id": row.asset_id,
            "timeframe": "1D",
            "as_of": row.technical_as_of or row.price_as_of,
            "retrieved_at": row.technical_retrieved_at or row.price_retrieved_at,
            "source": ((row.source_refs_json or {}).get("technical") or {}).get("source")
            or ((row.source_refs_json or {}).get("price") or {}).get("source"),
            "raw_payload": dict((row.technical_json or {}).get("raw_payload") or {}),
        })
        return SimpleNamespace(**values)
    if component == "score":
        if row.score_snapshot_id is None:
            return None
        values = dict(row.score_json or {})
        for field in (
            "quality_score", "value_score", "growth_score", "technical_score", "risk_score",
            "liquidity_score", "alb_score", "coverage_pct", "data_quality_score",
        ):
            values[field] = getattr(row, field)
        values.update({
            "id": row.score_snapshot_id,
            "asset_id": row.asset_id,
            "as_of": row.score_as_of,
            "calculated_at": row.score_calculated_at,
            "model_version": ((row.source_refs_json or {}).get("score") or {}).get("source"),
            "details_json": dict((row.score_json or {}).get("details") or {}),
        })
        return SimpleNamespace(**values)
    raise ValueError("invalid_current_metrics_component")


class AssetRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_ticker(self, ticker: str) -> AssetORM | None:
        asset = self.get_any_by_ticker(ticker)
        if asset is not None and not is_supported_ticker(asset.ticker, asset.asset_type):
            return None
        return asset

    def get_any_by_ticker(self, ticker: str) -> AssetORM | None:
        """Internal lookup that can also see legacy, currently unsupported rows."""
        return self.session.scalar(select(AssetORM).where(AssetORM.ticker == ticker.upper()))

    def list_assets(self, asset_type: str | None = None, limit: int = 100, offset: int = 0) -> list[AssetORM]:
        supported_types = {asset_type} if asset_type else None
        stmt = select(AssetORM).where(AssetORM.is_active.is_(True), self._supported_catalog_clause(supported_types)).order_by(AssetORM.ticker).limit(limit).offset(offset)
        if asset_type:
            stmt = stmt.where(AssetORM.asset_type == asset_type)
        return list(self.session.scalars(stmt))

    def search_assets(self, query: str, limit: int = 12) -> list[AssetORM]:
        clean = str(query or "").strip().upper()
        if not clean:
            return []
        prefix = f"{clean}%"
        contains = f"%{clean}%"
        stmt = (
            select(AssetORM)
            .where(
                AssetORM.is_active.is_(True),
                self._supported_catalog_clause(),
                or_(AssetORM.ticker.ilike(prefix), AssetORM.name.ilike(contains)),
            )
            .order_by(
                (AssetORM.ticker == clean).desc(),
                AssetORM.ticker.startswith(clean).desc(),
                AssetORM.ticker,
            )
            .limit(max(1, min(int(limit), 25)))
        )
        return list(self.session.scalars(stmt))

    def upsert_asset(self, *, ticker: str, asset_type: str, **fields) -> AssetORM:
        ticker = require_supported_ticker(ticker, asset_type)
        asset = self.get_any_by_ticker(ticker)
        if asset is None:
            asset = AssetORM(ticker=ticker, asset_type=asset_type)
            self.session.add(asset)
        for key in ("name", "exchange", "currency", "sector", "industry", "segment", "market_cap_category", "is_active"):
            if key in fields and fields[key] is not None:
                setattr(asset, key, fields[key])
        if fields.get("metadata_json"):
            asset.metadata_json = {**(asset.metadata_json or {}), **fields["metadata_json"]}
        asset.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        AssetCurrentMetricsRepository(self.session).ensure(asset.id)
        return asset

    @staticmethod
    def _ticker_patterns(root_lengths: tuple[int, ...], suffixes: tuple[str, ...]):
        """Build compact, portable suffix clauses for the supported B3 catalog.

        The previous implementation expanded stocks into 21 ``LIKE``
        predicates.  PostgreSQL then repeatedly evaluated that disjunction on
        every screener request, even though the rule only depends on the
        ticker length and suffix.  Grouping equal-size suffixes preserves the
        exact accepted lengths while producing only one predicate per suffix
        size (two for stocks and one for FIIs/ETFs/BDRs).
        """
        grouped: dict[int, list[str]] = {}
        for suffix in suffixes:
            grouped.setdefault(len(suffix), []).append(suffix)
        clauses = []
        for suffix_length, values in grouped.items():
            accepted_lengths = tuple(sorted({root + suffix_length for root in root_lengths}))
            clauses.append(and_(
                func.length(AssetORM.ticker).in_(accepted_lengths),
                func.substr(
                    AssetORM.ticker,
                    func.length(AssetORM.ticker) - suffix_length + 1,
                    suffix_length,
                ).in_(tuple(values)),
            ))
        return clauses

    @classmethod
    def _supported_catalog_clause(cls, asset_types: set[str] | None = None):
        roots = (3, 4, 5)
        clauses = {
            "stock": and_(AssetORM.asset_type == "stock", or_(*cls._ticker_patterns(roots, ("3", "4", "5", "6", "7", "8", "11")))),
            "fii": and_(AssetORM.asset_type == "fii", or_(*cls._ticker_patterns(roots, ("11",)))),
            "etf": and_(AssetORM.asset_type == "etf", or_(*cls._ticker_patterns(roots, ("11",)))),
            "bdr": and_(AssetORM.asset_type == "bdr", or_(*cls._ticker_patterns(roots, tuple(f"3{i}" for i in range(1, 10))))),
            "future": and_(AssetORM.asset_type == "future", AssetORM.ticker.like("%1!")),
        }
        requested = set(asset_types) if asset_types is not None else set(B3_CATALOG_TYPES)
        selected = [clauses[item] for item in sorted(requested & set(B3_CATALOG_TYPES))]
        if asset_types is None or requested - set(B3_CATALOG_TYPES):
            selected.append(AssetORM.asset_type.notin_(B3_CATALOG_TYPES))
        return or_(*selected) if selected else false()

    def deactivate_unsupported_assets(self) -> list[dict]:
        """Stop legacy noise from receiving snapshots without deleting history."""
        rows = list(self.session.scalars(select(AssetORM).where(
            AssetORM.asset_type.in_(B3_CATALOG_TYPES), AssetORM.is_active.is_(True),
        )))
        deactivated = []
        for asset in rows:
            reason = ticker_exclusion_reason(asset.ticker, asset.asset_type)
            if reason is None:
                continue
            asset.is_active = False
            asset.metadata_json = {**(asset.metadata_json or {}), "catalog_exclusion_reason": reason}
            deactivated.append({"ticker": asset.ticker, "asset_type": asset.asset_type, "reason": reason})
        if deactivated:
            self.session.flush()
        return deactivated

    def upsert_fundamentals(
        self,
        asset: AssetORM,
        *,
        source: str,
        reference_date: datetime,
        retrieved_at: datetime,
        status: str,
        quality_score: float | None,
        data: dict,
        raw_payload: dict,
    ) -> FundamentalSnapshotORM:
        stmt = select(FundamentalSnapshotORM).where(
            FundamentalSnapshotORM.asset_id == asset.id,
            FundamentalSnapshotORM.reference_date == reference_date,
            FundamentalSnapshotORM.source == source,
        )
        row = self.session.scalar(stmt)
        if row is None:
            row = FundamentalSnapshotORM(
                asset_id=asset.id,
                reference_date=reference_date,
                source=source,
            )
            self.session.add(row)
        row.retrieved_at = retrieved_at
        row.status = status
        row.quality_score = _decimal_or_none(quality_score)
        numeric_fields = {
            "price", "pe", "pbv", "dividend_yield_pct", "ev_ebitda", "ebit_margin_pct", "net_margin_pct",
            "current_ratio", "roe_pct", "roic_pct", "gross_debt_to_equity", "net_debt_to_ebitda",
            "revenue_cagr_5y_pct", "earnings_cagr_5y_pct", "ffo_yield_pct", "cap_rate_pct", "vacancy_pct",
            "financial_vacancy_pct", "ltv_pct", "wale_years", "daily_liquidity",
        }
        for key in numeric_fields:
            if key in data:
                setattr(row, key, _decimal_or_none(data.get(key)))
        row.raw_payload = raw_payload or {}
        self.session.flush()
        AssetCurrentMetricsRepository(self.session).sync_fundamental(row)
        self.session.flush()
        return row

    def upsert_technical(
        self,
        asset: AssetORM,
        *,
        source: str,
        timeframe: str,
        as_of: datetime,
        retrieved_at: datetime,
        status: str,
        quality_score: float | None = None,
        data: dict = None,
        raw_payload: dict = None,
    ) -> TechnicalSnapshotORM:
        stmt = select(TechnicalSnapshotORM).where(
            TechnicalSnapshotORM.asset_id == asset.id,
            TechnicalSnapshotORM.timeframe == timeframe,
            TechnicalSnapshotORM.as_of == as_of,
            TechnicalSnapshotORM.source == source,
        )
        row = self.session.scalar(stmt)
        if row is None:
            row = TechnicalSnapshotORM(asset_id=asset.id, timeframe=timeframe, as_of=as_of, source=source)
            self.session.add(row)
        row.retrieved_at = retrieved_at
        row.status = status
        row.quality_score = _decimal_or_none(quality_score)
        data = data or {}
        for key in (
            "score_tv", "market_cap", "daily_liquidity", "sma20", "sma50", "sma200", "sma20_1w", "sma50_1w",
            "sma20_1m", "sma50_1m", "high", "low", "close", "rsi14", "bb_lower", "bb_upper", "bb_middle",
            "macd", "atr14", "volatility_annual_pct", "max_drawdown_1y_pct", "return_1m_pct", "return_3m_pct", "return_12m_pct",
        ):
            if key in data:
                setattr(row, key, _decimal_or_none(data.get(key)))
        row.signal_tv = data.get("signal_tv")
        row.raw_payload = raw_payload or {}
        self.session.flush()
        AssetCurrentMetricsRepository(self.session).sync_technical(row)
        self.session.flush()
        return row

    def latest_fundamentals(self, asset_id) -> FundamentalSnapshotORM | None:
        stmt = (
            select(FundamentalSnapshotORM)
            .where(FundamentalSnapshotORM.asset_id == asset_id)
            .order_by(
                FundamentalSnapshotORM.reference_date.desc(),
                FundamentalSnapshotORM.retrieved_at.desc(),
                FundamentalSnapshotORM.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalar(stmt)


    def fundamental_history_until(self, asset_id, *, end=None):
        stmt = select(FundamentalSnapshotORM).where(FundamentalSnapshotORM.asset_id == asset_id)
        if end is not None:
            stmt = stmt.where(FundamentalSnapshotORM.reference_date <= end)
        stmt = stmt.order_by(FundamentalSnapshotORM.reference_date, FundamentalSnapshotORM.retrieved_at)
        return list(self.session.scalars(stmt))

    def latest_technical(self, asset_id, timeframe: str = "1D", source: str | None = None) -> TechnicalSnapshotORM | None:
        stmt = select(TechnicalSnapshotORM).where(TechnicalSnapshotORM.asset_id == asset_id, TechnicalSnapshotORM.timeframe == timeframe)
        if source is not None:
            stmt = stmt.where(TechnicalSnapshotORM.source == source)
        stmt = stmt.order_by(
            TechnicalSnapshotORM.as_of.desc(),
            TechnicalSnapshotORM.retrieved_at.desc(),
            TechnicalSnapshotORM.id.desc(),
        ).limit(1)
        return self.session.scalar(stmt)


    def upsert_price_bar(self, asset, *, timeframe, timestamp, source, data, retrieved_at=None, status="valid"):
        stmt=select(PriceBarORM).where(PriceBarORM.asset_id==asset.id,PriceBarORM.timeframe==timeframe,PriceBarORM.timestamp==timestamp,PriceBarORM.source==source)
        row=self.session.scalar(stmt)
        if row is None:
            row=PriceBarORM(asset_id=asset.id,timeframe=timeframe,timestamp=timestamp,source=source); self.session.add(row)
        for k in ("open","high","low","close","volume","adjusted_close"):
            if k in data:setattr(row,k,_decimal_or_none(data.get(k)))
        if retrieved_at is not None: row.retrieved_at=retrieved_at
        row.status=status
        self.session.flush()
        AssetCurrentMetricsRepository(self.session).sync_price(row)
        self.session.flush()
        return row

    def bulk_upsert_price_bars(self, asset, rows, *, retrieved_at=None, status="valid"):
        if not rows:
            return 0
        timeframe = rows[0].get("timeframe", "1D")
        source = rows[0].get("source", "yahoo")
        timestamps = [r["timestamp"] for r in rows]
        start, end = min(timestamps), max(timestamps)
        existing_rows = list(self.session.scalars(
            select(PriceBarORM).where(
                PriceBarORM.asset_id == asset.id, PriceBarORM.timeframe == timeframe, PriceBarORM.source == source,
                PriceBarORM.timestamp >= start, PriceBarORM.timestamp <= end,
            )
        ))
        existing = {r.timestamp: r for r in existing_rows}
        for data in rows:
            ts = data["timestamp"]
            row = existing.get(ts)
            if row is None:
                row = PriceBarORM(asset_id=asset.id, timeframe=data.get("timeframe", timeframe), timestamp=ts, source=data.get("source", source))
                self.session.add(row); existing[ts] = row
            for k in ("open", "high", "low", "close", "volume", "adjusted_close"):
                if k in data:
                    setattr(row, k, _decimal_or_none(data.get(k)))
            if retrieved_at is not None:
                row.retrieved_at = retrieved_at
            row.status = status
        self.session.flush()
        latest = max(existing.values(), key=lambda item: (item.timestamp, item.retrieved_at, str(item.id)))
        AssetCurrentMetricsRepository(self.session).sync_price(latest)
        self.session.flush()
        return len(rows)

    def price_history(self, asset_id, timeframe="1D", limit=600):
        stmt=select(PriceBarORM).where(PriceBarORM.asset_id==asset_id,PriceBarORM.timeframe==timeframe).order_by(PriceBarORM.timestamp.desc()).limit(limit)
        return list(reversed(list(self.session.scalars(stmt))))

    def price_history_range(self, asset_id, *, start=None, end=None, timeframe="1D", source=None):
        stmt = select(PriceBarORM).where(PriceBarORM.asset_id == asset_id, PriceBarORM.timeframe == timeframe)
        if source is not None:
            stmt = stmt.where(PriceBarORM.source == source)
        if start is not None:
            stmt = stmt.where(PriceBarORM.timestamp >= start)
        if end is not None:
            stmt = stmt.where(PriceBarORM.timestamp <= end)
        stmt = stmt.order_by(PriceBarORM.timestamp)
        return list(self.session.scalars(stmt))

    def latest_price_bar(self, asset_id, timeframe="1D"):
        return self.session.scalar(
            select(PriceBarORM).where(PriceBarORM.asset_id == asset_id, PriceBarORM.timeframe == timeframe)
            .order_by(
                PriceBarORM.timestamp.desc(), PriceBarORM.retrieved_at.desc(), PriceBarORM.id.desc(),
            ).limit(1)
        )

    def upsert_valuation(self, asset, *, method, as_of, method_version="1.0", value=None, upside_pct=None, status="valid", inputs=None):
        stmt=select(ValuationSnapshotORM).where(ValuationSnapshotORM.asset_id==asset.id,ValuationSnapshotORM.method==method,ValuationSnapshotORM.as_of==as_of,ValuationSnapshotORM.method_version==method_version)
        row=self.session.scalar(stmt)
        if row is None: row=ValuationSnapshotORM(asset_id=asset.id,method=method,as_of=as_of,method_version=method_version); self.session.add(row)
        row.value=_decimal_or_none(value); row.upside_pct=_decimal_or_none(upside_pct); row.status=status; row.inputs_json=inputs or {}; self.session.flush(); return row

    def upsert_scores(self, asset, *, as_of, model_version="1.0", scores=None, coverage_pct=None, data_quality_score=None, details=None):
        stmt=select(ScoreSnapshotORM).where(ScoreSnapshotORM.asset_id==asset.id,ScoreSnapshotORM.as_of==as_of,ScoreSnapshotORM.model_version==model_version)
        row=self.session.scalar(stmt)
        if row is None: row=ScoreSnapshotORM(asset_id=asset.id,as_of=as_of,model_version=model_version); self.session.add(row)
        scores=scores or {}
        for k in ("quality_score","value_score","growth_score","technical_score","risk_score","liquidity_score","alb_score"):
            setattr(row,k,_decimal_or_none(scores.get(k)))
        row.coverage_pct=_decimal_or_none(coverage_pct); row.data_quality_score=_decimal_or_none(data_quality_score); row.details_json=details or {}
        self.session.flush()
        AssetCurrentMetricsRepository(self.session).sync_score(row)
        self.session.flush()
        return row

    def latest_scores(self, asset_id):
        return self.session.scalar(select(ScoreSnapshotORM).where(ScoreSnapshotORM.asset_id==asset_id).order_by(ScoreSnapshotORM.as_of.desc(), ScoreSnapshotORM.calculated_at.desc(), ScoreSnapshotORM.id.desc()).limit(1))

    def _latest_rows_by_asset(self, model, asset_ids, *, filters=(), order_by=()):
        """Return one latest ORM row per asset without issuing an N+1 query."""
        ids = list(dict.fromkeys(asset_ids or []))
        if not ids:
            return {}
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            # DISTINCT ON can stop at the first indexed row for each asset.
            # The previous window function had to rank every historical row
            # in the requested assets and repeatedly exceeded the production
            # statement timeout while the current view was rebuilt.
            latest = (
                select(model.id.label("row_id"))
                .where(model.asset_id.in_(ids), *filters)
                .distinct(model.asset_id)
                .order_by(model.asset_id, *order_by)
                .subquery()
            )
            statement = select(model).join(latest, latest.c.row_id == model.id)
        else:
            # SQLite is used by the deterministic repository tests and does
            # not implement PostgreSQL's DISTINCT ON extension.
            ranked = (
                select(
                    model.id.label("row_id"),
                    func.row_number().over(
                        partition_by=model.asset_id,
                        order_by=order_by,
                    ).label("row_rank"),
                )
                .where(model.asset_id.in_(ids), *filters)
                .subquery()
            )
            statement = (
                select(model)
                .join(ranked, ranked.c.row_id == model.id)
                .where(ranked.c.row_rank == 1)
            )
        rows = self.session.scalars(statement)
        return {row.asset_id: row for row in rows}

    def latest_current_sources_batch(self, asset_ids, *, timeframe: str = "1D") -> dict:
        """Load the four historical sources needed by a materializer batch."""
        ids = list(dict.fromkeys(asset_ids or []))
        if not ids:
            return {}
        fundamentals = self._latest_rows_by_asset(
            FundamentalSnapshotORM,
            ids,
            order_by=(
                FundamentalSnapshotORM.reference_date.desc(),
                FundamentalSnapshotORM.retrieved_at.desc(),
                FundamentalSnapshotORM.id.desc(),
            ),
        )
        technicals = self._latest_rows_by_asset(
            TechnicalSnapshotORM,
            ids,
            filters=(TechnicalSnapshotORM.timeframe == timeframe,),
            order_by=(
                TechnicalSnapshotORM.as_of.desc(),
                TechnicalSnapshotORM.retrieved_at.desc(),
                TechnicalSnapshotORM.id.desc(),
            ),
        )
        scores = self._latest_rows_by_asset(
            ScoreSnapshotORM,
            ids,
            order_by=(
                ScoreSnapshotORM.as_of.desc(),
                ScoreSnapshotORM.calculated_at.desc(),
                ScoreSnapshotORM.id.desc(),
            ),
        )
        prices = self._latest_rows_by_asset(
            PriceBarORM,
            ids,
            filters=(PriceBarORM.timeframe == timeframe,),
            order_by=(
                PriceBarORM.timestamp.desc(),
                PriceBarORM.retrieved_at.desc(),
                PriceBarORM.id.desc(),
            ),
        )
        return {
            asset_id: {
                "fundamental": fundamentals.get(asset_id),
                "technical": technicals.get(asset_id),
                "score": scores.get(asset_id),
                "price": prices.get(asset_id),
            }
            for asset_id in ids
        }

    def _latest_fundamental_alias(self):
        latest_id = (
            select(FundamentalSnapshotORM.id)
            .where(FundamentalSnapshotORM.asset_id == AssetORM.id)
            .order_by(
                FundamentalSnapshotORM.reference_date.desc(),
                FundamentalSnapshotORM.retrieved_at.desc(),
                FundamentalSnapshotORM.id.desc(),
            )
            .limit(1)
            .correlate(AssetORM)
            .scalar_subquery()
        )
        return aliased(FundamentalSnapshotORM), latest_id

    def _latest_technical_alias(self, timeframe="1D"):
        latest_id = (
            select(TechnicalSnapshotORM.id)
            .where(
                TechnicalSnapshotORM.asset_id == AssetORM.id,
                TechnicalSnapshotORM.timeframe == timeframe,
            )
            .order_by(
                TechnicalSnapshotORM.as_of.desc(),
                TechnicalSnapshotORM.retrieved_at.desc(),
                TechnicalSnapshotORM.id.desc(),
            )
            .limit(1)
            .correlate(AssetORM)
            .scalar_subquery()
        )
        return aliased(TechnicalSnapshotORM), latest_id

    def _latest_score_alias(self):
        latest_id = (
            select(ScoreSnapshotORM.id)
            .where(ScoreSnapshotORM.asset_id == AssetORM.id)
            .order_by(
                ScoreSnapshotORM.as_of.desc(),
                ScoreSnapshotORM.calculated_at.desc(),
                ScoreSnapshotORM.id.desc(),
            )
            .limit(1)
            .correlate(AssetORM)
            .scalar_subquery()
        )
        return aliased(ScoreSnapshotORM), latest_id

    @staticmethod
    def _apply_min(stmt, col, threshold):
        if threshold is not None:
            stmt = stmt.where(col.is_not(None), col >= threshold)
        return stmt

    @staticmethod
    def _apply_max(stmt, col, threshold):
        if threshold is not None:
            stmt = stmt.where(col.is_not(None), col <= threshold)
        return stmt

    def _current_coverage_complete(self, asset_types, *, component: str) -> bool:
        accepted = set(asset_types or ())
        if not accepted:
            return True
        if component not in {"fundamental", "technical"}:
            raise ValueError("invalid_current_metrics_component")
        # Coverage means that every active catalog asset has been visited by
        # the resumable materializer.  An asset is allowed to have no source
        # snapshot: the historical queries also return/skip that asset with a
        # null component.  Requiring a non-null fundamental or technical id
        # here would keep the fast path disabled forever whenever the catalog
        # legitimately contains one asset without data.
        current_row_exists = (
            select(AssetCurrentMetricsORM.asset_id)
            .where(AssetCurrentMetricsORM.asset_id == AssetORM.id)
            .exists()
        )
        missing_asset_id = self.session.scalar(
            select(AssetORM.id)
            .where(
                AssetORM.asset_type.in_(accepted),
                AssetORM.is_active.is_(True),
                self._supported_catalog_clause(accepted),
                ~current_row_exists,
            )
            .limit(1)
        )
        return missing_asset_id is None

    @staticmethod
    def _current_universe_tuple(asset, metrics):
        return (
            asset,
            _current_component(metrics, "fundamental"),
            _current_component(metrics, "technical"),
            _current_component(metrics, "score"),
        )

    @staticmethod
    def _current_projection_columns(metrics):
        """Small, typed projection used by navigation and screeners.

        The JSON mirrors remain stored and auditable, but are intentionally
        absent from this hot read path. Only the historical-equivalent
        fundamental price scalar is extracted from the materialized mirror;
        the route never reopens the large historical snapshot or transfers
        the complete provider payload merely to render the list.
        """
        return [
            metrics.asset_id.label("cm_asset_id"),
            metrics.fundamental_snapshot_id.label("cm_fundamental_id"),
            metrics.technical_snapshot_id.label("cm_technical_id"),
            metrics.price_bar_id.label("cm_price_bar_id"),
            metrics.score_snapshot_id.label("cm_score_id"),
            func.coalesce(
                metrics.fundamental_json["price"].as_float(),
                metrics.price,
            ).label("cm_fundamental_price"),
            metrics.fundamental_daily_liquidity.label("cm_fundamental_daily_liquidity"),
            metrics.price.label("cm_close"),
            *[
                getattr(metrics, field).label(f"cm_fundamental_{field}")
                for field in _CURRENT_FUNDAMENTAL_FIELDS
            ],
            *[
                getattr(metrics, field).label(f"cm_technical_{field}")
                for field in _CURRENT_TECHNICAL_FIELDS
            ],
            *[
                getattr(metrics, field).label(f"cm_score_{field}")
                for field in _CURRENT_SCORE_FIELDS
            ],
        ]

    @staticmethod
    def _current_projection_tuple(row):
        asset = row[0]
        values = row._mapping
        asset_id = values["cm_asset_id"]
        fundamental = None
        if values["cm_fundamental_id"] is not None:
            fundamental_values = {
                field: values[f"cm_fundamental_{field}"]
                for field in _CURRENT_FUNDAMENTAL_FIELDS
            }
            fundamental_values.update({
                "id": values["cm_fundamental_id"],
                "asset_id": asset_id,
                "price": values["cm_fundamental_price"],
                "daily_liquidity": values["cm_fundamental_daily_liquidity"],
                # row_from_orm recovers the TTM dividend exactly from price
                # and DY when no normalized provider dividend is present.
                "raw_payload": {},
            })
            fundamental = SimpleNamespace(**fundamental_values)

        technical = None
        if values["cm_technical_id"] is not None or values["cm_price_bar_id"] is not None:
            technical_values = {
                field: values[f"cm_technical_{field}"]
                for field in _CURRENT_TECHNICAL_FIELDS
            }
            technical_values.update({
                "id": values["cm_technical_id"] or values["cm_price_bar_id"],
                "asset_id": asset_id,
                "close": values["cm_close"],
                "raw_payload": {},
            })
            technical = SimpleNamespace(**technical_values)

        score = None
        if values["cm_score_id"] is not None:
            score_values = {
                field: values[f"cm_score_{field}"]
                for field in _CURRENT_SCORE_FIELDS
            }
            score_values.update({
                "id": values["cm_score_id"],
                "asset_id": asset_id,
                "details_json": {},
            })
            score = SimpleNamespace(**score_values)
        return asset, fundamental, technical, score

    @staticmethod
    def _navigation_projection_columns(metrics):
        """Typed ETF/BDR/future fields needed by the normal navigation list.

        A technical snapshot's close historically wins over a newer price-bar
        fallback in ``_current_component``.  Extracting that one JSON scalar
        preserves the public value exactly without selecting the full technical
        document.  When there is no technical snapshot, the promoted current
        price retains the existing price-bar fallback semantics.
        """
        return [
            metrics.asset_id.label("cm_nav_asset_id"),
            metrics.technical_snapshot_id.label("cm_nav_technical_id"),
            metrics.price_bar_id.label("cm_nav_price_bar_id"),
            metrics.score_snapshot_id.label("cm_nav_score_id"),
            case(
                (
                    metrics.technical_snapshot_id.is_not(None),
                    metrics.technical_json["close"].as_float(),
                ),
                else_=metrics.price,
            ).label("cm_nav_close"),
            *[
                getattr(metrics, field).label(f"cm_nav_technical_{field}")
                for field in _NAVIGATION_TECHNICAL_FIELDS
            ],
            *[
                getattr(metrics, field).label(f"cm_nav_score_{field}")
                for field in _CURRENT_SCORE_FIELDS
            ],
        ]

    @staticmethod
    def _navigation_projection_tuple(row):
        """Rebuild the established four-item universe tuple from narrow rows."""
        asset = row[0]
        values = row._mapping
        asset_id = values["cm_nav_asset_id"]

        technical = None
        if (
            values["cm_nav_technical_id"] is not None
            or values["cm_nav_price_bar_id"] is not None
        ):
            technical = SimpleNamespace(**{
                "id": values["cm_nav_technical_id"] or values["cm_nav_price_bar_id"],
                "asset_id": asset_id,
                "close": values["cm_nav_close"],
                "raw_payload": {},
                **{
                    field: values[f"cm_nav_technical_{field}"]
                    for field in _NAVIGATION_TECHNICAL_FIELDS
                },
            })

        score = None
        if values["cm_nav_score_id"] is not None:
            score = SimpleNamespace(**{
                "id": values["cm_nav_score_id"],
                "asset_id": asset_id,
                "details_json": {},
                **{
                    field: values[f"cm_nav_score_{field}"]
                    for field in _CURRENT_SCORE_FIELDS
                },
            })
        return asset, None, technical, score

    def current_technical_features(self, asset_ids) -> dict:
        ids = list(dict.fromkeys(asset_ids or []))
        if not ids:
            return {}
        rows = self.session.execute(
            select(
                AssetCurrentMetricsORM.asset_id,
                AssetCurrentMetricsORM.technical_features_json,
            ).where(AssetCurrentMetricsORM.asset_id.in_(ids))
        )
        return {
            asset_id: dict(payload or {})
            for asset_id, payload in rows
            if isinstance(payload, dict) and payload
        }

    def current_valuation_payloads(self, asset_ids) -> dict:
        """Return worker-built default valuations without touching history.

        An empty payload is intentionally omitted.  Callers can then expose
        the inexpensive Graham/DY fields already present in their base row and
        keep the peer/economic methods explicitly unavailable until the worker
        has produced a trustworthy snapshot.
        """
        ids = list(dict.fromkeys(asset_ids or []))
        if not ids:
            return {}
        rows = self.session.execute(
            select(
                AssetCurrentMetricsORM.asset_id,
                AssetCurrentMetricsORM.valuation_json,
            ).where(AssetCurrentMetricsORM.asset_id.in_(ids))
        )
        return {
            asset_id: dict(payload or {})
            for asset_id, payload in rows
            if isinstance(payload, dict) and payload
        }

    def current_valuation_snapshots_by_ticker(self, tickers) -> dict[str, dict]:
        """Load compact default valuations and their coverage state in one query.

        ``calculated_at`` distinguishes a trustworthy explicit N/D result from
        a row created before the V1.23.5 R2 navigation backfill.  Consumers may
        use the historical calculator only for the latter case.
        """
        clean = sorted({
            str(ticker or "").strip().upper()
            for ticker in (tickers or [])
            if str(ticker or "").strip()
        })
        if not clean:
            return {}
        rows = self.session.execute(
            select(
                AssetORM.ticker,
                AssetCurrentMetricsORM.valuation_json,
                AssetCurrentMetricsORM.valuation_calculated_at,
            )
            .select_from(AssetORM)
            .outerjoin(
                AssetCurrentMetricsORM,
                AssetCurrentMetricsORM.asset_id == AssetORM.id,
            )
            .where(
                AssetORM.ticker.in_(clean),
                AssetORM.is_active.is_(True),
            )
        )
        return {
            str(ticker): {
                "payload": dict(payload or {}) if isinstance(payload, dict) else {},
                "calculated_at": calculated_at,
                "covered": calculated_at is not None,
            }
            for ticker, payload, calculated_at in rows
        }

    def current_navigation_snapshot(self, asset_id) -> dict:
        """Read both compact navigation projections, normally from identity map."""
        metrics = self.session.get(AssetCurrentMetricsORM, asset_id)
        if metrics is None:
            return {"valuation": {}, "backtest_leaders": []}
        return {
            "valuation": dict(metrics.valuation_json or {}),
            "valuation_calculated_at": metrics.valuation_calculated_at,
            "backtest_leaders": list(metrics.backtest_leaders_json or []),
            "backtest_leaders_calculated_at": metrics.backtest_leaders_calculated_at,
        }

    def current_snapshot(self, asset_id):
        metrics = self.session.get(AssetCurrentMetricsORM, asset_id)
        if metrics is None:
            return None
        return (
            _current_component(metrics, "fundamental"),
            _current_component(metrics, "technical"),
            _current_component(metrics, "score"),
        )

    def _screen_current_stocks(self, filters, *, limit: int, offset: int):
        m = AssetCurrentMetricsORM
        stmt = (
            select(AssetORM, m)
            .select_from(AssetORM)
            .join(m, m.asset_id == AssetORM.id)
            .where(
                AssetORM.asset_type == "stock",
                AssetORM.is_active.is_(True),
                m.fundamental_snapshot_id.is_not(None),
                self._supported_catalog_clause({"stock"}),
            )
        )
        stmt = self._apply_min(stmt, m.roe_pct, filters.roe_min)
        stmt = self._apply_min(stmt, m.net_margin_pct, filters.net_margin_min)
        stmt = self._apply_min(stmt, m.ebit_margin_pct, filters.ebit_margin_min)
        stmt = self._apply_min(stmt, m.revenue_cagr_5y_pct, filters.revenue_cagr_5y_min)
        stmt = self._apply_min(stmt, m.pe, filters.pe_min)
        stmt = self._apply_max(stmt, m.pe, filters.pe_max)
        stmt = self._apply_max(stmt, m.pbv, filters.pbv_max)
        stmt = self._apply_min(stmt, m.dividend_yield_pct, filters.dividend_yield_min)
        stmt = self._apply_max(stmt, m.ev_ebitda, filters.ev_ebitda_max)
        stmt = self._apply_max(stmt, m.gross_debt_to_equity, filters.gross_debt_to_equity_max)
        stmt = self._apply_min(stmt, m.current_ratio, filters.current_ratio_min)
        stmt = self._apply_min(stmt, m.daily_liquidity, filters.daily_liquidity_min)
        if filters.require_below_graham:
            stmt = stmt.where(
                m.price.is_not(None), m.price > 0,
                m.pe.is_not(None), m.pe > 0,
                m.pbv.is_not(None), m.pbv > 0,
                (m.pe * m.pbv) < 22.5,
            )
        rows = self._current_metrics_page(stmt, m, limit=limit, offset=offset)
        return [(asset, fundamental, score) for asset, fundamental, _technical, score in rows]

    def _current_metrics_page(self, stmt, metrics, *, limit: int, offset: int):
        """Page on narrow typed columns before loading the selected JSON rows.

        ``asset_current_metrics`` deliberately keeps auditable JSON mirrors.
        Selecting the complete ORM row before ``ORDER BY/LIMIT`` made
        PostgreSQL carry those large values through the screener sort.  On the
        micro VM this could exceed the statement timeout.  The inner query now
        filters and sorts only identifiers plus the score; the outer query
        loads the complete rows for at most the requested page.  Ordering and
        returned objects remain identical.
        """
        page = (
            stmt.with_only_columns(
                AssetORM.id.label("asset_id"),
                metrics.alb_score.label("sort_score"),
                AssetORM.ticker.label("sort_ticker"),
            )
            .order_by(metrics.alb_score.desc().nullslast(), AssetORM.ticker)
            .offset(max(0, int(offset)))
            .limit(max(1, int(limit)))
            .subquery("current_metrics_page")
        )
        projected = self.session.execute(
            select(
                AssetORM,
                *self._current_projection_columns(metrics),
            )
            .select_from(page)
            .join(AssetORM, AssetORM.id == page.c.asset_id)
            .join(metrics, metrics.asset_id == page.c.asset_id)
            .order_by(page.c.sort_score.desc().nullslast(), page.c.sort_ticker)
        )
        return [self._current_projection_tuple(row) for row in projected]

    def _screen_current_fiis(self, filters, *, limit: int, offset: int):
        m = AssetCurrentMetricsORM
        stmt = (
            select(AssetORM, m)
            .select_from(AssetORM)
            .join(m, m.asset_id == AssetORM.id)
            .where(
                AssetORM.asset_type == "fii",
                AssetORM.is_active.is_(True),
                m.fundamental_snapshot_id.is_not(None),
                self._supported_catalog_clause({"fii"}),
            )
        )
        stmt = self._apply_max(stmt, m.pbv, filters.pbv_max)
        stmt = self._apply_min(stmt, m.dividend_yield_pct, filters.dividend_yield_min)
        stmt = self._apply_min(stmt, m.ffo_yield_pct, filters.ffo_yield_min)
        stmt = self._apply_min(stmt, m.cap_rate_pct, filters.cap_rate_min)
        stmt = self._apply_max(stmt, m.vacancy_pct, filters.vacancy_max)
        stmt = self._apply_min(
            stmt, m.fundamental_daily_liquidity, filters.daily_liquidity_min,
        )
        if filters.require_below_dividend_target:
            stmt = stmt.where(
                m.price.is_not(None), m.price > 0,
                m.dividend_yield_pct.is_not(None), m.dividend_yield_pct > 6.0,
            )
        rows = self._current_metrics_page(stmt, m, limit=limit, offset=offset)
        return [(asset, fundamental, score) for asset, fundamental, _technical, score in rows]

    def screen_latest_stocks(self, filters, limit=100, offset=0):
        """PostgreSQL-first screener: latest snapshots + filters are executed in SQL."""
        if self._current_coverage_complete({"stock"}, component="fundamental"):
            return self._screen_current_stocks(filters, limit=limit, offset=offset)
        f, latest_fundamental_id = self._latest_fundamental_alias()
        t, latest_technical_id = self._latest_technical_alias("1D")
        sc, latest_score_id = self._latest_score_alias()

        stmt = (
            select(AssetORM, f, sc)
            .select_from(AssetORM)
            .join(f, f.id == latest_fundamental_id)
            .outerjoin(t, t.id == latest_technical_id)
            .outerjoin(sc, sc.id == latest_score_id)
            .where(AssetORM.asset_type == "stock", AssetORM.is_active.is_(True), self._supported_catalog_clause({"stock"}))
        )

        stmt = self._apply_min(stmt, f.roe_pct, filters.roe_min)
        stmt = self._apply_min(stmt, f.net_margin_pct, filters.net_margin_min)
        stmt = self._apply_min(stmt, f.ebit_margin_pct, filters.ebit_margin_min)
        stmt = self._apply_min(stmt, f.revenue_cagr_5y_pct, filters.revenue_cagr_5y_min)
        stmt = self._apply_min(stmt, f.pe, filters.pe_min)
        stmt = self._apply_max(stmt, f.pe, filters.pe_max)
        stmt = self._apply_max(stmt, f.pbv, filters.pbv_max)
        stmt = self._apply_min(stmt, f.dividend_yield_pct, filters.dividend_yield_min)
        stmt = self._apply_max(stmt, f.ev_ebitda, filters.ev_ebitda_max)
        stmt = self._apply_max(stmt, f.gross_debt_to_equity, filters.gross_debt_to_equity_max)
        stmt = self._apply_min(stmt, f.current_ratio, filters.current_ratio_min)
        if filters.daily_liquidity_min is not None:
            liquidity = func.coalesce(t.daily_liquidity, f.daily_liquidity)
            stmt = stmt.where(liquidity.is_not(None), liquidity >= filters.daily_liquidity_min)

        # Graham Number condition can be reduced algebraically to P/L * P/VP < 22.5
        # for positive price, positive P/L and positive P/VP. This avoids per-row Python valuation.
        if filters.require_below_graham:
            stmt = stmt.where(
                f.price.is_not(None), f.price > 0,
                f.pe.is_not(None), f.pe > 0,
                f.pbv.is_not(None), f.pbv > 0,
                (f.pe * f.pbv) < 22.5,
            )

        stmt = stmt.order_by(sc.alb_score.desc().nullslast(), AssetORM.ticker).offset(offset).limit(limit)
        return list(self.session.execute(stmt).all())

    def screen_latest_fiis(self, filters, limit=100, offset=0):
        """PostgreSQL-first FII screener."""
        if self._current_coverage_complete({"fii"}, component="fundamental"):
            return self._screen_current_fiis(filters, limit=limit, offset=offset)
        f, latest_fundamental_id = self._latest_fundamental_alias()
        sc, latest_score_id = self._latest_score_alias()

        stmt = (
            select(AssetORM, f, sc)
            .select_from(AssetORM)
            .join(f, f.id == latest_fundamental_id)
            .outerjoin(sc, sc.id == latest_score_id)
            .where(AssetORM.asset_type == "fii", AssetORM.is_active.is_(True), self._supported_catalog_clause({"fii"}))
        )
        stmt = self._apply_max(stmt, f.pbv, filters.pbv_max)
        stmt = self._apply_min(stmt, f.dividend_yield_pct, filters.dividend_yield_min)
        stmt = self._apply_min(stmt, f.ffo_yield_pct, filters.ffo_yield_min)
        stmt = self._apply_min(stmt, f.cap_rate_pct, filters.cap_rate_min)
        stmt = self._apply_max(stmt, f.vacancy_pct, filters.vacancy_max)
        stmt = self._apply_min(stmt, f.daily_liquidity, filters.daily_liquidity_min)

        # Current V1.x dividend-target method uses current DPA / 6%. With positive price,
        # price below that ceiling is equivalent to current DY > 6%.
        if filters.require_below_dividend_target:
            stmt = stmt.where(f.price.is_not(None), f.price > 0, f.dividend_yield_pct.is_not(None), f.dividend_yield_pct > 6.0)

        stmt = stmt.order_by(sc.alb_score.desc().nullslast(), AssetORM.ticker).offset(offset).limit(limit)
        return list(self.session.execute(stmt).all())

    def latest_universe(self, asset_type: str, limit: int = 1200):
        """Latest fundamentals/technical/scores for a whole asset class in one SQL query."""
        accepted_types = {"etf", "bdr", "future"} if asset_type == "other_b3" else {asset_type}
        required_component = "fundamental" if accepted_types <= {"stock", "fii"} else "technical"
        if self._current_coverage_complete(accepted_types, component=required_component):
            if accepted_types <= {"stock", "fii"}:
                projected = self.session.execute(
                    select(
                        AssetORM,
                        *self._current_projection_columns(AssetCurrentMetricsORM),
                    )
                    .select_from(AssetORM)
                    .join(
                        AssetCurrentMetricsORM,
                        AssetCurrentMetricsORM.asset_id == AssetORM.id,
                    )
                    .where(
                        AssetORM.asset_type.in_(accepted_types),
                        AssetORM.is_active.is_(True),
                        self._supported_catalog_clause(accepted_types),
                    )
                    .order_by(AssetORM.ticker)
                    .limit(limit)
                )
                return [self._current_projection_tuple(row) for row in projected]
            rows = self.session.execute(
                select(AssetORM, AssetCurrentMetricsORM)
                .select_from(AssetORM)
                .join(AssetCurrentMetricsORM, AssetCurrentMetricsORM.asset_id == AssetORM.id)
                .where(
                    AssetORM.asset_type.in_(accepted_types),
                    AssetORM.is_active.is_(True),
                    self._supported_catalog_clause(accepted_types),
                )
                .order_by(AssetORM.ticker)
                .limit(limit)
            )
            return [self._current_universe_tuple(asset, metrics) for asset, metrics in rows]
        f, latest_fundamental_id = self._latest_fundamental_alias()
        t, latest_technical_id = self._latest_technical_alias("1D")
        sc, latest_score_id = self._latest_score_alias()
        stmt = (
            select(AssetORM, f, t, sc)
            .select_from(AssetORM)
            .outerjoin(f, f.id == latest_fundamental_id)
            .outerjoin(t, t.id == latest_technical_id)
            .outerjoin(sc, sc.id == latest_score_id)
            .where(AssetORM.asset_type.in_(accepted_types), AssetORM.is_active.is_(True), self._supported_catalog_clause(accepted_types))
            .order_by(AssetORM.ticker)
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

    def latest_navigation_universe(self, asset_type: str, limit: int = 1200):
        """Return the normal list contract without loading wide current JSON.

        Only ETF/BDR/future navigation uses this narrower representation.  The
        advanced screener and current-metrics worker intentionally continue to
        call ``latest_universe`` so class-specific raw valuation inputs remain
        available.  An incomplete materialized catalog also delegates to that
        method, preserving the historical-snapshot fallback unchanged.
        """
        accepted_types = (
            {"etf", "bdr", "future"}
            if asset_type == "other_b3"
            else {asset_type}
        )
        if not accepted_types <= {"etf", "bdr", "future"}:
            return self.latest_universe(asset_type=asset_type, limit=limit)
        if not self._current_coverage_complete(
            accepted_types, component="technical",
        ):
            return self.latest_universe(asset_type=asset_type, limit=limit)

        metrics = AssetCurrentMetricsORM
        projected = self.session.execute(
            select(
                AssetORM,
                *self._navigation_projection_columns(metrics),
            )
            .select_from(AssetORM)
            .join(metrics, metrics.asset_id == AssetORM.id)
            .where(
                AssetORM.asset_type.in_(accepted_types),
                AssetORM.is_active.is_(True),
                self._supported_catalog_clause(accepted_types),
            )
            .order_by(AssetORM.ticker)
            .limit(limit)
        )
        return [self._navigation_projection_tuple(row) for row in projected]

    def latest_market_references_by_ticker(self, tickers) -> dict[str, dict]:
        """Load current spot and income references for many tickers at once."""
        clean = sorted({str(ticker or "").strip().upper() for ticker in (tickers or []) if str(ticker or "").strip()})
        if not clean:
            return {}
        f, latest_fundamental_id = self._latest_fundamental_alias()
        t, latest_technical_id = self._latest_technical_alias("1D")
        stmt = (
            select(AssetORM, f, t)
            .select_from(AssetORM)
            .outerjoin(f, f.id == latest_fundamental_id)
            .outerjoin(t, t.id == latest_technical_id)
            .where(AssetORM.ticker.in_(clean), AssetORM.is_active.is_(True))
        )
        result = {}
        for asset, fundamental, technical in self.session.execute(stmt):
            fundamental_price = getattr(fundamental, "price", None) if fundamental is not None else None
            technical_price = getattr(technical, "close", None) if technical is not None else None
            dividend_yield = getattr(fundamental, "dividend_yield_pct", None) if fundamental is not None else None
            result[asset.ticker] = {
                # Carry should use the newest market quote. Fundamentals are
                # only the fallback when the daily technical snapshot is absent.
                "price": float(technical_price if technical_price is not None else fundamental_price) if (fundamental_price is not None or technical_price is not None) else None,
                "dividend_yield_pct": float(dividend_yield) if dividend_yield is not None else None,
                "asset_type": asset.asset_type,
            }
        return result

    def price_histories_batch(self, asset_ids, *, start=None, end=None, timeframe="1D"):
        """Load price histories for a candidate set with one query, avoiding screener N+1 reads."""
        ids = list(asset_ids or [])
        if not ids:
            return {}
        stmt = select(PriceBarORM).where(PriceBarORM.asset_id.in_(ids), PriceBarORM.timeframe == timeframe)
        if start is not None:
            stmt = stmt.where(PriceBarORM.timestamp >= start)
        if end is not None:
            stmt = stmt.where(PriceBarORM.timestamp <= end)
        stmt = stmt.order_by(PriceBarORM.asset_id, PriceBarORM.timestamp)
        out = {}
        for row in self.session.scalars(stmt):
            out.setdefault(row.asset_id, []).append(row)
        return out

    def score_history(self, asset_id, limit=120):
        stmt = select(ScoreSnapshotORM).where(ScoreSnapshotORM.asset_id == asset_id).order_by(ScoreSnapshotORM.as_of.desc()).limit(limit)
        return list(reversed(list(self.session.scalars(stmt))))

    def valuation_history(self, asset_id, method=None, limit=120):
        stmt = select(ValuationSnapshotORM).where(ValuationSnapshotORM.asset_id == asset_id)
        if method:
            stmt = stmt.where(ValuationSnapshotORM.method == method)
        stmt = stmt.order_by(ValuationSnapshotORM.as_of.desc()).limit(limit)
        return list(reversed(list(self.session.scalars(stmt))))

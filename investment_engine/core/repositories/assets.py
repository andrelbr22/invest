from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import Session, aliased
from ...infrastructure.db.models import AssetORM, FundamentalSnapshotORM, TechnicalSnapshotORM, PriceBarORM, ValuationSnapshotORM, ScoreSnapshotORM


def _decimal_or_none(value):
    if value is None:
        return None
    return Decimal(str(value))


class AssetRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_ticker(self, ticker: str) -> AssetORM | None:
        return self.session.scalar(select(AssetORM).where(AssetORM.ticker == ticker.upper()))

    def list_assets(self, asset_type: str | None = None, limit: int = 100, offset: int = 0) -> list[AssetORM]:
        stmt = select(AssetORM).order_by(AssetORM.ticker).limit(limit).offset(offset)
        if asset_type:
            stmt = stmt.where(AssetORM.asset_type == asset_type)
        return list(self.session.scalars(stmt))

    def upsert_asset(self, *, ticker: str, asset_type: str, **fields) -> AssetORM:
        ticker = ticker.upper().strip()
        asset = self.get_by_ticker(ticker)
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
        return asset

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
        return row

    def latest_fundamentals(self, asset_id) -> FundamentalSnapshotORM | None:
        stmt = (
            select(FundamentalSnapshotORM)
            .where(FundamentalSnapshotORM.asset_id == asset_id)
            .order_by(FundamentalSnapshotORM.reference_date.desc(), FundamentalSnapshotORM.retrieved_at.desc())
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
        stmt = stmt.order_by(TechnicalSnapshotORM.as_of.desc(), TechnicalSnapshotORM.retrieved_at.desc()).limit(1)
        return self.session.scalar(stmt)


    def upsert_price_bar(self, asset, *, timeframe, timestamp, source, data, retrieved_at=None, status="valid"):
        stmt=select(PriceBarORM).where(PriceBarORM.asset_id==asset.id,PriceBarORM.timeframe==timeframe,PriceBarORM.timestamp==timestamp,PriceBarORM.source==source)
        row=self.session.scalar(stmt)
        if row is None:
            row=PriceBarORM(asset_id=asset.id,timeframe=timeframe,timestamp=timestamp,source=source); self.session.add(row)
        for k in ("open","high","low","close","volume","adjusted_close"):
            if k in data:setattr(row,k,_decimal_or_none(data.get(k)))
        if retrieved_at is not None: row.retrieved_at=retrieved_at
        row.status=status; self.session.flush(); return row

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
            .order_by(PriceBarORM.timestamp.desc()).limit(1)
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
        row.coverage_pct=_decimal_or_none(coverage_pct); row.data_quality_score=_decimal_or_none(data_quality_score); row.details_json=details or {}; self.session.flush(); return row

    def latest_scores(self, asset_id):
        return self.session.scalar(select(ScoreSnapshotORM).where(ScoreSnapshotORM.asset_id==asset_id).order_by(ScoreSnapshotORM.as_of.desc(), ScoreSnapshotORM.calculated_at.desc()).limit(1))

    def _latest_fundamental_alias(self):
        ranked = (
            select(
                FundamentalSnapshotORM,
                func.row_number().over(
                    partition_by=FundamentalSnapshotORM.asset_id,
                    order_by=(FundamentalSnapshotORM.reference_date.desc(), FundamentalSnapshotORM.retrieved_at.desc()),
                ).label("rn"),
            )
            .subquery()
        )
        return aliased(FundamentalSnapshotORM, ranked), ranked

    def _latest_technical_alias(self, timeframe="1D"):
        ranked = (
            select(
                TechnicalSnapshotORM,
                func.row_number().over(
                    partition_by=TechnicalSnapshotORM.asset_id,
                    order_by=(TechnicalSnapshotORM.as_of.desc(), TechnicalSnapshotORM.retrieved_at.desc()),
                ).label("rn"),
            )
            .where(TechnicalSnapshotORM.timeframe == timeframe)
            .subquery()
        )
        return aliased(TechnicalSnapshotORM, ranked), ranked

    def _latest_score_alias(self):
        ranked = (
            select(
                ScoreSnapshotORM,
                func.row_number().over(
                    partition_by=ScoreSnapshotORM.asset_id,
                    order_by=(ScoreSnapshotORM.as_of.desc(), ScoreSnapshotORM.calculated_at.desc()),
                ).label("rn"),
            )
            .subquery()
        )
        return aliased(ScoreSnapshotORM, ranked), ranked

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

    def screen_latest_stocks(self, filters, limit=100, offset=0):
        """PostgreSQL-first screener: latest snapshots + filters are executed in SQL."""
        f, fq = self._latest_fundamental_alias()
        t, tq = self._latest_technical_alias("1D")
        sc, sq = self._latest_score_alias()

        stmt = (
            select(AssetORM, f, sc)
            .join(f, and_(f.asset_id == AssetORM.id, fq.c.rn == 1))
            .outerjoin(t, and_(t.asset_id == AssetORM.id, tq.c.rn == 1))
            .outerjoin(sc, and_(sc.asset_id == AssetORM.id, sq.c.rn == 1))
            .where(AssetORM.asset_type == "stock", AssetORM.is_active.is_(True))
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
        f, fq = self._latest_fundamental_alias()
        sc, sq = self._latest_score_alias()

        stmt = (
            select(AssetORM, f, sc)
            .join(f, and_(f.asset_id == AssetORM.id, fq.c.rn == 1))
            .outerjoin(sc, and_(sc.asset_id == AssetORM.id, sq.c.rn == 1))
            .where(AssetORM.asset_type == "fii", AssetORM.is_active.is_(True))
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
        f, fq = self._latest_fundamental_alias()
        t, tq = self._latest_technical_alias("1D")
        sc, sq = self._latest_score_alias()
        stmt = (
            select(AssetORM, f, t, sc)
            .outerjoin(f, and_(f.asset_id == AssetORM.id, fq.c.rn == 1))
            .outerjoin(t, and_(t.asset_id == AssetORM.id, tq.c.rn == 1))
            .outerjoin(sc, and_(sc.asset_id == AssetORM.id, sq.c.rn == 1))
            .where(AssetORM.asset_type == asset_type, AssetORM.is_active.is_(True))
            .order_by(AssetORM.ticker)
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

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

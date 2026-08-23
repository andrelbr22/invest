from __future__ import annotations
from datetime import datetime, timezone
from ...core.repositories.assets import AssetRepository
from ...core.indicators.technical import compute_indicators
from ..providers.prices import YahooPriceProvider


class PriceIngestionService:
    def __init__(self, session, provider=None):
        self.session = session
        self.repo = AssetRepository(session)
        self.provider = provider or YahooPriceProvider()

    def ingest_asset(self, ticker, asset_type="stock", range_="2y", start=None, end=None):
        asset = self.repo.upsert_asset(ticker=ticker, asset_type=asset_type)
        rows = self.provider.fetch(ticker, range_=range_, start=start, end=end)
        now = datetime.now(timezone.utc)
        self.repo.bulk_upsert_price_bars(asset, rows, retrieved_at=now)
        bars = [{
            "timestamp": r.timestamp,
            "open": float(r.open) if r.open is not None else None,
            "high": float(r.high) if r.high is not None else None,
            "low": float(r.low) if r.low is not None else None,
            "close": float(r.close) if r.close is not None else None,
            "volume": float(r.volume) if r.volume is not None else None,
            "adjusted_close": float(r.adjusted_close) if r.adjusted_close is not None else None,
        } for r in self.repo.price_history(asset.id, limit=700)]
        ind = compute_indicators(bars)
        if bars:
            self.repo.upsert_technical(
                asset, source="internal", timeframe="1D", as_of=bars[-1]["timestamp"], retrieved_at=now,
                status="valid", quality_score=100.0, data=ind,
                raw_payload={"bars": len(bars), "engine": "technical_v1.5"},
            )
        return {"ticker": asset.ticker, "bars": len(rows), "indicators": ind}

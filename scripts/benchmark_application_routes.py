"""Measure the real API/repository path against the configured database.

This is intentionally an operator command, not a public endpoint.  It runs the
FastAPI routes through ASGI, uses the production database configuration and
prints aggregate timings without exposing user data or credentials.
"""

from __future__ import annotations

import argparse
import math
from statistics import median
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import select

from investment_engine.api.app import (
    _request_email,
    _SCREENER_RESPONSE_CACHE,
    _SHARED_RESPONSE_CACHE,
    app,
)
from investment_engine.infrastructure.config import settings
from investment_engine.infrastructure.db.models import AssetORM
from investment_engine.infrastructure.db.session import get_session_factory


TARGETS_MS = {
    "health": 300,
    "dashboard": 1500,
    "screener_50": 2000,
    "screener_100": 3000,
    "asset_detail": 2000,
    # Extended journeys are opt-in and do not make an otherwise safe
    # promotion fail merely because an administrator did not request them.
    "universe_etf_100": 3000,
    "advanced_stock_50": 5000,
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def sample_ticker() -> str:
    session = get_session_factory()()
    try:
        ticker = session.scalar(
            select(AssetORM.ticker)
            .where(AssetORM.asset_type == "stock", AssetORM.is_active.is_(True))
            .order_by(AssetORM.ticker)
            .limit(1)
        )
        if not ticker:
            raise SystemExit("Nenhuma ação ativa disponível para medir o detalhe.")
        return str(ticker)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument(
        "--cold",
        action="store_true",
        help="invalidate process-local response caches before each request",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="also measure representative multi-asset and advanced journeys",
    )
    args = parser.parse_args()
    samples = max(5, min(100, args.samples))
    warmup = max(0, min(10, args.warmup))
    ticker = sample_ticker()
    operator = next(iter(settings.owner_emails), "benchmark@system.local")
    app.dependency_overrides[_request_email] = lambda: operator
    routes = [
        ("health", "GET", "/health", None),
        ("dashboard", "GET", "/market-dashboard", None),
        ("screener_50", "GET", "/screen/db/stocks/default?limit=50", None),
        ("screener_100", "GET", "/screen/db/stocks/default?limit=100", None),
        ("asset_detail", "GET", f"/assets/{ticker}/intelligence", None),
    ]
    if args.extended:
        routes.extend([
            ("universe_etf_100", "GET", "/screen/db/universe/etf?limit=100", None),
            (
                "advanced_stock_50", "POST", "/screen/advanced",
                {"asset_type": "stock", "limit": 50},
            ),
        ])
    try:
        client = TestClient(app, base_url="http://localhost")
        failed = False
        for label, method, path, json_body in routes:
            timings = []
            for number in range(samples + warmup):
                if args.cold:
                    _SHARED_RESPONSE_CACHE.invalidate()
                    _SCREENER_RESPONSE_CACHE.invalidate()
                started = perf_counter()
                response = client.request(method, path, json=json_body)
                elapsed = (perf_counter() - started) * 1000
                if response.status_code != 200:
                    raise SystemExit(f"{label}: HTTP {response.status_code} em {path}")
                if number >= warmup:
                    timings.append(elapsed)
            p50 = median(timings)
            p95 = percentile(timings, .95)
            target = TARGETS_MS[label]
            status = "OK" if p95 <= target else "ACIMA_DA_META"
            failed = failed or status != "OK"
            print(
                f"{label}: modo={'frio' if args.cold else 'aquecido'} "
                f"amostras={len(timings)} p50={p50:.2f}ms "
                f"p95={p95:.2f}ms máximo={max(timings):.2f}ms meta={target}ms {status}"
            )
        if failed:
            raise SystemExit(2)
    finally:
        app.dependency_overrides.pop(_request_email, None)


if __name__ == "__main__":
    main()

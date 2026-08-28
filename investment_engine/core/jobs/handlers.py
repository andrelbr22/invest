from __future__ import annotations

from datetime import timedelta

from ...data.providers.market_dashboard import MarketDashboardService
from ...infrastructure.db.session import get_session_factory
from ..repositories.economic_series import SharedSnapshotRepository, utcnow


def handle_noop(payload: dict) -> dict:
    """Health-check handler used by deployment and queue tests."""
    return {"ok": True, "echo": dict(payload or {})}


def _record_refresh_failure(snapshot_key: str, exc: Exception) -> None:
    """Keep the last valid payload while recording a safe refresh failure code."""
    session = get_session_factory()()
    try:
        SharedSnapshotRepository(session).mark_refresh_failed(snapshot_key, type(exc).__name__)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def handle_market_dashboard_refresh(payload: dict) -> dict:
    """Fetch and persist the shared dashboard without blocking a browser request."""
    snapshot_key = str(payload.get("snapshot_key") or "market-dashboard:main")
    try:
        result = MarketDashboardService().build()
    except Exception as exc:
        _record_refresh_failure(snapshot_key, exc)
        raise
    session = get_session_factory()()
    try:
        row = SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key,
            snapshot_kind="market_dashboard",
            payload=result,
            source="configured-market-providers",
            as_of=utcnow(),
            valid_until=utcnow() + timedelta(hours=6),
        )
        session.commit()
        return {"snapshot_key": row.snapshot_key, "payload_hash": row.payload_hash}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def handle_economy_headlines_refresh(payload: dict) -> dict:
    snapshot_key = str(payload.get("snapshot_key") or "economy-headlines:main")
    try:
        result = MarketDashboardService().economy_headlines(limit=max(1, min(10, int(payload.get("limit") or 5))))
    except Exception as exc:
        _record_refresh_failure(snapshot_key, exc)
        raise
    session = get_session_factory()()
    try:
        row = SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key,
            snapshot_kind="economy_headlines",
            payload=result,
            source="configured-news-providers",
            as_of=utcnow(),
            valid_until=utcnow() + timedelta(hours=1),
        )
        session.commit()
        return {"snapshot_key": row.snapshot_key, "payload_hash": row.payload_hash}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DEFAULT_JOB_HANDLERS = {
    "noop": handle_noop,
    "market_dashboard_refresh": handle_market_dashboard_refresh,
    "economy_headlines_refresh": handle_economy_headlines_refresh,
}

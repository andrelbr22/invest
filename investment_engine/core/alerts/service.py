from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..repositories.alerts import AlertRepository, alert_dict, event_dict
from ...data.providers.intraday import IntradayQuoteProvider
from ...integrations.email_delivery import AlertEmailSender
from ...infrastructure.config import settings
from ...infrastructure.db.models import PriceAlertORM
from ...infrastructure.db.session import get_session_factory


logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(value: str | None) -> bool:
    clean = str(value or "").strip()
    return not clean or bool(EMAIL_PATTERN.fullmatch(clean))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def is_b3_monitoring_window(now: datetime) -> bool:
    local = _utc(now).astimezone(ZoneInfo("America/Sao_Paulo"))
    return local.weekday() < 5 and 10 <= local.hour < 18


def evaluate_alert(alert, quote: dict) -> tuple[list[str], dict]:
    rules, values = [], {}
    if alert.price_above is not None:
        values["price_above"] = float(alert.price_above)
        if float(quote["high"]) >= float(alert.price_above):
            rules.append("price_above")
    if alert.price_below is not None:
        values["price_below"] = float(alert.price_below)
        if float(quote["low"]) <= float(alert.price_below):
            rules.append("price_below")
    change = quote.get("change_pct")
    if alert.change_positive_pct is not None:
        values["change_positive_pct"] = float(alert.change_positive_pct)
        if change is not None and float(change) >= float(alert.change_positive_pct):
            rules.append("change_positive_pct")
    if alert.change_negative_pct is not None:
        values["change_negative_pct"] = float(alert.change_negative_pct)
        if change is not None and float(change) <= -abs(float(alert.change_negative_pct)):
            rules.append("change_negative_pct")
    return rules, values


class AlertService:
    def __init__(self, session):
        self.session = session
        self.repository = AlertRepository(session)

    def dashboard(self, owner_email: str, *, limit: int, permissions: dict, smtp_configured: bool) -> dict:
        preference = self.repository.preference(owner_email)
        alerts = self.repository.list_for_owner(owner_email)
        return {
            "primary_email": owner_email,
            "secondary_email": preference.secondary_email if preference else None,
            "delivery_configured": smtp_configured,
            "limit": limit,
            "active_count": sum(1 for row in alerts if row.status == "active"),
            "permissions": permissions,
            "alerts": [alert_dict(row) for row in alerts],
            "history": [event_dict(row) for row in self.repository.history(owner_email)],
        }


class AlertMonitor:
    """One lightweight monitor per API process with quote de-duplication."""

    def __init__(self, *, provider=None, sender=None, poll_seconds: int | None = None):
        self.provider = provider or IntradayQuoteProvider()
        self.sender = sender or AlertEmailSender()
        self.poll_seconds = max(30, int(poll_seconds or settings.alert_monitor_poll_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()
        self._run_lock = threading.Lock()

    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="price-alert-monitor", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("price alert cycle failed")
            self._stop.wait(self.poll_seconds)

    def run_once(self, now: datetime | None = None) -> dict:
        if not self._run_lock.acquire(blocking=False):
            return {"checked": 0, "triggered": 0, "delivered": 0, "quote_failures": 0, "already_running": True}
        try:
            return self._run_once(now)
        finally:
            self._run_lock.release()

    def _run_once(self, now: datetime | None = None) -> dict:
        now = _utc(now or datetime.now(timezone.utc))
        session_factory = get_session_factory()
        with session_factory() as session:
            repository = AlertRepository(session)
            due = repository.due_alerts(now)
            if not is_b3_monitoring_window(now):
                due = [row for row in due if row.market_scope != "b3"]
            snapshots = [
                {
                    "id": row.id, "scope": row.market_scope,
                    "provider_symbol": row.provider_symbol,
                }
                for row in due
            ]
            for row in due:
                repository.mark_checked(row, now)
            session.commit()

        quote_cache, failures = {}, 0
        for item in snapshots:
            key = (item["scope"], item["provider_symbol"])
            if key in quote_cache:
                continue
            try:
                quote_cache[key] = self.provider.snapshot(
                    item["provider_symbol"].split("|"), market_scope=item["scope"]
                )
            except Exception as exc:
                failures += 1
                logger.warning("alert quote unavailable for %s: %s", item["provider_symbol"], exc)

        triggered = 0
        for item in snapshots:
            quote = quote_cache.get((item["scope"], item["provider_symbol"]))
            if not quote:
                continue
            with session_factory() as session:
                row = session.get(PriceAlertORM, item["id"])
                if row is None or row.status != "active":
                    continue
                if row.last_quote_at is not None and _utc(row.last_quote_at) >= _utc(quote["quote_at"]):
                    continue
                repository = AlertRepository(session)
                repository.record_observation(row, quote)
                matched, configured = evaluate_alert(row, quote)
                if matched:
                    preference = repository.preference(row.owner_email)
                    recipients = [row.owner_email]
                    if preference and preference.secondary_email:
                        recipients.append(preference.secondary_email)
                    observed = {
                        **{key: quote.get(key) for key in (
                            "price", "high", "low", "previous_close", "change_pct",
                            "currency", "interval", "source",
                        )},
                        "quote_at": _utc(quote["quote_at"]).isoformat(),
                    }
                    repository.trigger(
                        row, rules=matched, configured_values=configured,
                        observed=observed, recipients=recipients,
                    )
                    triggered += 1
                session.commit()

        delivered = self.deliver_pending()
        return {"checked": len(snapshots), "triggered": triggered, "delivered": delivered, "quote_failures": failures}

    def deliver_pending(self) -> int:
        if not self.sender.configured:
            return 0
        delivered = 0
        session_factory = get_session_factory()
        with session_factory() as session:
            event_ids = [row.id for row in AlertRepository(session).pending_deliveries(datetime.now(timezone.utc))]
        for event_id in event_ids:
            with session_factory() as session:
                from ...infrastructure.db.models import PriceAlertEventORM
                event = session.get(PriceAlertEventORM, event_id)
                if event is None or event.delivery_status != "pending":
                    continue
                repository = AlertRepository(session)
                payload = event_dict(event)
                try:
                    self.sender.send_alert(payload)
                    repository.delivery_sent(event)
                    delivered += 1
                except Exception as exc:
                    repository.delivery_failed(event, str(exc))
                session.commit()
        return delivered

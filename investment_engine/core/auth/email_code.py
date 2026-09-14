from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections import deque
import hashlib
import hmac
import re
import secrets
import threading
import time
import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from ...infrastructure.db.models import EmailLoginCodeORM


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CODE_PATTERN = re.compile(r"^\d{6}$")
CODE_TTL = timedelta(minutes=10)
REQUEST_COOLDOWN = timedelta(minutes=1)
MAX_ATTEMPTS = 5
EXPIRED_CODE_RETENTION = timedelta(days=1)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalized_email(value: object) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("invalid_email_address")
    return email


def normalized_code(value: object) -> str:
    code = re.sub(r"\D", "", str(value or ""))
    if not CODE_PATTERN.fullmatch(code):
        raise ValueError("invalid_email_login_code")
    return code


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _digest(*, secret: str, email: str, code: str, salt: str) -> str:
    key = hashlib.sha256(str(secret).encode("utf-8")).digest()
    payload = f"{email}\n{code}\n{salt}".encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


class EmailLoginRequestGuard:
    """Small process-local safety valve in addition to the database e-mail limit.

    The durable one-request-per-minute rule remains keyed by e-mail in
    ``email_login_codes``.  This guard limits bursts spread over many addresses
    from one client and also protects the SMTP provider during a broad spike.
    The web service has a single process in the supported deployment, so this
    deliberately simple bound is effective without storing raw client IPs.
    """

    def __init__(
        self,
        *,
        client_limit: int = 30,
        global_limit: int = 300,
        window_seconds: int = 600,
    ):
        self.client_limit = max(1, int(client_limit))
        self.global_limit = max(self.client_limit, int(global_limit))
        self.window_seconds = max(60, int(window_seconds))
        self._lock = threading.Lock()
        self._global: deque[float] = deque()
        self._clients: dict[str, deque[float]] = {}

    def _prune(self, values: deque[float], cutoff: float) -> None:
        while values and values[0] <= cutoff:
            values.popleft()

    def reserve(self, client_fingerprint: str, *, now: float | None = None) -> int | None:
        current = time.monotonic() if now is None else float(now)
        cutoff = current - self.window_seconds
        clean = str(client_fingerprint or "unknown")[:80]
        with self._lock:
            self._prune(self._global, cutoff)
            values = self._clients.setdefault(clean, deque())
            self._prune(values, cutoff)
            if len(values) >= self.client_limit:
                return max(1, int(values[0] + self.window_seconds - current) + 1)
            if len(self._global) >= self.global_limit:
                return max(1, int(self._global[0] + self.window_seconds - current) + 1)
            values.append(current)
            self._global.append(current)
            # Remove empty buckets left by prior windows without retaining an
            # unbounded list of client fingerprints.
            if len(self._clients) > self.global_limit * 2:
                self._clients = {
                    key: bucket for key, bucket in self._clients.items() if bucket
                }
            return None

    def clear(self) -> None:
        with self._lock:
            self._global.clear()
            self._clients.clear()


class EmailLoginCodeService:
    def __init__(self, session: Session, *, secret: str):
        if len(str(secret or "")) < 32:
            raise ValueError("email_login_secret_not_configured")
        self.session = session
        self.secret = str(secret)

    def get(self, email: str) -> EmailLoginCodeORM | None:
        return self.session.scalar(
            select(EmailLoginCodeORM).where(EmailLoginCodeORM.email == normalized_email(email))
        )

    def _get_for_update(self, email: str) -> EmailLoginCodeORM | None:
        # Serializes requests for an address on PostgreSQL.  The primary key
        # still protects the first simultaneous insertion when no row exists.
        return self.session.scalar(
            select(EmailLoginCodeORM)
            .where(EmailLoginCodeORM.email == normalized_email(email))
            .with_for_update()
        )

    def _serialize_first_issue(self, email: str) -> None:
        """Serialize the first insert for one address on PostgreSQL.

        ``SELECT ... FOR UPDATE`` cannot lock a row that does not exist yet.
        A transaction-scoped advisory lock closes that small race without
        exposing the address itself or imposing a global login bottleneck.
        """
        bind = self.session.get_bind()
        if bind.dialect.name != "postgresql":
            return
        lock_id = int.from_bytes(
            hashlib.sha256(normalized_email(email).encode("utf-8")).digest()[:8],
            byteorder="big",
            signed=True,
        )
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        """Remove old consumed/expired challenges without touching recent codes."""
        current = _aware(now or utcnow())
        result = self.session.execute(
            delete(EmailLoginCodeORM).where(
                EmailLoginCodeORM.expires_at < current - EXPIRED_CODE_RETENTION
            )
        )
        return int(result.rowcount or 0)

    def issue(self, email: str, *, now: datetime | None = None) -> tuple[EmailLoginCodeORM, str]:
        clean = normalized_email(email)
        current = _aware(now or utcnow())
        self.cleanup_expired(now=current)
        self._serialize_first_issue(clean)
        row = self._get_for_update(clean)
        if row is not None and current < _aware(row.requested_at) + REQUEST_COOLDOWN:
            remaining = int((_aware(row.requested_at) + REQUEST_COOLDOWN - current).total_seconds())
            raise ValueError(f"email_login_rate_limited:{max(1, remaining)}")
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_urlsafe(24)
        values = {
            "code_hash": _digest(secret=self.secret, email=clean, code=code, salt=salt),
            "salt": salt,
            "requested_at": current,
            "expires_at": current + CODE_TTL,
            "consumed_at": None,
            "attempts": 0,
            "request_id": uuid.uuid4(),
            "updated_at": current,
        }
        if row is None:
            row = EmailLoginCodeORM(email=clean, **values)
            self.session.add(row)
        else:
            for field, value in values.items():
                setattr(row, field, value)
        self.session.flush()
        return row, code

    def verify(self, email: str, code: str, *, now: datetime | None = None) -> bool:
        clean = normalized_email(email)
        supplied = normalized_code(code)
        current = _aware(now or utcnow())
        row = self._get_for_update(clean)
        if row is None or row.consumed_at is not None or current > _aware(row.expires_at):
            return False
        if int(row.attempts or 0) >= MAX_ATTEMPTS:
            return False
        row.attempts = int(row.attempts or 0) + 1
        row.updated_at = current
        expected = _digest(secret=self.secret, email=clean, code=supplied, salt=row.salt)
        accepted = hmac.compare_digest(expected, row.code_hash)
        if accepted or row.attempts >= MAX_ATTEMPTS:
            row.consumed_at = current
        self.session.flush()
        return accepted

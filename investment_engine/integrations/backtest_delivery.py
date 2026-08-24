from __future__ import annotations

import hashlib
import json
import time
from urllib.parse import urlparse

import requests


CALLBACK_API_VERSION = "1"


class BacktestDeliveryError(RuntimeError):
    """Safe callback error that never includes the credential or response body."""


def delivery_checksum(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_callback_url(value: str) -> str:
    clean = str(value or "").strip().rstrip("/")
    parsed = urlparse(clean)
    local_hosts = {"localhost", "127.0.0.1", "testserver"}
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BacktestDeliveryError("O endereço de entrega dos resultados é inválido.")
    if parsed.scheme != "https" and parsed.hostname not in local_hosts:
        raise BacktestDeliveryError("A entrega dos resultados exige HTTPS.")
    return clean


class BacktestDeliveryClient:
    def __init__(
        self, *, base_url: str, token: str, http=requests,
        timeout: int = 60, attempts: int = 4,
    ):
        self.base_url = validate_callback_url(base_url)
        self.token = str(token or "").strip()
        if len(self.token) < 32:
            raise BacktestDeliveryError("A credencial de entrega não foi configurada corretamente.")
        self.http = http
        self.timeout = max(5, int(timeout))
        self.attempts = max(1, min(int(attempts), 6))

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Backtest-Callback-Version": CALLBACK_API_VERSION,
        }

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        last_status = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = self.http.post(
                    url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout,
                )
                last_status = response.status_code
                if 200 <= response.status_code < 300:
                    data = response.json()
                    return data if isinstance(data, dict) else {}
                if response.status_code not in {408, 425, 429, 500, 502, 503, 504}:
                    break
            except requests.RequestException:
                pass
            if attempt < self.attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
        status_note = f" (HTTP {last_status})" if last_status else ""
        raise BacktestDeliveryError(f"A Oracle não confirmou a entrega dos resultados{status_note}.")

    def start_job(
        self, *, source: str, max_combinations: int,
        job_id: str | None = None, tickers: list[str] | None = None,
    ) -> dict:
        return self._post("/automation/backtests/jobs/start", {
            "source": source,
            "job_id": job_id,
            "tickers": list(tickers or []),
            "max_combinations": int(max_combinations),
        })

    def deliver_asset(self, job_id: str, payload: dict) -> dict:
        body = dict(payload)
        body["checksum"] = delivery_checksum(payload)
        return self._post(f"/automation/backtests/jobs/{job_id}/assets", body)

    def finish_job(self, job_id: str) -> dict:
        return self._post(f"/automation/backtests/jobs/{job_id}/complete", {})

    def fail_job(self, job_id: str, *, code: str, message: str, details: dict | None = None) -> dict:
        return self._post(f"/automation/backtests/jobs/{job_id}/failed", {
            "code": str(code)[:80],
            "message": str(message)[:500],
            "details": dict(details or {}),
        })

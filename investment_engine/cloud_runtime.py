"""Runtime adapter for hosting the API inside Streamlit Community Cloud."""

from __future__ import annotations

import os
import socket
import threading
import time
import json
from urllib.request import urlopen
from pathlib import Path


_START_LOCK = threading.Lock()
_API_THREAD: threading.Thread | None = None
_API_SERVER = None


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "true" if default else "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _running_api_version(host: str, port: int) -> str | None:
    try:
        with urlopen(f"http://{host}:{port}/health", timeout=1.0) as response:
            return str(json.loads(response.read().decode("utf-8")).get("version") or "")
    except Exception:
        return None


def _stop_stale_api(host: str, port: int) -> None:
    global _API_THREAD, _API_SERVER
    if _API_SERVER is not None:
        _API_SERVER.should_exit = True
    if _API_THREAD is not None and _API_THREAD.is_alive():
        _API_THREAD.join(timeout=10)
    deadline = time.monotonic() + 10
    while _port_is_open(host, port) and time.monotonic() < deadline:
        time.sleep(0.2)
    _API_THREAD = None
    _API_SERVER = None


def _normalize_database_urls() -> None:
    """Accept Neon connection strings exactly as copied from its dashboard."""

    for name in ("DATABASE_URL", "DATABASE_ADMIN_URL"):
        value = os.getenv(name, "").strip()
        if value.startswith("postgresql://"):
            os.environ[name] = value.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )


def _run_migrations() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL não configurada. Adicione a conexão PostgreSQL em "
            "Settings > Secrets no Streamlit Community Cloud."
        )

    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    command.upgrade(config, "head")


def _serve_api(host: str, port: int) -> None:
    global _API_SERVER

    import uvicorn
    from investment_engine.api.app import app

    configuration = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=os.getenv("EMBEDDED_API_LOG_LEVEL", "warning"),
        access_log=False,
    )
    _API_SERVER = uvicorn.Server(configuration)
    _API_SERVER.run()


def ensure_cloud_runtime() -> None:
    """Apply migrations and start the private API once per Python process."""

    global _API_THREAD

    if not _enabled("EMBEDDED_API_ENABLED", True):
        return

    _normalize_database_urls()

    host = os.getenv("EMBEDDED_API_HOST", "127.0.0.1")
    port = int(os.getenv("EMBEDDED_API_PORT", "8765"))
    expected_version = os.getenv("EXPECTED_EMBEDDED_API_VERSION", "").strip()

    if _port_is_open(host, port):
        if not expected_version or _running_api_version(host, port) == expected_version:
            return
        _stop_stale_api(host, port)

    with _START_LOCK:
        if _port_is_open(host, port):
            if not expected_version or _running_api_version(host, port) == expected_version:
                return
            _stop_stale_api(host, port)
        if _API_THREAD is not None and _API_THREAD.is_alive():
            return

        _run_migrations()
        _API_THREAD = threading.Thread(
            target=_serve_api,
            args=(host, port),
            name="investment-engine-api",
            daemon=True,
        )
        _API_THREAD.start()

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if _port_is_open(host, port):
                return
            if not _API_THREAD.is_alive():
                break
            time.sleep(0.2)

        raise RuntimeError("A API interna não iniciou dentro do prazo esperado.")

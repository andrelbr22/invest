"""Streamlit Community Cloud entry point.

The public Streamlit process hosts the user interface.  A private FastAPI
server is started inside the same container so the existing application can
keep using its HTTP API without exposing a second public service.
"""

from __future__ import annotations

import os
import runpy
from pathlib import Path


os.environ.setdefault("EMBEDDED_API_ENABLED", "true")
os.environ.setdefault("EMBEDDED_API_HOST", "127.0.0.1")
os.environ.setdefault("EMBEDDED_API_PORT", "8765")
os.environ.setdefault("INVESTMENT_API_URL", "http://127.0.0.1:8765")
os.environ.setdefault("SHOW_API_SELECTOR", "false")
os.environ.setdefault("APP_AUTH_REQUIRED", "true")
os.environ.setdefault("APP_ENVIRONMENT", "streamlit-cloud")
os.environ["EXPECTED_EMBEDDED_API_VERSION"] = "0.11.4"

from investment_engine.cloud_runtime import ensure_cloud_runtime


ensure_cloud_runtime()

APP_FILE = Path(__file__).resolve().parent / "examples" / "streamlit_v15_integrated.py"
runpy.run_path(str(APP_FILE), run_name="__main__")

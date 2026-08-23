"""Compatibility entry point for the existing Streamlit Community Cloud app."""

from __future__ import annotations

import runpy
from pathlib import Path


runpy.run_path(
    str(Path(__file__).resolve().parent / "streamlit_app.py"),
    run_name="__main__",
)

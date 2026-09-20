"""Compatibility import for process managers that expect a root module."""

from investment_engine.api.app import app

__all__ = ["app"]

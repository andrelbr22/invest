"""Persistent background work used by V1.20 and later releases."""

__all__ = ["BackgroundWorker"]


def __getattr__(name: str):
    # Keep the historical package-level import without importing the worker
    # while schedules/observability are still being initialised.
    if name == "BackgroundWorker":
        from .worker import BackgroundWorker

        return BackgroundWorker
    raise AttributeError(name)

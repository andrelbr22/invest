from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable, Generic, Hashable, TypeVar


K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


@dataclass(frozen=True)
class _CacheEntry(Generic[V]):
    expires_at: float
    value: V


class BoundedTTLCache(Generic[K, V]):
    """Small process-local cache for immutable response payloads.

    Values are copied when written and read so one request cannot mutate the
    cached object seen by another request.  The size bound prevents a long-
    lived API process from accumulating arbitrary user keys.
    """

    def __init__(self, ttl_seconds: float, *, max_entries: int = 2048):
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[K, _CacheEntry[V]] = OrderedDict()
        self._lock = RLock()
        # Every invalidation advances the generation, even when the requested
        # key is not present yet.  A request that loaded a value concurrently
        # before a permission/preset update therefore cannot put the stale
        # value back after the update committed.
        self._generation = 0

    def get(self, key: K) -> tuple[bool, V | None]:
        found, value, _generation = self.get_with_generation(key)
        return found, value

    def get_with_generation(self, key: K) -> tuple[bool, V | None, int]:
        """Return the value and the generation observed by this read.

        Cache-miss loaders should publish with :meth:`set_if_generation` so a
        concurrent invalidation always wins over an older database read.
        """
        now = monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False, None, self._generation
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return False, None, self._generation
            self._entries.move_to_end(key)
            return True, deepcopy(entry.value), self._generation

    def set(self, key: K, value: V) -> None:
        if self.ttl_seconds <= 0:
            return
        with self._lock:
            self._set_locked(key, value)

    def set_if_generation(self, key: K, value: V, generation: int) -> bool:
        """Publish a loaded value only if no invalidation happened meanwhile."""
        if self.ttl_seconds <= 0:
            return False
        with self._lock:
            if int(generation) != self._generation:
                return False
            self._set_locked(key, value)
            return True

    def _set_locked(self, key: K, value: V) -> None:
        self._entries[key] = _CacheEntry(
            expires_at=monotonic() + self.ttl_seconds,
            value=deepcopy(value),
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def invalidate(self, predicate: Callable[[K], bool] | None = None) -> int:
        with self._lock:
            self._generation += 1
            if predicate is None:
                removed = len(self._entries)
                self._entries.clear()
                return removed
            keys = [key for key in self._entries if predicate(key)]
            for key in keys:
                self._entries.pop(key, None)
            return len(keys)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

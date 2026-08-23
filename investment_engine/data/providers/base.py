from __future__ import annotations
from abc import ABC, abstractmethod


class StockFundamentalsProvider(ABC):
    @abstractmethod
    def fetch(self) -> list[dict]: ...


class FiiFundamentalsProvider(ABC):
    @abstractmethod
    def fetch(self) -> list[dict]: ...

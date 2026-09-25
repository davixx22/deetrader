from abc import ABC, abstractmethod
from typing import Any

from app.schemas.trading import TradeProposal


class BaseStrategy(ABC):
    name: str

    @abstractmethod
    def analyze(self, symbol: str, data: list[dict[str, Any]]) -> dict[str, Any]: ...

    @abstractmethod
    def generate_signal(self, symbol: str, analysis: dict[str, Any]) -> TradeProposal | None: ...

    @abstractmethod
    def calculate_confidence(self, analysis: dict[str, Any]) -> int: ...

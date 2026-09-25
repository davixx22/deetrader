import uuid
from decimal import Decimal
from typing import Any

from app.schemas.trading import Direction, TradeProposal
from app.strategies.base import BaseStrategy

D = Decimal


class TechnicalStrategy(BaseStrategy):
    name = "technical"
    direction = Direction.LONG

    def analyze(self, symbol: str, data: list[dict[str, Any]]) -> dict[str, Any]:
        closes = [D(str(x["close"])) for x in data]
        volumes = [D(str(x["volume"])) for x in data]
        last = closes[-1]
        window = closes[-20:]
        sma = sum(window, D("0")) / D(len(window))
        momentum = (last / closes[-6] - 1) * 100 if len(closes) > 6 else D("0")
        volume_window = volumes[-20:]
        rel_volume = volumes[-1] / (sum(volume_window, D("0")) / D(len(volume_window)))
        return {
            "symbol": symbol,
            "price": last,
            "sma": sma,
            "momentum": momentum,
            "relative_volume": rel_volume,
            "atr": max(closes[-14:]) - min(closes[-14:]),
        }

    def calculate_confidence(self, a: dict[str, Any]) -> int:
        return max(0, min(100, int(55 + abs(a["momentum"]) * 4 + (a["relative_volume"] - 1) * 12)))

    def generate_signal(self, symbol: str, a: dict[str, Any]) -> TradeProposal | None:
        confidence = self.calculate_confidence(a)
        if confidence < 60:
            return None
        entry = a["price"]
        risk = max(a["atr"] * D("0.25"), entry * D("0.01"))
        if self.direction == Direction.LONG:
            stop = entry - risk
            target = entry + risk * D("2")
        else:
            stop = entry + risk
            target = entry - risk * D("2")
        return TradeProposal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            direction=self.direction,
            entry=entry,
            stop_loss=stop,
            take_profit=target,
            strategy=self.name,
            strategy_confidence=confidence,
        )


class MomentumShortStrategy(TechnicalStrategy):
    name = "momentum-short"
    direction = Direction.SHORT


class OverextendedShortStrategy(TechnicalStrategy):
    name = "overextended-short"
    direction = Direction.SHORT


class BreakdownShortStrategy(TechnicalStrategy):
    name = "breakdown-short"
    direction = Direction.SHORT


class MeanReversionStrategy(TechnicalStrategy):
    name = "mean-reversion"
    direction = Direction.LONG


class VolatilityStrategy(TechnicalStrategy):
    name = "volatility"
    direction = Direction.LONG


STRATEGIES = {
    x.name: x()
    for x in [
        MomentumShortStrategy,
        OverextendedShortStrategy,
        BreakdownShortStrategy,
        MeanReversionStrategy,
        VolatilityStrategy,
    ]
}

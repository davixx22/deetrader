from decimal import Decimal
from typing import Protocol


class MarketDataProvider(Protocol):
    async def snapshot(self, symbol: str) -> dict: ...


class MockMarketDataProvider:
    async def snapshot(self, symbol: str) -> dict:
        seed = sum(map(ord, symbol))
        price = Decimal(80 + seed % 240)
        return {
            "symbol": symbol,
            "price": price,
            "change_percent": Decimal((seed % 900) - 450) / 100,
            "volume": 500_000 + seed * 1400,
            "relative_volume": Decimal("1.2") + Decimal(seed % 20) / 10,
            "market_cap": seed * 1_000_000,
            "atr": price * Decimal("0.028"),
            "rsi": 45 + seed % 35,
            "ema": price * Decimal("0.99"),
            "sma": price * Decimal("1.01"),
            "vwap": price * Decimal("1.002"),
            "volume_spike": seed % 3 == 0,
            "week_52_distance": Decimal(seed % 30),
            "volatility": Decimal("0.35"),
            "trend": "down" if seed % 2 else "up",
            "shortable": seed % 5 != 0,
        }


class MarketScanner:
    def __init__(self, provider: MarketDataProvider):
        self.provider = provider

    async def scan(self, symbols: list[str], filters: dict) -> list[dict]:
        results = []
        for symbol in symbols:
            row = await self.provider.snapshot(symbol)
            if "min_price" in filters and row["price"] < Decimal(str(filters["min_price"])):
                continue
            if "max_price" in filters and row["price"] > Decimal(str(filters["max_price"])):
                continue
            if row["relative_volume"] < Decimal(str(filters.get("min_relative_volume", 0))):
                continue
            if filters.get("shortable") and not row["shortable"]:
                continue
            results.append(row)
        return sorted(results, key=lambda x: x["relative_volume"], reverse=True)

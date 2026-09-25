import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.brokers.base import BrokerAdapter
from app.schemas.trading import Direction, MarketQuote, OrderRequest

D = Decimal


class PaperBrokerAdapter(BrokerAdapter):
    def __init__(
        self,
        starting_cash: Decimal | None = None,
        fee_rate: Decimal = D("0.001"),
        slippage_bps: Decimal = D("3"),
        spread_bps: Decimal = D("4"),
    ):
        self.configured = starting_cash is not None
        self.cash = starting_cash or D("0")
        self.starting_cash = starting_cash or D("0")
        self.fee_rate = fee_rate
        self.slippage_bps = slippage_bps
        self.spread_bps = spread_bps
        self.connected = False
        self.prices: dict[str, MarketQuote] = {}
        self.positions: dict[str, dict[str, Any]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.trades: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    def set_price(self, symbol: str, price: Decimal, shortable: bool = True):
        half = price * self.spread_bps / D("20000")
        self.prices[symbol] = MarketQuote(
            symbol=symbol, bid=price - half, ask=price + half, last=price, shortable=shortable
        )

    async def get_market_price(self, symbol: str) -> MarketQuote:
        if symbol not in self.prices:
            self.set_price(symbol, D("100"))
        return self.prices[symbol]

    async def get_short_availability(self, symbol: str) -> bool:
        return (await self.get_market_price(symbol)).shortable

    def _unrealized(self) -> Decimal:
        total = D("0")
        for symbol, p in self.positions.items():
            mark = self.prices.get(
                symbol, MarketQuote(symbol=symbol, bid=p["entry"], ask=p["entry"], last=p["entry"])
            ).last
            delta = mark - p["entry"] if p["direction"] == Direction.LONG else p["entry"] - mark
            total += delta * p["quantity"]
        return total

    async def get_account(self):
        exposure = D("0")
        for symbol, position in self.positions.items():
            exposure += position["quantity"] * (await self.get_market_price(symbol)).last
        equity = (
            self.cash
            + sum(p["quantity"] * p["entry"] for p in self.positions.values())
            + self._unrealized()
        )
        return {
            "configured": self.configured,
            "cash": self.cash,
            "equity": equity,
            "buying_power": max(D("0"), equity * 2 - exposure),
            "unrealized_pnl": self._unrealized(),
            "currency": "CZK",
        }

    async def configure_account(self, starting_cash: Decimal, reset: bool = False):
        if starting_cash <= 0:
            raise ValueError("Starting cash must be greater than zero")
        async with self._lock:
            has_activity = bool(self.positions or self.orders or self.trades)
            if has_activity and not reset:
                raise RuntimeError("PAPER_ACCOUNT_HAS_ACTIVITY")
            if reset:
                self.positions.clear()
                self.orders.clear()
                self.trades.clear()
            self.cash = starting_cash
            self.starting_cash = starting_cash
            self.configured = True
        return await self.get_account()

    async def get_positions(self):
        return list(self.positions.values())

    async def get_orders(self):
        return list(self.orders.values())

    async def get_buying_power(self):
        return (await self.get_account())["buying_power"]

    async def get_trade_history(self):
        return self.trades.copy()

    async def submit_order(self, request: OrderRequest, quantity: Decimal):
        return await self._fill(request, quantity, bracket=False)

    async def submit_bracket_order(self, request: OrderRequest, quantity: Decimal):
        return await self._fill(request, quantity, bracket=True)

    async def _fill(self, request: OrderRequest, quantity: Decimal, bracket: bool):
        async with self._lock:
            if not self.connected:
                raise RuntimeError("BROKER_DISCONNECTED")
            if not self.configured:
                raise RuntimeError("PAPER_ACCOUNT_NOT_CONFIGURED")
            if any(o["client_order_id"] == request.idempotency_key for o in self.orders.values()):
                return next(
                    o
                    for o in self.orders.values()
                    if o["client_order_id"] == request.idempotency_key
                )
            quote = await self.get_market_price(request.proposal.symbol)
            if request.proposal.direction == Direction.SHORT and not quote.shortable:
                raise RuntimeError("SHORT_UNAVAILABLE")
            slip = quote.last * self.slippage_bps / D("10000")
            fill = (
                quote.ask + slip
                if request.proposal.direction == Direction.LONG
                else quote.bid - slip
            )
            notional = (quantity * fill).quantize(D("0.01"))
            fee = (notional * self.fee_rate).quantize(D("0.01"))
            if notional + fee > await self.get_buying_power():
                raise RuntimeError("INSUFFICIENT_BUYING_POWER")
            order_id = str(uuid.uuid4())
            order = {
                "id": order_id,
                "client_order_id": request.idempotency_key,
                "proposal_id": request.proposal.id,
                "symbol": request.proposal.symbol,
                "quantity": quantity,
                "fill_price": fill.quantize(D("0.0001")),
                "fees": fee,
                "status": "FILLED",
                "bracket": bracket,
                "created_at": datetime.now(UTC),
            }
            self.orders[order_id] = order
            self.positions[request.proposal.symbol] = {
                "symbol": request.proposal.symbol,
                "direction": request.proposal.direction,
                "quantity": quantity,
                "entry": fill,
                "stop_loss": request.proposal.stop_loss,
                "take_profit": request.proposal.take_profit,
                "strategy": request.proposal.strategy,
                "opened_at": datetime.now(UTC),
            }
            self.cash -= notional + fee
            return order

    async def cancel_order(self, order_id: str):
        order = self.orders[order_id]
        if order["status"] == "FILLED":
            raise RuntimeError("FILLED_ORDER_CANNOT_BE_CANCELLED")
        order["status"] = "CANCELLED"
        return order

    async def close_position(self, symbol: str, quantity: Decimal | None = None):
        async with self._lock:
            p = self.positions[symbol]
            close_qty = min(quantity or p["quantity"], p["quantity"])
            quote = await self.get_market_price(symbol)
            exit_price = quote.bid if p["direction"] == Direction.LONG else quote.ask
            pnl = (
                (exit_price - p["entry"])
                if p["direction"] == Direction.LONG
                else (p["entry"] - exit_price)
            ) * close_qty
            proceeds = p["entry"] * close_qty + pnl
            fee = (abs(exit_price * close_qty) * self.fee_rate).quantize(D("0.01"))
            self.cash += proceeds - fee
            p["quantity"] -= close_qty
            trade = {
                "symbol": symbol,
                "direction": p["direction"],
                "quantity": close_qty,
                "entry": p["entry"],
                "exit": exit_price,
                "pnl": (pnl - fee).quantize(D("0.01")),
                "fees": fee,
                "closed_at": datetime.now(UTC),
            }
            self.trades.append(trade)
            if p["quantity"] <= 0:
                del self.positions[symbol]
            return trade

    async def get_order_status(self, order_id: str):
        return self.orders[order_id]

    async def process_price_tick(self, symbol: str, price: Decimal):
        self.set_price(symbol, price)
        p = self.positions.get(symbol)
        if not p:
            return None
        stopped = (
            price <= p["stop_loss"] if p["direction"] == Direction.LONG else price >= p["stop_loss"]
        )
        targeted = (
            price >= p["take_profit"]
            if p["direction"] == Direction.LONG
            else price <= p["take_profit"]
        )
        if stopped or targeted:
            trade = await self.close_position(symbol)
            trade["exit_reason"] = "STOPPED_OUT" if stopped else "TAKE_PROFIT"
            return trade
        return None

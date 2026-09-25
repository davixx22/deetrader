from collections.abc import Callable
from decimal import Decimal
from typing import TypedDict

D = Decimal


class BacktestTrade(TypedDict):
    side: str
    entry: D
    exit: D
    quantity: D
    fees: D
    pnl: D


class BacktestEngine:
    def __init__(
        self,
        starting_equity: D,
        fee_rate: D = D("0.001"),
        spread_bps: D = D("4"),
        slippage_bps: D = D("3"),
    ):
        self.starting_equity = starting_equity
        self.fee_rate = fee_rate
        self.spread_bps = spread_bps
        self.slippage_bps = slippage_bps

    def run(
        self, bars: list[dict], signal: Callable[[list[dict]], str | None], risk_percent: D = D("1")
    ) -> dict:
        equity = self.starting_equity
        peak = equity
        max_drawdown = D("0")
        trades: list[BacktestTrade] = []
        for index in range(20, len(bars) - 1):
            side = signal(bars[: index + 1])
            if side not in {"LONG", "SHORT"}:
                continue
            entry = D(str(bars[index]["close"]))
            exit_price = D(str(bars[index + 1]["close"]))
            spread = entry * self.spread_bps / D("10000")
            slip = entry * self.slippage_bps / D("10000")
            adjusted_entry = (
                entry + spread / 2 + slip if side == "LONG" else entry - spread / 2 - slip
            )
            risk_per_unit = max(
                D(str(bars[index].get("atr", entry * D("0.02")))), entry * D("0.005")
            )
            quantity = equity * risk_percent / D("100") / risk_per_unit
            gross = (
                (exit_price - adjusted_entry) * quantity
                if side == "LONG"
                else (adjusted_entry - exit_price) * quantity
            )
            fees = (adjusted_entry + exit_price) * quantity * self.fee_rate
            pnl = gross - fees
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
            trades.append(
                {
                    "side": side,
                    "entry": adjusted_entry,
                    "exit": exit_price,
                    "quantity": quantity,
                    "fees": fees,
                    "pnl": pnl,
                }
            )
        wins = [trade for trade in trades if trade["pnl"] > 0]
        losses = [trade for trade in trades if trade["pnl"] < 0]
        gross_win = sum((trade["pnl"] for trade in wins), D("0"))
        gross_loss = abs(sum((trade["pnl"] for trade in losses), D("0")))
        return {
            "trades": trades,
            "pnl": equity - self.starting_equity,
            "equity": equity,
            "win_rate": D(len(wins)) / D(len(trades)) * 100 if trades else D("0"),
            "profit_factor": gross_win / gross_loss if gross_loss else D("0"),
            "drawdown": max_drawdown,
            "expectancy": (equity - self.starting_equity) / len(trades) if trades else D("0"),
        }

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal

from app.schemas.trading import AccountRiskState, Direction, RiskConfig, RiskDecision, TradeProposal

D = Decimal


class RiskEngine:
    def __init__(self, config: RiskConfig, max_price_age_seconds: int = 15):
        self.config = config
        self.max_price_age_seconds = max_price_age_seconds

    def reject(self, reason: str, warnings: list[str] | None = None) -> RiskDecision:
        return RiskDecision(approved=False, reason=reason, warnings=warnings or [])

    def validate_trade(
        self, proposal: TradeProposal, account: AccountRiskState, now: datetime | None = None
    ) -> RiskDecision:
        now = now or datetime.now(UTC)
        timestamp = (
            proposal.price_timestamp
            if proposal.price_timestamp.tzinfo
            else proposal.price_timestamp.replace(tzinfo=UTC)
        )
        if account.kill_switch:
            return self.reject("KILL_SWITCH_ACTIVE")
        if (now - timestamp).total_seconds() > self.max_price_age_seconds:
            return self.reject("STALE_MARKET_DATA")
        if proposal.symbol in self.config.blocked_symbols:
            return self.reject("SYMBOL_BLOCKED")
        if self.config.allowed_symbols and proposal.symbol not in self.config.allowed_symbols:
            return self.reject("SYMBOL_NOT_ALLOWED")
        if proposal.direction == Direction.SHORT and not self.config.allow_short:
            return self.reject("SHORT_DISABLED")
        if proposal.direction == Direction.LONG and not self.config.allow_long:
            return self.reject("LONG_DISABLED")
        if proposal.symbol in account.existing_symbols and not self.config.allow_averaging_down:
            return self.reject("AVERAGING_DOWN_DISABLED")
        if account.open_positions >= self.config.max_open_positions:
            return self.reject("MAX_OPEN_POSITIONS")
        if account.trades_today >= self.config.max_trades_per_day:
            return self.reject("MAX_TRADES_PER_DAY")
        if account.consecutive_losses >= self.config.maximum_consecutive_losses:
            return self.reject("MAX_CONSECUTIVE_LOSSES")
        daily_limit = (
            self.config.max_daily_loss
            or account.equity * self.config.max_daily_loss_percent / D("100")
        )
        if account.daily_pnl <= -daily_limit:
            return self.reject("MAX_DAILY_LOSS")
        if account.weekly_pnl <= -self.config.max_weekly_loss:
            return self.reject("MAX_WEEKLY_LOSS")
        risk_per_unit = abs(proposal.entry - proposal.stop_loss)
        reward_per_unit = abs(proposal.take_profit - proposal.entry)
        rr = reward_per_unit / risk_per_unit
        if rr < self.config.minimum_risk_reward:
            return self.reject("MINIMUM_RISK_REWARD")
        risk_budget = account.equity * self.config.max_risk_per_trade_percent / D("100")
        if self.config.max_risk_per_trade_amount is not None:
            risk_budget = min(risk_budget, self.config.max_risk_per_trade_amount)
        quantity = (risk_budget / risk_per_unit).quantize(D("0.0001"), rounding=ROUND_DOWN)
        max_notional = min(
            self.config.max_position_size,
            account.buying_power,
            self.config.max_total_exposure - account.total_exposure,
        )
        quantity = min(
            quantity, (max_notional / proposal.entry).quantize(D("0.0001"), rounding=ROUND_DOWN)
        )
        if quantity <= 0:
            return self.reject("NO_CAPACITY")
        actual_risk = (quantity * risk_per_unit).quantize(D("0.01"))
        reward = (quantity * reward_per_unit).quantize(D("0.01"))
        warnings = []
        if account.daily_pnl < -(daily_limit * D("0.75")):
            warnings.append("DAILY_LOSS_LIMIT_NEAR")
        return RiskDecision(
            approved=True,
            reason="APPROVED",
            calculated_position_size=quantity,
            risk_amount=actual_risk,
            risk_percent=(actual_risk / account.equity * 100).quantize(D("0.01")),
            expected_reward=reward,
            risk_reward_ratio=rr.quantize(D("0.01")),
            warnings=warnings,
        )

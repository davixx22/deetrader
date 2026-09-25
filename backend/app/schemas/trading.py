from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"
    COVER = "COVER"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TradeState(StrEnum):
    DISCOVERED = "DISCOVERED"
    ANALYZING = "ANALYZING"
    PROPOSED = "PROPOSED"
    RISK_REJECTED = "RISK_REJECTED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    STOPPED_OUT = "STOPPED_OUT"
    TAKE_PROFIT = "TAKE_PROFIT"
    MANUALLY_CLOSED = "MANUALLY_CLOSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class MarketQuote(BaseModel):
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    shortable: bool = True


class TradeProposal(BaseModel):
    id: str
    symbol: str = Field(pattern=r"^[A-Z0-9.\-]{1,15}$")
    direction: Direction
    entry: Decimal = Field(gt=0)
    stop_loss: Decimal = Field(gt=0)
    take_profit: Decimal = Field(gt=0)
    strategy: str
    strategy_confidence: int = Field(ge=0, le=100)
    price_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    environment: str = "paper"

    @model_validator(mode="after")
    def validate_levels(self):
        if self.direction == Direction.LONG and not (
            self.stop_loss < self.entry < self.take_profit
        ):
            raise ValueError("LONG requires stop < entry < target")
        if self.direction == Direction.SHORT and not (
            self.take_profit < self.entry < self.stop_loss
        ):
            raise ValueError("SHORT requires target < entry < stop")
        return self


class RiskConfig(BaseModel):
    starting_capital: Decimal = Decimal("500")
    currency: str = "CZK"
    max_risk_per_trade_percent: Decimal = Decimal("5")
    max_risk_per_trade_amount: Decimal | None = None
    max_daily_loss: Decimal | None = None
    max_daily_loss_percent: Decimal = Decimal("10")
    max_weekly_loss: Decimal = Decimal("100")
    max_open_positions: int = 1
    max_total_exposure: Decimal = Decimal("500")
    max_position_size: Decimal = Decimal("250")
    minimum_risk_reward: Decimal = Decimal("2")
    maximum_leverage: Decimal = Decimal("2")
    allow_short: bool = True
    allow_long: bool = True
    allow_averaging_down: bool = False
    allowed_symbols: set[str] = Field(default_factory=set)
    blocked_symbols: set[str] = Field(default_factory=set)
    max_trades_per_day: int = 5
    cooldown_after_loss: int = 900
    maximum_consecutive_losses: int = 3


class AccountRiskState(BaseModel):
    equity: Decimal
    available_cash: Decimal
    buying_power: Decimal
    daily_pnl: Decimal = Decimal("0")
    weekly_pnl: Decimal = Decimal("0")
    open_positions: int = 0
    total_exposure: Decimal = Decimal("0")
    trades_today: int = 0
    consecutive_losses: int = 0
    kill_switch: bool = False
    existing_symbols: set[str] = Field(default_factory=set)


class RiskDecision(BaseModel):
    approved: bool
    reason: str
    calculated_position_size: Decimal = Decimal("0")
    risk_amount: Decimal = Decimal("0")
    risk_percent: Decimal = Decimal("0")
    expected_reward: Decimal = Decimal("0")
    risk_reward_ratio: Decimal = Decimal("0")
    warnings: list[str] = Field(default_factory=list)


class AIAnalysis(BaseModel):
    decision: str = Field(pattern="^(approve|reject|neutral)$")
    confidence: int = Field(ge=0, le=100)
    reasoning_summary: str = Field(max_length=2000)
    risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    invalidations: list[str] = Field(default_factory=list)


class OrderRequest(BaseModel):
    proposal: TradeProposal
    idempotency_key: str = Field(min_length=8, max_length=100)
    user_approved: bool = False

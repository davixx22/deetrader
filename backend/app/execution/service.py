from datetime import UTC, datetime

from app.brokers.base import BrokerAdapter
from app.risk.engine import RiskEngine
from app.schemas.trading import AccountRiskState, Direction, OrderRequest


class ExecutionEngine:
    def __init__(
        self,
        broker: BrokerAdapter,
        risk: RiskEngine,
        trading_mode: str = "paper",
        execution_mode: str = "manual",
        live_enabled: bool = False,
        max_price_age_seconds: int = 15,
    ):
        self.broker = broker
        self.risk = risk
        self.trading_mode = trading_mode
        self.execution_mode = execution_mode
        self.live_enabled = live_enabled
        self.max_price_age_seconds = max_price_age_seconds
        self._keys: dict[str, dict] = {}

    async def execute(
        self,
        request: OrderRequest,
        account: AccountRiskState,
        auto_threshold: int = 75,
        ai_confidence: int | None = None,
    ):
        if request.idempotency_key in self._keys:
            return self._keys[request.idempotency_key]
        if request.proposal.environment != self.trading_mode:
            raise RuntimeError("ENVIRONMENT_MISMATCH")
        if self.trading_mode == "live" and not self.live_enabled:
            raise RuntimeError("LIVE_TRADING_DISABLED")
        if self.execution_mode in {"manual", "semi_auto"} and not request.user_approved:
            raise RuntimeError("USER_APPROVAL_REQUIRED")
        if self.execution_mode == "auto" and request.proposal.strategy_confidence < auto_threshold:
            raise RuntimeError("STRATEGY_CONFIDENCE_TOO_LOW")
        decision = self.risk.validate_trade(request.proposal, account, datetime.now(UTC))
        if not decision.approved:
            raise RuntimeError(decision.reason)
        quote = await self.broker.get_market_price(request.proposal.symbol)
        if (datetime.now(UTC) - quote.timestamp).total_seconds() > self.max_price_age_seconds:
            raise RuntimeError("STALE_MARKET_DATA")
        if (
            request.proposal.direction == Direction.SHORT
            and not await self.broker.get_short_availability(request.proposal.symbol)
        ):
            raise RuntimeError("SHORT_UNAVAILABLE")
        if account.buying_power < request.proposal.entry * decision.calculated_position_size:
            raise RuntimeError("INSUFFICIENT_BUYING_POWER")
        order = await self.broker.submit_bracket_order(request, decision.calculated_position_size)
        self._keys[request.idempotency_key] = order
        return order

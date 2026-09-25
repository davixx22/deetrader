from decimal import Decimal as D

import pytest

from app.ai.analyzer import AIAnalyzer
from app.brokers.paper import PaperBrokerAdapter
from app.execution.service import ExecutionEngine
from app.risk.engine import RiskEngine
from app.schemas.trading import AccountRiskState, Direction, OrderRequest, RiskConfig, TradeProposal


@pytest.mark.asyncio
async def test_execution_is_idempotent():
    broker = PaperBrokerAdapter(D("1000"))
    await broker.connect()
    broker.set_price("NVDA", D("100"))
    engine = ExecutionEngine(
        broker, RiskEngine(RiskConfig(max_position_size=D("1000"))), execution_mode="manual"
    )
    proposal = TradeProposal(
        id="p1",
        symbol="NVDA",
        direction=Direction.LONG,
        entry=D("100"),
        stop_loss=D("95"),
        take_profit=D("110"),
        strategy="test",
        strategy_confidence=90,
    )
    request = OrderRequest(proposal=proposal, idempotency_key="dedupe-key", user_approved=True)
    account = AccountRiskState(equity=D("1000"), available_cash=D("1000"), buying_power=D("2000"))
    one = await engine.execute(request, account)
    two = await engine.execute(request, account)
    assert one["id"] == two["id"]


@pytest.mark.asyncio
async def test_malformed_ai_response_fails_closed():
    with pytest.raises(ValueError, match="AI_MALFORMED_RESPONSE"):
        await AIAnalyzer(True).analyze({"provider_response": "not-json"})


@pytest.mark.asyncio
async def test_ai_outage_does_not_block_pipeline():
    result = await AIAnalyzer(False).analyze({})
    assert result.decision == "neutral" and result.confidence == 0

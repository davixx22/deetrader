from decimal import Decimal as D

import pytest

from app.brokers.paper import PaperBrokerAdapter
from app.schemas.trading import Direction, OrderRequest, TradeProposal


def request(key="unique-order"):
    return OrderRequest(
        idempotency_key=key,
        user_approved=True,
        proposal=TradeProposal(
            id="p1",
            symbol="AMD",
            direction=Direction.LONG,
            entry=D("100"),
            stop_loss=D("95"),
            take_profit=D("110"),
            strategy="test",
            strategy_confidence=90,
        ),
    )


@pytest.mark.asyncio
async def test_unconfigured_account_starts_empty_and_rejects_orders():
    broker = PaperBrokerAdapter()
    await broker.connect()
    account = await broker.get_account()
    assert account["configured"] is False
    assert account["cash"] == D("0")
    with pytest.raises(RuntimeError, match="PAPER_ACCOUNT_NOT_CONFIGURED"):
        await broker.submit_order(request("unconfigured-order"), D("1"))


@pytest.mark.asyncio
async def test_paper_account_can_be_configured_once_without_fake_activity():
    broker = PaperBrokerAdapter()
    await broker.connect()
    account = await broker.configure_account(D("25000"))
    assert account["configured"] is True
    assert account["cash"] == D("25000")
    assert await broker.get_positions() == []
    assert await broker.get_orders() == []
    assert await broker.get_trade_history() == []


@pytest.mark.asyncio
async def test_bracket_fill_stop_and_duplicate_protection():
    broker = PaperBrokerAdapter(starting_cash=D("1000"), slippage_bps=D("0"), spread_bps=D("0"))
    await broker.connect()
    broker.set_price("AMD", D("100"))
    first = await broker.submit_bracket_order(request(), D("2"))
    second = await broker.submit_bracket_order(request(), D("2"))
    assert first["id"] == second["id"] and len(await broker.get_orders()) == 1
    trade = await broker.process_price_tick("AMD", D("94"))
    assert (
        trade["exit_reason"] == "STOPPED_OUT"
        and trade["pnl"] < 0
        and not await broker.get_positions()
    )


@pytest.mark.asyncio
async def test_take_profit_and_partial_close():
    broker = PaperBrokerAdapter(starting_cash=D("1000"), slippage_bps=D("0"), spread_bps=D("0"))
    await broker.connect()
    broker.set_price("AMD", D("100"))
    await broker.submit_bracket_order(request("another-key"), D("2"))
    trade = await broker.process_price_tick("AMD", D("111"))
    assert trade["exit_reason"] == "TAKE_PROFIT" and trade["pnl"] > 0

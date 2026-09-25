import json
from decimal import Decimal as D

import httpx
import pytest

from app.brokers.ibkr import IBKRAPIError, IBKRBrokerAdapter
from app.schemas.trading import Direction, OrderRequest, TradeProposal


def proposal_request() -> OrderRequest:
    return OrderRequest(
        idempotency_key="ibkr-bracket-1",
        user_approved=True,
        proposal=TradeProposal(
            id="proposal-ibkr",
            symbol="AAPL",
            direction=Direction.LONG,
            entry=D("200"),
            stop_loss=D("195"),
            take_profit=D("210"),
            strategy="test",
            strategy_confidence=90,
        ),
    )


def mock_transport(captured: list[dict] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/sso/validate"):
            return httpx.Response(200, json={"RESULT": True, "LOGIN_TYPE": 2})
        if path.endswith("/portfolio/accounts"):
            return httpx.Response(200, json=[{"accountId": "DU123456"}])
        if path.endswith("/iserver/accounts"):
            return httpx.Response(
                200, json={"accounts": ["DU123456"], "selectedAccount": "DU123456"}
            )
        if path.endswith("/summary"):
            return httpx.Response(
                200,
                json={
                    "totalCashValue": 10000,
                    "netLiquidationValue": 12000,
                    "buyingPower": 24000,
                    "availableFunds": 9000,
                    "initialMargin": 2000,
                    "maintenanceMargin": 1800,
                    "currency": "USD",
                },
            )
        if path.endswith("/positions"):
            return httpx.Response(
                200,
                json=[
                    {
                        "description": "AAPL",
                        "conid": 265598,
                        "position": 2,
                        "avgPrice": 190,
                        "marketPrice": 200,
                        "marketValue": 400,
                        "realizedPnl": 0,
                        "unrealizedPnl": 20,
                        "currency": "USD",
                    }
                ],
            )
        if path.endswith("/secdef/search"):
            return httpx.Response(200, json=[{"symbol": "AAPL", "conid": 265598}])
        if path.endswith("/marketdata/snapshot"):
            return httpx.Response(200, json=[{"31": "200.10", "84": "200.00", "86": "200.20"}])
        if path.endswith("/contract/rules"):
            return httpx.Response(200, json={"canShort": True})
        if path.endswith("/orders") and request.method == "POST":
            if captured is not None:
                captured.append(json.loads(request.content))
            return httpx.Response(200, json=[{"order_id": "987654", "order_status": "Submitted"}])
        if path.endswith("/orders"):
            return httpx.Response(200, json={"orders": []})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def adapter(*, submit: bool = False, captured: list[dict] | None = None):
    client = httpx.AsyncClient(
        base_url="https://localhost:5000/v1/api", transport=mock_transport(captured)
    )
    return IBKRBrokerAdapter(
        base_url="https://localhost:5000/v1/api",
        client=client,
        order_submission_enabled=submit,
    )


@pytest.mark.asyncio
async def test_ibkr_connect_account_positions_and_quote():
    broker = adapter()
    await broker.connect()
    account = await broker.get_account()
    positions = await broker.get_positions()
    quote = await broker.get_market_price("AAPL")
    assert account["equity"] == D("12000")
    assert positions[0]["unrealized_pnl"] == D("20")
    assert quote.bid == D("200.00") and quote.shortable
    await broker.client.aclose()


@pytest.mark.asyncio
async def test_ibkr_submission_requires_separate_interlock():
    broker = adapter()
    await broker.connect()
    with pytest.raises(IBKRAPIError, match="IBKR_ORDER_SUBMISSION_DISABLED"):
        await broker.submit_bracket_order(proposal_request(), D("1"))
    await broker.client.aclose()


@pytest.mark.asyncio
async def test_ibkr_bracket_preserves_parent_and_protective_children():
    captured: list[dict] = []
    broker = adapter(submit=True, captured=captured)
    await broker.connect()
    result = await broker.submit_bracket_order(proposal_request(), D("1"))
    orders = captured[0]["orders"]
    assert result["order_status"] == "Submitted"
    assert orders[0]["cOID"] == "ibkr-bracket-1"
    assert orders[1]["orderType"] == "STP" and orders[1]["parentId"] == orders[0]["cOID"]
    assert orders[2]["orderType"] == "LMT" and orders[2]["parentId"] == orders[0]["cOID"]
    await broker.client.aclose()

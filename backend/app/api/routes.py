import asyncio
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.ai.analyzer import AIAnalyzer
from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.brokers.factory import create_broker
from app.brokers.ibkr import IBKRBrokerAdapter
from app.brokers.paper import PaperBrokerAdapter
from app.core.config import get_settings
from app.execution.service import ExecutionEngine
from app.risk.engine import RiskEngine
from app.scanner.service import MarketScanner, MockMarketDataProvider
from app.schemas.trading import AccountRiskState, OrderRequest, RiskConfig, TradeProposal

router = APIRouter(prefix="/api/v1")
security = HTTPBearer(auto_error=False)
settings = get_settings()
broker = create_broker(settings)
routing_config: dict[str, object] = {
    "provider": settings.broker_provider,
    "environment": settings.trading_mode,
    "order_submission_enabled": settings.ibkr_order_submission_enabled
    if settings.broker_provider == "ibkr"
    else True,
}
risk_config = RiskConfig()
risk_engine = RiskEngine(risk_config, settings.max_price_age_seconds)
execution = ExecutionEngine(
    broker,
    risk_engine,
    settings.trading_mode,
    settings.execution_mode,
    settings.live_trading_enabled,
)
scanner = MarketScanner(MockMarketDataProvider())
ai = AIAnalyzer(settings.ai_provider != "disabled")
agent_counters: dict[str, int] = {
    "symbols_scanned": 0,
    "signals_found": 0,
    "rejected": 0,
    "approved": 0,
}
agent_state: dict[str, object] = {
    "state": "STOPPED",
    "operation": None,
    "kill_switch": False,
    "last_scan": None,
    "next_scan": None,
    "counters": agent_counters,
}
events: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)
event_history: deque[dict] = deque(maxlen=50)
admin_hash = hash_password(settings.admin_password.get_secret_value())


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Authentication required")
    try:
        return decode_access_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(401, "Invalid or expired token") from exc


async def emit(category: str, message: str, **context):
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "category": category,
        "message": message,
        "context": context,
    }
    if events.full():
        events.get_nowait()
    await events.put(event)
    event_history.appendleft(event)


@router.post("/auth/login")
async def login(payload: dict):
    if payload.get("email") != "admin@deetrader.local" or not verify_password(
        payload.get("password", ""), admin_hash
    ):
        raise HTTPException(401, "Invalid credentials")
    await emit("SYSTEM", "User logged in", user="admin@deetrader.local")
    return {"access_token": create_access_token("admin@deetrader.local"), "token_type": "bearer"}


async def account_state():
    account = await broker.get_account()
    positions = await broker.get_positions()
    trades = await broker.get_trade_history()
    exposure = sum(p["quantity"] * p["entry"] for p in positions)
    return AccountRiskState(
        equity=account["equity"],
        available_cash=account["cash"],
        buying_power=account["buying_power"],
        open_positions=len(positions),
        total_exposure=exposure,
        trades_today=len(trades),
        kill_switch=agent_state["kill_switch"],
        existing_symbols={p["symbol"] for p in positions},
    )


@router.get("/dashboard")
async def dashboard():
    account = await broker.get_account()
    positions = await broker.get_positions()
    trades = await broker.get_trade_history()
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    return {
        "account": account,
        "positions": positions,
        "today_pnl": sum((t["pnl"] for t in trades), Decimal()),
        "total_pnl": sum((Decimal(str(t.get("pnl", 0))) for t in trades), Decimal()),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "profit_factor": sum(t["pnl"] for t in wins)
        / abs(sum((t["pnl"] for t in losses), Decimal(-1)))
        if wins
        else 0,
        "agent": agent_state,
        "broker": {
            "provider": routing_config["provider"],
            "connected": getattr(broker, "connected", False),
        },
        "trading_mode": routing_config["environment"],
        "execution_mode": settings.execution_mode,
    }


@router.get("/account")
async def account():
    return await broker.get_account()


@router.get("/positions")
async def positions():
    return await broker.get_positions()


@router.get("/orders")
async def orders():
    return await broker.get_orders()


@router.get("/trades")
async def trades(environment: str = "paper"):
    return [
        trade
        for trade in await broker.get_trade_history()
        if trade.get("environment", settings.trading_mode) == environment
    ]


@router.get("/strategies")
async def strategies():
    return [
        {"name": n, "enabled": True}
        for n in [
            "momentum-short",
            "overextended-short",
            "breakdown-short",
            "mean-reversion",
            "volatility",
        ]
    ]


@router.post("/scanner")
async def run_scanner(payload: dict):
    symbols = payload.get(
        "symbols",
        [
            "AAPL", "MSFT", "NVDA", "AMD", "AMZN", "GOOGL", "META", "TSLA",
            "AVGO", "NFLX", "PLTR", "INTC", "CSCO", "ORCL", "CRM", "ADBE",
            "QCOM", "MU", "ARM", "SMCI", "JPM", "BAC", "V", "MA", "WMT",
            "COST", "KO", "DIS", "NKE", "UBER",
        ],
    )
    results = await scanner.scan(symbols, payload.get("filters", {}))
    agent_state["last_scan"] = datetime.now(UTC).isoformat()
    agent_counters["symbols_scanned"] += len(symbols)
    agent_counters["signals_found"] += len(results)
    await emit("SCANNER", "Scan completed", symbols=len(symbols), candidates=len(results))
    return results


@router.post("/paper/account")
async def configure_paper_account(payload: dict, user=Depends(current_user)):
    if not isinstance(broker, PaperBrokerAdapter):
        raise HTTPException(409, "PAPER_BROKER_NOT_SELECTED")
    try:
        starting_cash = Decimal(str(payload.get("starting_cash", "0")))
    except Exception as exc:
        raise HTTPException(400, "Invalid starting cash") from exc
    if starting_cash <= 0 or starting_cash > Decimal("1000000000"):
        raise HTTPException(400, "Starting cash must be between 0 and 1,000,000,000")
    reset = bool(payload.get("reset", False))
    if reset and payload.get("confirmation") != "RESET PAPER ACCOUNT":
        raise HTTPException(400, "Explicit reset confirmation required")
    try:
        account = await broker.configure_account(starting_cash, reset=reset)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    await emit("ACCOUNT", "Paper account configured", user=user, reset=reset)
    return account


@router.post("/risk/validate")
async def validate(proposal: TradeProposal):
    return risk_engine.validate_trade(proposal, await account_state())


@router.get("/risk")
async def get_risk():
    return risk_config


@router.put("/risk")
async def set_risk(value: RiskConfig, user=Depends(current_user)):
    global risk_config, risk_engine, execution
    before = risk_config.model_dump(mode="json")
    risk_config = value
    risk_engine = RiskEngine(value, settings.max_price_age_seconds)
    execution.risk = risk_engine
    await emit(
        "RISK",
        "Risk configuration changed",
        user=user,
        before=before,
        after=value.model_dump(mode="json"),
    )
    return value


@router.post("/orders")
async def submit_order(request: OrderRequest, user=Depends(current_user)):
    try:
        order = await execution.execute(request, await account_state())
        await emit("ORDER", "Order filled", order_id=order["id"], symbol=order["symbol"])
        return order
    except RuntimeError as exc:
        await emit("RISK", "Order blocked", reason=str(exc), proposal=request.proposal.id)
        raise HTTPException(409, str(exc)) from exc


@router.post("/positions/{symbol}/close")
async def close_position(symbol: str, user=Depends(current_user)):
    trade = await broker.close_position(symbol.upper())
    await emit("ORDER", "Position manually closed", symbol=symbol, user=user)
    return trade


@router.get("/agent")
async def get_agent():
    return agent_state


@router.post("/agent/{action}")
async def control_agent(action: str, user=Depends(current_user)):
    if action not in {"start", "pause", "stop"}:
        raise HTTPException(400, "Unknown action")
    if agent_state["kill_switch"] and action == "start":
        raise HTTPException(409, "KILL_SWITCH_ACTIVE")
    agent_state["state"] = {"start": "RUNNING", "pause": "PAUSED", "stop": "STOPPED"}[action]
    await emit("SYSTEM", f"Agent {action}", user=user)
    return agent_state


@router.post("/agent/emergency-stop")
async def emergency_stop(payload: dict, user=Depends(current_user)):
    agent_state.update(state="STOPPED", kill_switch=True, operation=None)
    await emit("RISK", "Emergency stop activated", user=user)
    if payload.get("cancel_pending"):
        for order in await broker.get_orders():
            if order["status"] not in {"FILLED", "CANCELLED"}:
                await broker.cancel_order(order["id"])
    if payload.get("close_positions"):
        if payload.get("confirmation") != "CLOSE ALL POSITIONS":
            raise HTTPException(400, "Separate close confirmation required")
        for position in list(await broker.get_positions()):
            await broker.close_position(position["symbol"])
    return agent_state


@router.get("/analytics")
async def analytics():
    trades = await broker.get_trade_history()
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    gross_win = sum((t["pnl"] for t in wins), Decimal())
    gross_loss = abs(sum((t["pnl"] for t in losses), Decimal()))
    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "average_win": gross_win / len(wins) if wins else 0,
        "average_loss": gross_loss / len(losses) if losses else 0,
        "profit_factor": gross_win / gross_loss if gross_loss else 0,
        "expectancy": sum((t["pnl"] for t in trades), Decimal()) / len(trades) if trades else 0,
    }


@router.get("/broker")
async def broker_info():
    account = await broker.get_account()
    return {
        "provider": routing_config["provider"],
        "connection_state": "CONNECTED" if getattr(broker, "connected", False) else "DISCONNECTED",
        "account_id": "••••••••••",
        "environment": routing_config["environment"],
        "order_submission_enabled": routing_config["order_submission_enabled"],
        **account,
    }


@router.post("/broker/connect")
async def connect_ibkr(payload: dict, user=Depends(current_user)):
    global broker, execution
    method = payload.get("method", "gateway")
    if method not in {"gateway", "oauth"}:
        raise HTTPException(400, "Unsupported IBKR connection method")
    base_url = str(payload.get("base_url", "")).strip().rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise HTTPException(400, "A valid IBKR gateway URL is required")
    environment = payload.get("environment", "paper")
    if environment not in {"paper", "live"}:
        raise HTTPException(400, "Environment must be paper or live")
    token = str(payload.get("access_token", "")).strip() or None
    if method == "oauth" and not token:
        raise HTTPException(400, "OAuth access token is required")
    order_submission_enabled = bool(payload.get("order_submission_enabled", False))
    if environment == "live" and order_submission_enabled:
        if payload.get("live_confirmation") != "ENABLE LIVE IBKR":
            raise HTTPException(400, "Explicit LIVE confirmation is required")
    candidate = IBKRBrokerAdapter(
        base_url=base_url,
        account_id=str(payload.get("account_id", "")).strip() or None,
        access_token=token,
        verify_tls=bool(payload.get("verify_tls", method == "oauth")),
        timeout_seconds=settings.ibkr_timeout_seconds,
        order_submission_enabled=order_submission_enabled,
        expected_environment=environment,
        order_payload_style=settings.ibkr_order_payload_style,
    )
    try:
        await candidate.connect()
        account = await candidate.get_account()
    except Exception as exc:
        await candidate.disconnect()
        raise HTTPException(502, f"IBKR connection failed: {exc}") from exc
    broker = candidate
    execution = ExecutionEngine(
        broker,
        risk_engine,
        environment,
        settings.execution_mode,
        environment == "live" and order_submission_enabled,
        settings.max_price_age_seconds,
    )
    routing_config.update(
        provider="ibkr",
        environment=environment,
        order_submission_enabled=order_submission_enabled,
    )
    await emit("BROKER", "IBKR connected for current server session", user=user, method=method)
    return {
        "provider": "ibkr",
        "connection_state": "CONNECTED",
        "environment": environment,
        "order_submission_enabled": order_submission_enabled,
        "account_id": "••••" + str(account.get("account_id", ""))[-4:],
        "currency": account.get("currency"),
    }


@router.post("/broker/reconnect")
async def reconnect_broker(user=Depends(current_user)):
    await broker.connect()
    await emit("BROKER", "Broker connection refreshed", user=user)
    return {"connected": getattr(broker, "connected", False)}


@router.post("/broker/ibkr/replies/{reply_id}")
async def confirm_ibkr_reply(reply_id: str, payload: dict, user=Depends(current_user)):
    if not isinstance(broker, IBKRBrokerAdapter):
        raise HTTPException(409, "IBKR_NOT_SELECTED")
    if payload.get("confirmation") != "CONFIRM IBKR ORDER":
        raise HTTPException(400, "Explicit IBKR order confirmation required")
    result = await broker.confirm_order_reply(reply_id)
    await emit("ORDER", "IBKR warning reply confirmed", user=user, reply_id=reply_id)
    return result


@router.get("/settings")
async def get_app_settings():
    return {
        "trading_mode": settings.trading_mode,
        "execution_mode": settings.execution_mode,
        "live_trading_enabled": settings.live_trading_enabled,
        "broker_provider": settings.broker_provider,
        "ai_provider": settings.ai_provider,
        "market_data_provider": settings.market_data_provider,
    }


@router.get("/notifications")
async def notifications():
    return list(event_history)


@router.get("/audit")
async def audit(user=Depends(current_user)):
    return []


@router.websocket("/ws/{channel}")
async def websocket_stream(ws: WebSocket, channel: str):
    if channel not in {"market", "positions", "agent", "logs"}:
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            if channel == "logs":
                payload = await asyncio.wait_for(events.get(), timeout=10)
            elif channel == "positions":
                payload = {"positions": await broker.get_positions()}
            elif channel == "agent":
                payload = agent_state
            else:
                payload = {"heartbeat": datetime.now(UTC).isoformat()}
            await ws.send_json(payload)
            await asyncio.sleep(1)
    except (WebSocketDisconnect, TimeoutError):
        if ws.client_state.name == "CONNECTED":
            await ws.send_json({"heartbeat": datetime.now(UTC).isoformat()})

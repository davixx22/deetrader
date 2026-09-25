import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import httpx

from app.brokers.base import BrokerAdapter
from app.schemas.trading import Direction, MarketQuote, OrderRequest

D = Decimal


class IBKRAPIError(RuntimeError):
    """Sanitized IBKR transport or API error safe for logs and API responses."""


class IBKRBrokerAdapter(BrokerAdapter):
    """IBKR Web API adapter for Client Portal Gateway or OAuth 2.0 sessions.

    Authentication is intentionally external. Individual users authenticate the
    Client Portal Gateway in its browser; OAuth deployments inject a short-lived
    access token. The adapter never stores credentials and never confirms IBKR
    warning/reply messages automatically.
    """

    def __init__(
        self,
        base_url: str,
        account_id: str | None = None,
        access_token: str | None = None,
        verify_tls: bool = True,
        timeout_seconds: float = 10,
        order_submission_enabled: bool = False,
        expected_environment: Literal["paper", "live"] = "paper",
        order_payload_style: Literal["orders_object", "array"] = "orders_object",
        client: httpx.AsyncClient | None = None,
    ):
        headers = {"Accept": "application/json", "User-Agent": "DeeTrader/0.2"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        self.client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            verify=verify_tls,
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._owns_client = client is None
        self.account_id = account_id
        self.order_submission_enabled = order_submission_enabled
        self.expected_environment = expected_environment
        self.order_payload_style = order_payload_style
        self.connected = False
        self._conids: dict[str, int] = {}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self.client.request(method, path, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            self.connected = False
            raise IBKRAPIError("IBKR_API_UNAVAILABLE") from exc
        if response.status_code == 401:
            self.connected = False
            raise IBKRAPIError("IBKR_SESSION_UNAUTHORIZED")
        if response.status_code == 429:
            raise IBKRAPIError("IBKR_RATE_LIMITED")
        if response.is_error:
            raise IBKRAPIError(f"IBKR_HTTP_{response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise IBKRAPIError("IBKR_INVALID_RESPONSE") from exc

    @staticmethod
    def _validation_value(payload: dict[str, Any], key: str) -> Any:
        value = payload.get("success", {}).get("value", payload)
        return value.get(key) if isinstance(value, dict) else None

    async def connect(self) -> None:
        validation = await self._request("GET", "/sso/validate")
        if not self._validation_value(validation, "RESULT"):
            raise IBKRAPIError("IBKR_SESSION_NOT_AUTHENTICATED")
        login_type = self._validation_value(validation, "LOGIN_TYPE")
        if login_type is None:
            login_type = self._validation_value(validation, "loginType")
        expected_login_type = 2 if self.expected_environment == "paper" else 1
        if login_type is not None and int(login_type) != expected_login_type:
            raise IBKRAPIError("IBKR_ACCOUNT_ENVIRONMENT_MISMATCH")

        portfolio_accounts = await self._request("GET", "/portfolio/accounts")
        trading_accounts = await self._request("GET", "/iserver/accounts")
        available = {
            str(item.get("accountId") or item.get("id"))
            for item in portfolio_accounts
            if item.get("accountId") or item.get("id")
        }
        available.update(str(value) for value in trading_accounts.get("accounts", []))
        if self.account_id and self.account_id not in available:
            raise IBKRAPIError("IBKR_ACCOUNT_NOT_AVAILABLE")
        if not self.account_id:
            selected = trading_accounts.get("selectedAccount")
            self.account_id = str(selected or next(iter(available), ""))
        if not self.account_id:
            raise IBKRAPIError("IBKR_NO_TRADING_ACCOUNT")
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False
        if self._owns_client:
            await self.client.aclose()

    async def keepalive(self) -> None:
        self._require_connection()
        payload = await self._request("POST", "/tickle")
        authenticated = payload.get("iserver", {}).get("authStatus", {}).get("authenticated")
        if authenticated is False:
            self.connected = False
            raise IBKRAPIError("IBKR_BROKERAGE_SESSION_EXPIRED")

    def _require_connection(self) -> str:
        if not self.connected or not self.account_id:
            raise IBKRAPIError("IBKR_DISCONNECTED")
        return self.account_id

    async def get_account(self) -> dict[str, Any]:
        account_id = self._require_connection()
        summary = await self._request("GET", f"/iserver/account/{account_id}/summary")
        return {
            "account_id": account_id,
            "cash": D(str(summary.get("totalCashValue", 0))),
            "equity": D(str(summary.get("netLiquidationValue", 0))),
            "buying_power": D(str(summary.get("buyingPower", 0))),
            "available_funds": D(str(summary.get("availableFunds", 0))),
            "initial_margin": D(str(summary.get("initialMargin", 0))),
            "maintenance_margin": D(str(summary.get("maintenanceMargin", 0))),
            "currency": summary.get("currency", "BASE"),
        }

    async def get_positions(self) -> list[dict[str, Any]]:
        account_id = self._require_connection()
        rows = await self._request("GET", f"/portfolio2/{account_id}/positions")
        return [
            {
                "symbol": row.get("description") or row.get("contractDesc"),
                "conid": row.get("conid"),
                "direction": Direction.LONG
                if D(str(row.get("position", 0))) >= 0
                else Direction.SHORT,
                "quantity": abs(D(str(row.get("position", 0)))),
                "entry": D(str(row.get("avgPrice") or row.get("avgCost") or 0)),
                "market_price": D(str(row.get("marketPrice") or row.get("mktPrice") or 0)),
                "market_value": D(str(row.get("marketValue") or row.get("mktValue") or 0)),
                "realized_pnl": D(str(row.get("realizedPnl", 0))),
                "unrealized_pnl": D(str(row.get("unrealizedPnl", 0))),
                "currency": row.get("currency"),
            }
            for row in rows
            if D(str(row.get("position", 0))) != 0
        ]

    async def get_orders(self) -> list[dict[str, Any]]:
        self._require_connection()
        payload = await self._request("GET", "/iserver/account/orders")
        return payload.get("orders", payload if isinstance(payload, list) else [])

    async def _resolve_conid(self, symbol: str) -> int:
        symbol = symbol.upper()
        if symbol in self._conids:
            return self._conids[symbol]
        payload = await self._request(
            "POST", "/iserver/secdef/search", json={"symbol": symbol, "secType": "STK"}
        )
        matches = [item for item in payload if item.get("symbol", "").upper() == symbol]
        stocks = [item for item in matches if item.get("sections") or item.get("companyHeader")]
        selected = stocks or matches
        if not selected or not selected[0].get("conid"):
            raise IBKRAPIError("IBKR_CONTRACT_NOT_FOUND")
        conid = int(selected[0]["conid"])
        self._conids[symbol] = conid
        return conid

    @staticmethod
    def _price(value: Any) -> D:
        cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
        if not cleaned:
            raise IBKRAPIError("IBKR_MARKET_DATA_UNAVAILABLE")
        return D(cleaned)

    async def get_market_price(self, symbol: str) -> MarketQuote:
        self._require_connection()
        conid = await self._resolve_conid(symbol)
        payload = await self._request(
            "GET",
            "/iserver/marketdata/snapshot",
            params={"conids": str(conid), "fields": "31,84,86"},
        )
        if not payload:
            raise IBKRAPIError("IBKR_MARKET_DATA_UNAVAILABLE")
        row = payload[0]
        last = self._price(row.get("31"))
        bid = self._price(row.get("84", last))
        ask = self._price(row.get("86", last))
        updated = row.get("_updated")
        timestamp = (
            datetime.fromtimestamp(int(updated) / 1000, UTC) if updated else datetime.now(UTC)
        )
        return MarketQuote(
            symbol=symbol.upper(),
            bid=bid,
            ask=ask,
            last=last,
            timestamp=timestamp,
            shortable=await self.get_short_availability(symbol),
        )

    async def get_short_availability(self, symbol: str) -> bool:
        self._require_connection()
        conid = await self._resolve_conid(symbol)
        rules = await self._request(
            "GET", "/iserver/contract/rules", params={"conid": conid, "isBuy": "false"}
        )
        return bool(rules.get("canShort", False))

    async def get_buying_power(self) -> D:
        return D(str((await self.get_account())["buying_power"]))

    def _require_submission(self) -> str:
        account_id = self._require_connection()
        if not self.order_submission_enabled:
            raise IBKRAPIError("IBKR_ORDER_SUBMISSION_DISABLED")
        return account_id

    async def _submit_payload(self, orders: list[dict[str, Any]]) -> dict[str, Any]:
        account_id = self._require_submission()
        body: Any = {"orders": orders} if self.order_payload_style == "orders_object" else orders
        response = await self._request("POST", f"/iserver/account/{account_id}/orders", json=body)
        first = response[0] if isinstance(response, list) and response else response
        if isinstance(first, dict) and first.get("id") and first.get("message"):
            return {
                "status": "AWAITING_IBKR_CONFIRMATION",
                "reply_id": str(first["id"]),
                "messages": first.get("message", []),
            }
        return first

    async def submit_order(self, request: OrderRequest, quantity: D) -> dict[str, Any]:
        account_id = self._require_submission()
        conid = await self._resolve_conid(request.proposal.symbol)
        side = "BUY" if request.proposal.direction == Direction.LONG else "SELL"
        return await self._submit_payload(
            [
                {
                    "acctId": account_id,
                    "conid": conid,
                    "cOID": request.idempotency_key,
                    "orderType": "MKT",
                    "side": side,
                    "tif": "DAY",
                    "quantity": float(quantity),
                    "outsideRTH": False,
                }
            ]
        )

    async def submit_bracket_order(self, request: OrderRequest, quantity: D) -> dict[str, Any]:
        account_id = self._require_submission()
        conid = await self._resolve_conid(request.proposal.symbol)
        parent = request.idempotency_key
        entry_side = "BUY" if request.proposal.direction == Direction.LONG else "SELL"
        exit_side = "SELL" if entry_side == "BUY" else "BUY"
        common = {
            "acctId": account_id,
            "conid": conid,
            "listingExchange": "SMART",
            "tif": "GTC",
            "quantity": float(quantity),
            "outsideRTH": False,
        }
        return await self._submit_payload(
            [
                {**common, "cOID": parent, "orderType": "MKT", "side": entry_side},
                {
                    **common,
                    "parentId": parent,
                    "orderType": "STP",
                    "side": exit_side,
                    "price": float(request.proposal.stop_loss),
                },
                {
                    **common,
                    "parentId": parent,
                    "orderType": "LMT",
                    "side": exit_side,
                    "price": float(request.proposal.take_profit),
                },
            ]
        )

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        account_id = self._require_submission()
        return await self._request("DELETE", f"/iserver/account/{account_id}/order/{order_id}")

    async def confirm_order_reply(self, reply_id: str) -> dict[str, Any]:
        self._require_submission()
        response = await self._request(
            "POST", f"/iserver/reply/{reply_id}", json={"confirmed": True}
        )
        first = response[0] if isinstance(response, list) and response else response
        if isinstance(first, dict) and first.get("id") and first.get("message"):
            return {
                "status": "AWAITING_IBKR_CONFIRMATION",
                "reply_id": str(first["id"]),
                "messages": first.get("message", []),
            }
        return first

    async def close_position(self, symbol: str, quantity: D | None = None) -> dict[str, Any]:
        positions = await self.get_positions()
        position = next((item for item in positions if item["symbol"] == symbol.upper()), None)
        if not position:
            raise IBKRAPIError("IBKR_POSITION_NOT_FOUND")
        close_quantity = quantity or position["quantity"]
        account_id = self._require_submission()
        side = "SELL" if position["direction"] == Direction.LONG else "BUY"
        return await self._submit_payload(
            [
                {
                    "acctId": account_id,
                    "conid": position["conid"],
                    "cOID": f"close-{symbol}-{int(datetime.now(UTC).timestamp())}",
                    "orderType": "MKT",
                    "side": side,
                    "tif": "DAY",
                    "quantity": float(close_quantity),
                    "outsideRTH": False,
                }
            ]
        )

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        self._require_connection()
        return await self._request("GET", f"/iserver/account/order/status/{order_id}")

    async def get_trade_history(self) -> list[dict[str, Any]]:
        self._require_connection()
        payload = await self._request("GET", "/iserver/account/trades", params={"days": 7})
        rows = payload if isinstance(payload, list) else payload.get("trades", [])
        return [
            {
                "id": row.get("execution_id") or row.get("tradeId") or row.get("order_id"),
                "symbol": row.get("symbol"),
                "direction": "LONG" if str(row.get("side", "")).upper() == "BUY" else "SHORT",
                "quantity": D(str(row.get("size") or row.get("quantity") or 0)),
                "entry": D(str(row.get("price") or 0)),
                "pnl": D(str(row.get("fifoPnlRealized") or row.get("realizedPnl") or 0)),
                "fees": D(str(row.get("commission") or 0)),
                "environment": self.expected_environment,
                "executed_at": row.get("trade_time") or row.get("timestamp"),
            }
            for row in rows
        ]

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from app.risk.engine import RiskEngine
from app.schemas.trading import AccountRiskState, Direction, RiskConfig, TradeProposal


def proposal(**changes):
    data = dict(
        id="proposal-1",
        symbol="NVDA",
        direction=Direction.LONG,
        entry=D("100"),
        stop_loss=D("95"),
        take_profit=D("110"),
        strategy="test",
        strategy_confidence=80,
        price_timestamp=datetime.now(UTC),
    )
    data.update(changes)
    return TradeProposal(**data)


def state(**changes):
    data = dict(equity=D("500"), available_cash=D("500"), buying_power=D("1000"))
    data.update(changes)
    return AccountRiskState(**data)


def test_position_sizing_is_bounded_by_risk():
    decision = RiskEngine(RiskConfig(max_position_size=D("1000"))).validate_trade(
        proposal(), state()
    )
    assert (
        decision.approved
        and decision.calculated_position_size == D("5.0000")
        and decision.risk_amount == D("25.00")
    )


def test_rejects_daily_loss_and_kill_switch():
    engine = RiskEngine(RiskConfig())
    assert engine.validate_trade(proposal(), state(daily_pnl=D("-50"))).reason == "MAX_DAILY_LOSS"
    assert engine.validate_trade(proposal(), state(kill_switch=True)).reason == "KILL_SWITCH_ACTIVE"


def test_rejects_stale_data_and_bad_rr():
    engine = RiskEngine(RiskConfig(), 15)
    assert (
        engine.validate_trade(
            proposal(price_timestamp=datetime.now(UTC) - timedelta(seconds=16)), state()
        ).reason
        == "STALE_MARKET_DATA"
    )
    assert (
        engine.validate_trade(proposal(take_profit=D("108")), state()).reason
        == "MINIMUM_RISK_REWARD"
    )


def test_rejects_duplicate_symbol_when_averaging_disabled():
    assert (
        RiskEngine(RiskConfig()).validate_trade(proposal(), state(existing_symbols={"NVDA"})).reason
        == "AVERAGING_DOWN_DISABLED"
    )

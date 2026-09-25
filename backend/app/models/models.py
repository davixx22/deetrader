import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    name: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="CZK")
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    environment: Mapped[str] = mapped_column(String(10), index=True)


class BrokerConnection(TimestampMixin, Base):
    __tablename__ = "broker_connections"
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    masked_account_id: Mapped[str | None] = mapped_column(String(80))
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    account: Mapped[Account] = relationship()


class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    exchange: Mapped[str | None] = mapped_column(String(40))
    shortable: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class MarketSnapshot(TimestampMixin, Base):
    __tablename__ = "market_snapshots"
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    bid: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    ask: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    indicators: Mapped[dict] = mapped_column(JSONB, default=dict)


class Signal(TimestampMixin, Base):
    __tablename__ = "signals"
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    strategy: Mapped[str] = mapped_column(String(80), index=True)
    direction: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[int]
    payload: Mapped[dict] = mapped_column(JSONB)


class StrategyRun(TimestampMixin, Base):
    __tablename__ = "strategy_runs"
    strategy: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30))
    symbols_scanned: Mapped[int] = mapped_column(default=0)
    signals_found: Mapped[int] = mapped_column(default=0)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class AIAnalysis(TimestampMixin, Base):
    __tablename__ = "ai_analyses"
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id"), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[int]
    payload: Mapped[dict] = mapped_column(JSONB)


class TradeProposal(TimestampMixin, Base):
    __tablename__ = "trade_proposals"
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))
    entry: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    take_profit: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    strategy: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(30), index=True)
    environment: Mapped[str] = mapped_column(String(10), index=True)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("client_order_id"),)
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    client_order_id: Mapped[str] = mapped_column(String(100))
    broker_order_id: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    fees: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)


class Trade(TimestampMixin, Base):
    __tablename__ = "trades"
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10), index=True)
    environment: Mapped[str] = mapped_column(String(10), index=True)
    entry: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    exit: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    pnl: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)
    strategy: Mapped[str] = mapped_column(String(80), index=True)
    exit_reason: Mapped[str | None] = mapped_column(String(50))
    journal: Mapped[dict] = mapped_column(JSONB, default=dict)


class Position(TimestampMixin, Base):
    __tablename__ = "positions"
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    entry: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    take_profit: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    environment: Mapped[str] = mapped_column(String(10), index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class RiskDecision(TimestampMixin, Base):
    __tablename__ = "risk_decisions"
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    approved: Mapped[bool] = mapped_column(Boolean, index=True)
    reason: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column(JSONB)


class RiskConfig(TimestampMixin, Base):
    __tablename__ = "risk_configs"
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), unique=True)
    version: Mapped[int] = mapped_column(default=1)
    config: Mapped[dict] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentState(TimestampMixin, Base):
    __tablename__ = "agent_states"
    state: Mapped[str] = mapped_column(String(20))
    current_operation: Mapped[str | None] = mapped_column(String(200))
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    counters: Mapped[dict] = mapped_column(JSONB, default=dict)


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    channel: Mapped[str] = mapped_column(String(30), index=True)
    event: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(20), index=True)


class SystemEvent(TimestampMixin, Base):
    __tablename__ = "system_events"
    category: Mapped[str] = mapped_column(String(30), index=True)
    level: Mapped[str] = mapped_column(String(20), index=True)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)


Index("ix_trades_environment_created", "environment", "created_at")

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[3] / ".env", ".env"),
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    secret_key: str = "development-only-change-me-32-characters"
    admin_password: SecretStr = SecretStr("change-me-now")
    database_url: str = "postgresql+asyncpg://deetrader:deetrader@postgres:5432/deetrader"
    redis_url: str = "redis://redis:6379/0"
    trading_mode: Literal["paper", "live"] = "paper"
    execution_mode: Literal["manual", "semi_auto", "auto"] = "manual"
    broker_provider: Literal["paper", "ibkr"] = "paper"
    live_trading_enabled: bool = False
    ai_provider: str = "disabled"
    market_data_provider: str = "mock"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_price_age_seconds: int = 15
    access_token_minutes: int = 30
    ibkr_base_url: str = "https://host.docker.internal:5000/v1/api"
    ibkr_account_id: str | None = None
    ibkr_access_token: SecretStr | None = None
    ibkr_verify_tls: bool = True
    ibkr_timeout_seconds: float = 10
    ibkr_order_submission_enabled: bool = False
    ibkr_order_payload_style: Literal["orders_object", "array"] = "orders_object"

    @field_validator("live_trading_enabled")
    @classmethod
    def prevent_accidental_live(cls, value: bool, info):
        if value and info.data.get("trading_mode") != "live":
            raise ValueError("live_trading_enabled requires TRADING_MODE=live")
        return value

    @field_validator("ibkr_order_submission_enabled")
    @classmethod
    def require_explicit_broker(cls, value: bool, info):
        if value and info.data.get("broker_provider") != "ibkr":
            raise ValueError("IBKR order submission requires BROKER_PROVIDER=ibkr")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

from app.brokers.base import BrokerAdapter
from app.brokers.ibkr import IBKRBrokerAdapter
from app.brokers.paper import PaperBrokerAdapter
from app.core.config import Settings


def create_broker(settings: Settings) -> BrokerAdapter:
    if settings.broker_provider == "ibkr":
        token = (
            settings.ibkr_access_token.get_secret_value() if settings.ibkr_access_token else None
        )
        return IBKRBrokerAdapter(
            base_url=settings.ibkr_base_url,
            account_id=settings.ibkr_account_id,
            access_token=token,
            verify_tls=settings.ibkr_verify_tls,
            timeout_seconds=settings.ibkr_timeout_seconds,
            order_submission_enabled=settings.ibkr_order_submission_enabled,
            expected_environment=settings.trading_mode,
            order_payload_style=settings.ibkr_order_payload_style,
        )
    return PaperBrokerAdapter()

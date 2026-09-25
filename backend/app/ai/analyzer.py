import json

from pydantic import ValidationError

from app.schemas.trading import AIAnalysis


class AIAnalyzer:
    """Schema firewall: AI produces analysis only and has no broker dependency."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    async def analyze(self, context: dict) -> AIAnalysis:
        if not self.enabled:
            return AIAnalysis(
                decision="neutral",
                confidence=0,
                reasoning_summary="AI analysis disabled; deterministic pipeline remains available.",
            )
        raw = context.get("provider_response")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
            return AIAnalysis.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise ValueError("AI_MALFORMED_RESPONSE") from exc

from abc import ABC, abstractmethod
from typing import Any


class NotificationChannel(ABC):
    @abstractmethod
    async def send(self, event: str, payload: dict[str, Any]) -> None: ...


class WebNotificationChannel(NotificationChannel):
    def __init__(self):
        self.events: list[dict[str, Any]] = []

    async def send(self, event: str, payload: dict[str, Any]) -> None:
        self.events.append({"event": event, "payload": payload})


class WebhookNotificationChannel(NotificationChannel):
    def __init__(self, url: str, client):
        self.url = url
        self.client = client

    async def send(self, event: str, payload: dict[str, Any]) -> None:
        response = await self.client.post(
            self.url, json={"event": event, "data": payload}, timeout=5
        )
        response.raise_for_status()


class NotificationService:
    def __init__(self, channels: list[NotificationChannel]):
        self.channels = channels

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        for channel in self.channels:
            await channel.send(event, payload)

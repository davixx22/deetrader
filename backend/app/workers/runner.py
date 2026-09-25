import asyncio
import signal

import structlog
from redis.asyncio import Redis

from app.core.config import get_settings

log = structlog.get_logger()


async def run():
    redis = Redis.from_url(get_settings().redis_url)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    log.info("worker_started", mode=get_settings().trading_mode)
    while not stop.is_set():
        await redis.set("deetrader:worker:heartbeat", "alive", ex=30)
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
        except TimeoutError:
            continue
    await redis.aclose()
    log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(run())

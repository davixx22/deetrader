import asyncio
import sys

from redis.asyncio import Redis

from app.core.config import get_settings


async def check() -> int:
    redis = Redis.from_url(get_settings().redis_url)
    try:
        heartbeat = await redis.get("deetrader:worker:heartbeat")
        return 0 if heartbeat == b"alive" else 1
    finally:
        await redis.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(check()))

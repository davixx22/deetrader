import asyncio
import time
from collections import defaultdict, deque

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.routes import broker, router
from app.core.config import get_settings
from app.database.session import engine

settings = get_settings()
log = structlog.get_logger()
app = FastAPI(
    title="DeeTrader API",
    version="0.1.0",
    docs_url="/api/docs" if settings.app_env != "production" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
requests_total = Counter(
    "deetrader_http_requests_total", "HTTP requests", ["method", "path", "status"]
)
current_equity = Gauge("deetrader_current_equity", "Current paper equity")
rate_buckets: dict[str, deque] = defaultdict(deque)
broker_session_task: asyncio.Task | None = None


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = rate_buckets[ip]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= 120:
        return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
    bucket.append(now)
    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        }
    )
    requests_total.labels(request.method, request.url.path, response.status_code).inc()
    return response


@app.on_event("startup")
async def startup():
    global broker_session_task
    try:
        await broker.connect()
    except Exception as exc:
        log.error("broker_connect_failed", error=type(exc).__name__)
    if settings.broker_provider == "ibkr":
        broker_session_task = asyncio.create_task(manage_broker_session())


async def manage_broker_session():
    while True:
        await asyncio.sleep(45)
        try:
            if not getattr(broker, "connected", False):
                await broker.connect()
            elif hasattr(broker, "keepalive"):
                await broker.keepalive()
        except Exception as exc:
            log.error("broker_session_refresh_failed", error=type(exc).__name__)


@app.on_event("shutdown")
async def shutdown():
    if broker_session_task:
        broker_session_task.cancel()
    await broker.disconnect()


async def component_health() -> dict[str, str]:
    components = {
        "backend": "HEALTHY",
        "database": "UNHEALTHY",
        "redis": "UNHEALTHY",
        "broker": "HEALTHY" if getattr(broker, "connected", False) else "UNHEALTHY",
        "market_data": "HEALTHY",
        "agent": "HEALTHY",
        "ai": "DEGRADED" if settings.ai_provider == "disabled" else "HEALTHY",
    }
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            components["database"] = "HEALTHY"
    except Exception:
        pass
    try:
        redis = Redis.from_url(settings.redis_url)
        await redis.ping()
        await redis.aclose()
        components["redis"] = "HEALTHY"
    except Exception:
        pass
    overall = (
        "HEALTHY"
        if all(v == "HEALTHY" for v in components.values())
        else (
            "UNHEALTHY"
            if components["backend"] == "UNHEALTHY" or components["broker"] == "UNHEALTHY"
            else "DEGRADED"
        )
    )
    return {**components, "overall": overall}


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    return await component_health()


@app.get("/health/live")
async def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    components = await component_health()
    ready = components["database"] == "HEALTHY" and components["redis"] == "HEALTHY"
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "components": components},
        status_code=200 if ready else 503,
    )


@app.get("/metrics")
async def metrics():
    account = await broker.get_account()
    current_equity.set(float(account["equity"]))
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(router)

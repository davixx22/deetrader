FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml ./
COPY app ./app
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN addgroup --system --gid 10001 deetrader \
    && adduser --system --uid 10001 --ingroup deetrader deetrader
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY migrations ./migrations
COPY alembic.ini ./
USER deetrader
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--no-server-header"]

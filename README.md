# DeeTrader

DeeTrader is a risk-first platform for manual, semi-automatic, and automatic paper trading. The shipped defaults are intentionally conservative: **paper broker, manual execution, stopped agent, disabled AI, and disabled live trading**. AI can analyze a proposal but never sizes or submits an order. Every executable proposal must pass the deterministic risk engine.

> This software is an engineering platform, not financial advice. Keep it in paper mode until a broker adapter, market-data license, controls, and jurisdiction-specific obligations have been independently reviewed.

## Architecture

```text
Market data provider -> Scanner -> Strategy plugins -> Optional AI schema firewall
                                                        |
                                                        v
Browser -> Nginx -> FastAPI -> Deterministic Risk Engine -> Execution Engine
                         |                                  |
                         v                                  v
                   PostgreSQL/Redis               BrokerAdapter -> PaperBroker
```

The frontend never talks to a broker. The AI module has no broker dependency or credentials. Execution checks environment, approval mode, confidence, kill switch, data age, symbol policy, direction policy, losses, exposure, position count, risk/reward, buying power, and idempotency. Any uncertainty fails closed with no order.

## Included

- Responsive dark-first terminal dashboard, portfolio, scanner candidates, agent activity, risk utilization, PAPER status, and safe controls.
- FastAPI REST and WebSocket API with CORS restrictions, validation, rate limiting, security headers, Argon2 passwords, JWT primitives, structured events, health, and Prometheus metrics.
- Full `BrokerAdapter` contract, functional `PaperBrokerAdapter`, and an IBKR Web API adapter for Client Portal Gateway or OAuth 2.0 sessions.
- Market/limit-ready order schema, long and short positions, bracket stops/targets, fees, spread, slippage, realized/unrealized P&L, partial close, equity, cash, buying power, and basic margin simulation.
- Deterministic risk validation and equity-based position sizing.
- Strategy plugin contract with momentum short, overextended short, breakdown short, mean reversion, and volatility examples.
- Filterable provider-based scanner and optional Pydantic-validated AI analysis.
- PostgreSQL schema and Alembic migration for users, accounts, broker connections, instruments, snapshots, signals, strategy runs, AI analyses, proposals, orders, trades, positions, risk decisions/configuration, agent state, notifications, audit logs, and system events.
- Docker Compose for frontend, backend, worker, PostgreSQL, Redis, Nginx, and optional Prometheus/Grafana.
- Automated coverage of risk sizing, loss limits, stale prices, risk/reward, averaging-down protection, duplicate orders, bracket stops/targets, paper P&L, AI fallback, malformed AI responses, and drawdown.

## Requirements

- Docker Engine 27+ with Compose v2 (recommended)
- Or Python 3.12+ and Node.js 22+ for local development
- Linux VPS with at least 2 CPU cores, 4 GB RAM, persistent storage, TLS termination, and firewall rules for production

## Quick start with Docker

1. Copy `.env.example` to `.env` and replace `SECRET_KEY`, `POSTGRES_PASSWORD`, database URL password, allowed origin, and public URLs.
2. Keep `TRADING_MODE=paper`, `EXECUTION_MODE=manual`, and `LIVE_TRADING_ENABLED=false`.
3. Start services and migrate:

```bash
docker compose build
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
curl http://localhost/health
```

Optional monitoring:

```bash
docker compose --profile monitoring up -d
```

The UI is served at `http://localhost`. In production, put TLS in front of Nginx or replace it with a TLS-enabled reverse proxy.

## Local development

Backend:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

## First login

The development authentication endpoint recognizes `admin@deetrader.local` with the temporary password `change-me-now`. This bootstrap identity is only for the local paper build. Before public exposure, replace bootstrap authentication with a persisted user record and a one-time setup flow; do not expose the development password.

## Configuration

Critical environment settings:

| Variable | Safe default | Purpose |
|---|---:|---|
| `TRADING_MODE` | `paper` | Trade environment; never defaults to live |
| `EXECUTION_MODE` | `manual` | `manual`, `semi_auto`, or `auto` |
| `LIVE_TRADING_ENABLED` | `false` | Separate live interlock |
| `BROKER_PROVIDER` | `paper` | Selected adapter |
| `MARKET_DATA_PROVIDER` | `mock` | Quote/scanner provider |
| `AI_PROVIDER` | `disabled` | Optional analysis only |
| `MAX_PRICE_AGE_SECONDS` | `15` | Reject older prices |
| `SECRET_KEY` | none in production | JWT signing key, preferably injected as a Docker secret |

### IBKR Web API connection

DeeTrader supports the official IBKR Web API through either an authenticated Client Portal Gateway or an OAuth 2.0 access token. For an individual account, install and authenticate the Client Portal Gateway first, then configure:

```env
BROKER_PROVIDER=ibkr
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
IBKR_BASE_URL=https://host.docker.internal:5000/v1/api
IBKR_ACCOUNT_ID=DU123456
IBKR_VERIFY_TLS=false
IBKR_ORDER_SUBMISSION_ENABLED=false
```

A ready-to-edit safe profile is included as `.env.ibkr.example`. It selects the IBKR paper environment but keeps order submission disabled.

`IBKR_VERIFY_TLS=false` is only appropriate for the Gateway's local self-signed certificate on a trusted host path. OAuth deployments should keep TLS verification enabled and inject `IBKR_ACCESS_TOKEN` as a secret. Start read-only: `/api/v1/broker` reports the masked account and balances, while positions, orders, execution quotes, shortability, and trades use IBKR endpoints. The scanner remains on the explicit mock provider until a licensed historical/streaming feed is selected. Enable `IBKR_ORDER_SUBMISSION_ENABLED=true` only after paper-session validation and risk testing.

IBKR warning messages are never accepted automatically. If IBKR returns a reply ID, the order stays `AWAITING_IBKR_CONFIRMATION`; an authenticated caller must explicitly POST `{"confirmation":"CONFIRM IBKR ORDER"}` to `/api/v1/broker/ibkr/replies/{reply_id}`.

Risk configuration is exposed through `GET/PUT /api/v1/risk`. Critical updates require authentication and emit a structured risk event. Initial limits are 5% risk per trade, 10% daily loss, one open position, 2:1 minimum reward/risk, no averaging down, and three consecutive losses.

## API

Public reads: `GET /health`, `/metrics`, `/api/v1/dashboard`, `/account`, `/positions`, `/orders`, `/trades`, `/strategies`, `/risk`, `/agent`, `/analytics`, `/broker`, `/settings`, `/notifications`.

Authenticated mutations: `POST /auth/login`, `/scanner`, `/risk/validate`, `/orders`, `/positions/{symbol}/close`, `/agent/{start|pause|stop}`, `/agent/emergency-stop`; `PUT /risk`; `GET /audit`.

WebSockets: `/api/v1/ws/market`, `/api/v1/ws/positions`, `/api/v1/ws/agent`, `/api/v1/ws/logs`.

Interactive OpenAPI docs are available at `/api/docs` outside production.

## Database and migrations

Apply migrations with `docker compose run --rm backend alembic upgrade head`. Create a reviewed migration with `alembic revision --autogenerate -m "description"`. Never edit an already-applied production migration. Orders have a unique `client_order_id`; trades and positions carry `environment` so paper and live statistics can be filtered independently.

## Paper trading behavior

Quotes may come from the mock provider or a future licensed provider. A fill uses the bid/ask spread plus configured slippage, then charges fees. A bracket position is monitored by price ticks and closes at its stop or target. Repeating an idempotency key returns the original order. Broker disconnect, stale data, missing approval, short unavailability, inadequate buying power, or any breached risk rule blocks execution.

## Production deployment and security

- Generate secrets with a cryptographically secure tool and inject them through Docker secrets or the VPS secret manager.
- Run behind TLS, allow only ports 80/443, restrict `/metrics`, and keep PostgreSQL/Redis on the internal network.
- Replace the bootstrap login, rotate all initial credentials, configure backups, and test restore procedures.
- Pin and scan container images, run as non-root, monitor health/metrics, and ship structured logs to protected storage.
- Restrict CORS to the final HTTPS origin. Bearer authentication avoids browser CSRF on the API; if converted to cookie sessions, add SameSite cookies and CSRF tokens.
- Never put broker or AI keys in `NEXT_PUBLIC_*`, logs, the database, or frontend bundles.

## Backups

Run encrypted daily `pg_dump` backups plus snapshots of the PostgreSQL and Redis volumes. Retain at least one off-host copy. Quarterly, restore into an isolated environment and verify trade, audit, and risk records. Redis is not the system of record.

## Logging and monitoring

The application emits structured events without secrets. Prometheus scrapes `/metrics`; Grafana can use Prometheus as its data source. Alert on degraded health, broker disconnects, order errors, daily loss proximity, kill-switch activation, absent worker heartbeat, database saturation, and restart loops.

## Tests and quality checks

```bash
cd backend
python -m pytest -q
python -m ruff check app tests
cd ../frontend
npm run lint
npm run build
cd ..
docker compose config -q
```

## Troubleshooting

- `DEGRADED` health during host-only development is expected when PostgreSQL or Redis is not running.
- `STALE_MARKET_DATA` means the proposal timestamp exceeded `MAX_PRICE_AGE_SECONDS`; obtain a fresh quote and revalidate.
- `USER_APPROVAL_REQUIRED` is expected in manual and semi-auto modes.
- `KILL_SWITCH_ACTIVE` requires an audited reset flow before the agent can restart.
- Never retry an ambiguous broker timeout with a new idempotency key; reconcile the original broker order first.

## Activating IBKR order routing

1. Authenticate an IBKR paper session and verify `/api/v1/broker`, positions, market snapshots, and contract resolution.
2. Run adapter contract tests against the official paper environment, including reconnects, partial fills, rejects, cancel/replace, shortability, margin, market holidays, and timeouts.
3. Keep `TRADING_MODE=paper` and enable `IBKR_ORDER_SUBMISSION_ENABLED=true` for bracket-order paper testing.
4. Reconcile local and broker state after every ambiguous timeout. Never retry with a new idempotency key until the original order is resolved.
5. Persist and independently audit every proposal, risk decision, IBKR reply, order, fill, and lifecycle transition.
6. Perform security, failure-injection, capacity, legal/compliance, and extended shadow-run reviews.
7. Only then set `TRADING_MODE=live` and `LIVE_TRADING_ENABLED=true` for a tightly limited pilot. Keep live AUTO disabled.

## Known boundaries

The delivered build is complete for local/mock-data paper operation. IBKR connectivity is implemented but cannot be authenticated without the user's Gateway/OAuth session and account ID. Market-data entitlements, external AI calls, outbound Discord/Telegram/email delivery, production identity provisioning, and exchange-calendar service require external credentials or contracts and are not simulated as live.

## Kubernetes and JFrog Artifactory

The production deployment is packaged as a Helm chart in `deploy/helm/deetrader` with separate frontend, API, and worker Deployments. The chart includes readiness/liveness probes, non-root containers, resource limits, a PodDisruptionBudget, optional frontend autoscaling and NetworkPolicy, an Ingress, and optional PostgreSQL and Redis StatefulSets. The API and worker intentionally default to one replica because the authenticated IBKR session and runtime broker switch are process-local; scale them only after moving that state to a shared session service. For a production cluster, managed PostgreSQL and Redis are recommended; disable the bundled StatefulSets and provide their URLs through the existing Secret.

1. Copy `deploy/kubernetes/secrets.example.yaml`, replace every placeholder, and create the Secret through your cluster secret manager. Do not commit the populated file.
2. Copy `deploy/kubernetes/artifactory-values.example.yaml` and replace the registry hostname, repositories, image tag, hostname, TLS secret, and CORS origin.
3. Configure an `artifactory-regcred` image pull secret in the target namespace, preferably through External Secrets or your platform secret operator.
4. Install Helm 3, then deploy with:

```powershell
.\scripts\deploy-kubernetes.ps1 -ValuesFile .\deploy\kubernetes\artifactory-values.yaml
```

To build and publish both OCI images and the packaged Helm chart to Artifactory, configure JFrog CLI with a server ID, set `JFROG_USER` and `JFROG_TOKEN` in the current process, then run:

```powershell
.\scripts\publish-artifactory.ps1 `
  -Registry artifactory.example.com `
  -DockerRepository docker-local `
  -HelmRepository helm-local `
  -JfrogServerId company-artifactory `
  -Tag 0.1.0
```

The frontend image is built for same-origin API access. The Ingress routes `/api` and `/health` to the backend and all other paths to the frontend, so no internal Kubernetes hostname is exposed to the browser.

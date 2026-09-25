param([switch]$Monitoring)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath ".env")) { Copy-Item -LiteralPath ".env.example" -Destination ".env" }
docker compose build
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
if ($Monitoring) { docker compose --profile monitoring up -d } else { docker compose up -d }
docker compose ps

# Deployment

## Docker Compose (recommended when Docker Desktop is installed)

```bash
cp .env.example .env
# Edit JWT_SECRET_KEY and other secrets
docker compose up --build -d
```

The API runs `alembic upgrade head` on start and listens on
`http://localhost:8000`.

The compose file is tuned for development: it bind-mounts the source directories
and runs uvicorn with `--reload`. For a real deployment, drop the volumes, drop
`--reload`, and pin `ENVIRONMENT=production`.

## Windows without Docker

Use SQLite and the in-process token store:

```
DATABASE_URL=sqlite+aiosqlite:///./agentlens.db
REDIS_URL=memory://
```

Then from PowerShell:

```powershell
.\scripts\dev.ps1
```

Generate a JWT secret without OpenSSL:

```powershell
.\scripts\generate-secret.ps1
```

On SQLite the API creates its tables from the models at startup, so Alembic is
optional locally. On PostgreSQL, run the migrations:

```bash
cd apps/api
alembic upgrade head
```

The chain is portable and runs on either backend, and `tests/test_migrations.py`
diffs the migrated schema against the models so the two cannot drift apart.

Services:

| Service | Port | Description |
|---------|------|-------------|
| web | 3000 | Next.js frontend |
| api | 8000 | FastAPI backend |
| postgres | 5432 | PostgreSQL |
| redis | 6379 | Redis |
| worker | — | Background worker |

## Environment variables

Everything below is read by the API through `app/config.py`. See `.env.example`
for the full list.

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | SQLite file | `postgresql+asyncpg://…` in production |
| `REDIS_URL` | `memory://` | `memory://` uses an in-process store; set a real URL in production |
| `JWT_SECRET_KEY` | — | Required. Rotating it invalidates every session |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | |
| `CORS_ORIGINS` | localhost:3000 | Comma-separated exact origins |
| `ENVIRONMENT` | `development` | `production` enables HSTS |
| `OPENAI_API_KEY` | empty | Enables the real LLM judge; empty falls back to the offline heuristic |
| `JUDGE_MODEL` | `gpt-4o-mini` | |
| `JUDGE_BASE_URL` | OpenAI | Any OpenAI-compatible endpoint |
| `MAX_EVALUATION_ITEMS` | `2000` | Cap on subjects per evaluation run |
| `RATE_LIMIT_ENABLED` | `true` | |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | `1200` / `60` | Per client IP |
| `MAX_REQUEST_BYTES` | `5242880` | Requests over this get `413` |
| `STREAM_MAX_SECONDS` | `900` | SSE connections close and let the browser reconnect |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Baked into the frontend at build time |

## Production checklist

1. Set strong secrets: `JWT_SECRET_KEY`, database and Redis passwords.
2. Use managed PostgreSQL and Redis. `REDIS_URL=memory://` cannot revoke a refresh
   token across processes, so a logout on one worker would not apply to another.
3. Set `ENVIRONMENT=production` for HSTS, and terminate TLS in front of the API.
4. Restrict `CORS_ORIGINS` to your dashboard origin.
5. Run the API and worker as separate containers; deploy the frontend as a
   container or to an edge platform with `NEXT_PUBLIC_API_URL` set at build time.
6. Point probes at `/health` (liveness) and `/health/ready` (readiness — returns
   `503` when the database is unreachable).
7. Scrape `/api/v1/system/metrics/prometheus`. It requires a JWT, so scrape it with
   a service account rather than leaving it open.

## Scaling notes

Two subsystems are per-process and need attention before running multiple API
workers:

**The live event bus.** Ingestion publishes to an in-process bus, so a browser
connected to worker A will not see traces ingested by worker B. Replace the bus
in `app/core/events.py` with Redis pub/sub, or pin dashboard SSE connections to
one worker.

**The metrics registry and rate limiter.** Both are in-memory per process, so
counters reset on restart and the effective rate limit multiplies by the worker
count. Aggregate metrics in Prometheus and enforce rate limits at the edge.

Evaluation runs execute inline in the request, so a large dataset with an LLM
judge holds a connection open for its duration. Keep a generous proxy timeout for
`POST /api/v1/projects/{id}/evaluation-runs`, or shard large sweeps.

## Backups

All state is in PostgreSQL; Redis holds only revocable tokens and can be lost
without data loss (users get logged out). Traces are append-mostly and grow with
volume — `GET /api/v1/organizations/{org_id}/usage` reports row counts and 24-hour
volume per workspace to size retention.

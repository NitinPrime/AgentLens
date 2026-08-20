# API Reference

Base URL: `http://localhost:8000`

Interactive docs: `/docs`

## Authentication

Dashboard users:

```http
Authorization: Bearer <access_token>
```

SDK / ingestion (project API keys):

```http
Authorization: Bearer al_xxxxxxxxx
```

API key secrets are shown **once** at creation. Only SHA-256 hashes are stored.

## Auth

- `GET /health`
- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`
- `GET /api/v1/users/me`
- `PATCH /api/v1/users/me`

## Organizations, projects, API keys

### Organizations

- `GET /api/v1/organizations`
- `POST /api/v1/organizations`
- `GET /api/v1/organizations/{org_id}`
- `PATCH /api/v1/organizations/{org_id}`
- `GET /api/v1/organizations/{org_id}/members`
- `POST /api/v1/organizations/{org_id}/members`

### Projects

- `GET /api/v1/organizations/{org_id}/projects`
- `POST /api/v1/organizations/{org_id}/projects`
- `GET /api/v1/projects/{project_id}`
- `PATCH /api/v1/projects/{project_id}`
- `DELETE /api/v1/projects/{project_id}`

### API keys

- `GET /api/v1/projects/{project_id}/api-keys`
- `POST /api/v1/projects/{project_id}/api-keys` — returns `secret` once
- `POST /api/v1/projects/{project_id}/api-keys/{key_id}/revoke`
- `GET /api/v1/sdk/verify` — authenticate with `Bearer al_…`

Signup automatically provisions a personal organization with the user as owner.

## Trace ingestion and reads

SDK (API key):

- `POST /api/v1/traces`
- `POST /api/v1/spans`
- `POST /api/v1/llm-calls`
- `POST /api/v1/tool-calls`
- `POST /api/v1/events`

Dashboard (JWT):

- `GET /api/v1/projects/{project_id}/traces`
- `GET /api/v1/projects/{project_id}/traces/{trace_id}`
- `GET /api/v1/traces/{trace_id}`

Traces, spans, LLM calls, and tool calls are upserted by `id` so the SDK can start a run (`status=running`) and later complete it. Trace token totals, cost, and duration are recomputed from child rows on every write.

## Analytics

- `GET /api/v1/organizations/{org_id}/analytics?range=24h|7d|30d|90d|custom&project_id=&start=&end=`

Returns summary KPIs, a filled timeseries (runs, success, errors, latency, tokens, cost), and per-model usage. Values are aggregated from stored traces — not hardcoded. `custom` requires `start` and `end`.

## Evaluations

Dashboard (JWT):

- `GET /api/v1/evaluator-types`
- `GET|POST /api/v1/projects/{project_id}/datasets`
- `GET|PATCH|DELETE /api/v1/datasets/{dataset_id}`
- `GET|POST /api/v1/datasets/{dataset_id}/items`
- `GET|POST /api/v1/projects/{project_id}/evaluators`
- `PATCH|DELETE /api/v1/evaluators/{evaluator_id}`
- `GET|POST /api/v1/projects/{project_id}/evaluation-runs`
- `GET /api/v1/evaluation-runs/{run_id}`
- `GET /api/v1/evaluation-runs/{run_id}/results?only_failures=&limit=&offset=`
- `GET /api/v1/evaluation-runs/{run_id}/compare?baseline={run_id}&max_pass_rate_drop=&max_score_drop=`
- `GET|POST /api/v1/projects/{project_id}/prompt-versions`

SDK (API key):

- `GET /api/v1/sdk/datasets`
- `GET|POST /api/v1/sdk/datasets/{name}/items` — POST creates the dataset when the name is new
- `POST /api/v1/sdk/evaluation-runs`

Details in [evaluations.md](evaluations.md).

## Versions and regressions

- `GET /api/v1/projects/{project_id}/versions?dimension=agent_version|prompt_version|model_version|agent_name&range=30d`
- `GET /api/v1/projects/{project_id}/versions/compare?dimension=&baseline=&candidate=&range=&max_success_rate_drop=&max_latency_increase=&max_cost_increase=`

Details in [versions.md](versions.md).

## Live stream and self-observability

- `GET /api/v1/projects/{project_id}/stream?token={access_token}` — server-sent events

  `EventSource` cannot set headers, so the access token is passed as a query
  parameter. Event names: `connected`, `trace`, `span`, `llm_call`, `tool_call`,
  `event`, `closing`. Comment frames (`: ping`) act as heartbeats.

- `GET /api/v1/system/info`
- `GET /api/v1/system/metrics`
- `GET /api/v1/system/metrics/prometheus`
- `GET /api/v1/organizations/{org_id}/usage`
- `GET /health`, `GET /health/ready`

## Conventions

**Errors** are `{"detail": "message"}` for handled failures and FastAPI's
validation array for malformed bodies.

**Headers** on every response: `X-Request-ID` (echoed from the request when you
send one, otherwise generated) and `X-Response-Time`, plus
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and
`Permissions-Policy`. HSTS is added when `ENVIRONMENT=production`.

**Status codes** worth noting: `201` on creation, `204` on delete, `401` for a
missing or invalid credential, `403` when your role in the organization is too low
for the action, `404` for anything belonging to another tenant (rather than `403`,
so ids cannot be probed), `413` for a body over `MAX_REQUEST_BYTES`, `429` when
rate limited (with `Retry-After`), and `503` from `/health/ready` when the
database is unreachable.

**Pagination** uses `limit` and `offset`, and list responses that support it
return `{"items": [...], "total": n}`.

**Rate limiting** is a sliding window per client IP, `RATE_LIMIT_REQUESTS` per
`RATE_LIMIT_WINDOW_SECONDS` (default 1200 per 60s), and can be disabled with
`RATE_LIMIT_ENABLED=false` for bulk imports or seeding. Health checks, the docs,
and the SSE stream are exempt. Behind a proxy the limit applies to the proxy's
address, so enforce per-client limits at the edge instead.


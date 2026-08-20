# AgentLens

**Understand what your AI agents actually do.**

AgentLens is an observability, debugging, evaluation, and monitoring platform for
applications built with AI agents and LLM workflows — think Datadog / Sentry /
PostHog, but specifically for AI agents.

Your agent sends traces through the SDK. AgentLens gives you the execution tree,
the cost and latency of every model call, dashboards over the whole fleet, scored
evaluations against golden datasets, and a regression check between two versions.

## What it does

| Capability | Where |
|-----------|-------|
| Trace every agent run: spans, LLM calls, tool calls, events, errors | `/traces` |
| Waterfall explorer with input/output, tokens, and cost per span | `/traces/[id]` |
| Live feed over server-sent events as runs are ingested | `/traces` |
| KPIs and charts: runs, success rate, latency, tokens, cost, model mix | `/dashboard` |
| Datasets, twelve evaluator types, and an LLM judge | `/evaluations` |
| Run comparison with the exact checks that flipped to failing | `/evaluations/[id]` |
| Version rollups and pass/warn/fail regression verdicts | `/versions` |
| Its own request metrics, stream stats, and workspace usage | `/settings` |

## Try it in five minutes

Two commands. The first writes a local `.env`, installs dependencies, starts the
API and the web app in their own terminals, and waits until the API answers. The
second fills it with a week of believable traffic.

```powershell
Set-Location E:\AgentLens
.\scripts\dev.ps1
.\apps\api\.venv\Scripts\python.exe scripts\seed_demo.py
```

```bash
python scripts/seed_demo.py
```

The seeder creates a demo account, a week of traces across two agent versions
where the newer one regresses, six evaluators, a golden dataset, and four
evaluation runs. It prints the login and an API key when it finishes. Nothing
calls a model provider, so no provider key is needed.

Sign in at http://localhost:3000 with `demo@agentlens.dev` / `DemoPassword123!`,
then drive it live:

```powershell
$env:AGENTLENS_API_KEY = "al_..."     # printed by the seeder
python examples\support_agent.py --runs 12    # watch /traces update live
python examples\evaluate_agent.py --degrade   # a CI quality gate failing
```

Full walkthrough: [docs/demo.md](docs/demo.md).

## Instrument your own agent

```python
from agentlens import AgentLens

lens = AgentLens(api_key="al_...")

with lens.trace(
    "support_ticket",
    agent_name="support-agent",
    agent_version="v1.5.0",
    input={"question": question},
) as trace:
    with trace.tool_call("order_lookup", {"order_id": "NW-10231"}) as tool:
        tool.set_output({"status": "in_transit"})

    with trace.llm_call(
        model="gpt-4o",
        messages=[{"role": "user", "content": question}],
        input_tokens=1200,
    ) as call:
        reply = my_llm.complete(question)
        call.set_completion(reply)
        call.set_usage(output_tokens=80)

    trace.set_output(reply)
```

Or wrap an existing entry point:

```python
@lens.observe(agent_name="support-agent", agent_version="v1.5.0")
def answer(question: str) -> str:
    return my_agent.run(question)
```

Then gate your deploys on quality:

```python
lens.evaluate("support-golden", answer).require_pass_rate(0.9)
```

Cost is estimated server-side from the model and token counts, so you never send
money amounts. Ids are client-generated and writes are idempotent, so a run can be
opened as `running` and completed later. See [docs/sdk.md](docs/sdk.md).

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Recharts |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Alembic |
| Database | PostgreSQL (SQLite for local development) |
| Cache / tokens | Redis (in-process fallback for local development) |
| SDK | Python, `httpx` only |

## Project structure

```text
agentlens/
├── apps/
│   ├── web/          # Next.js dashboard and landing page
│   └── api/          # FastAPI backend, Alembic migrations, tests
├── packages/
│   └── python-sdk/   # agentlens SDK and its tests
├── workers/          # Background worker
├── examples/         # Runnable demo agents
├── scripts/          # dev.ps1, generate-secret.ps1, seed_demo.py
├── docs/             # Architecture, API, SDK, evaluations, versions, demo, deployment
├── .github/          # CI workflow and issue templates
└── docker-compose.yml
```

## Setup

### Prerequisites

- Node.js 22+
- Python 3.10+ (3.12 recommended)
- Docker Desktop (optional — only for the full Postgres/Redis stack)

### Windows (PowerShell)

PowerShell does **not** accept `&&`. Run commands on separate lines, or use `;`.

Generate a JWT secret without OpenSSL:

```powershell
.\scripts\generate-secret.ps1
```

Copy `.env.example` to `.env` and set `JWT_SECRET_KEY` to that value. Without
Docker, keep the local defaults:

```
DATABASE_URL=sqlite+aiosqlite:///./agentlens.db
REDIS_URL=memory://
```

Start both services:

```powershell
Set-Location E:\AgentLens
.\scripts\dev.ps1
```

Or run each one yourself:

```powershell
Set-Location E:\AgentLens\apps\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
Set-Location E:\AgentLens\apps\web
npm run dev
```

- Web: http://localhost:3000
- API docs: http://localhost:8000/docs

### Docker Compose

```bash
cp .env.example .env
docker compose up postgres redis api worker -d
```

Full stack: `docker compose up --build`.

## Tests

Backend (72 tests). The suite pins its own SQLite database and in-process token
store, so it does not need Postgres, Redis, or a `.env`:

```powershell
Set-Location E:\AgentLens\apps\api
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\pytest.exe -q
```

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

SDK (16 tests, no server needed — the API is faked):

```powershell
Set-Location E:\AgentLens\packages\python-sdk
..\..\apps\api\.venv\Scripts\pytest.exe -q
```

Frontend:

```powershell
Set-Location E:\AgentLens\apps\web
npm run lint
npm run build
```

## Roadmap

- [x] Phase 1: Monorepo, Docker, auth
- [x] Phase 2: Organizations, projects, API keys
- [x] Phase 3: Trace ingestion, SDK
- [x] Phase 4: Trace explorer UI
- [x] Phase 5: Analytics dashboard
- [x] Phase 6: Evaluations & LLM-as-judge
- [x] Phase 7: Regression testing & versions
- [x] Phase 8: Demo agents & seeded demo
- [x] Phase 9: Real-time updates & self-observability
- [x] Phase 10: Testing, security, docs, deployment polish

## Known limits

Deliberate trade-offs, documented rather than hidden:

- **Evaluation runs execute inline** in the HTTP request. Large datasets with an
  LLM judge hold the connection open; shard sweeps beyond a few hundred items.
- **The live event bus and metrics registry are per-process.** Multiple API workers
  need Redis pub/sub for the stream and Prometheus for aggregation. See
  [docs/deployment.md](docs/deployment.md#scaling-notes).
- **The rate limiter keys on client IP**, so behind a proxy it applies to the
  proxy. Enforce per-client limits at the edge.
- **Without `OPENAI_API_KEY` the LLM judge uses an offline heuristic.** Scores are
  labelled as such and are a smoke test, not a quality bar.
- **Model prices come from a static table** (`app/core/pricing.py`) and need
  updating as providers change them.

## Documentation

- [Architecture](docs/architecture.md) — components, data model, request flow, trade-offs
- [API](docs/api.md) — every endpoint, conventions, status codes
- [SDK](docs/sdk.md) — tracing, decorators, datasets, evaluations
- [Evaluations](docs/evaluations.md) — evaluator catalogue, LLM judge, run comparison
- [Versions](docs/versions.md) — rollups and regression verdicts
- [Demo](docs/demo.md) — the seeded workspace and example agents
- [Deployment](docs/deployment.md) — configuration, production checklist, scaling

## License

MIT — see [LICENSE](LICENSE).
#   A g e n t L e n s  
 
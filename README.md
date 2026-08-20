# AgentLens

**Observability for AI agents** — Datadog / Sentry for LLM workflows.

Your agent sends traces through a Python SDK. AgentLens shows the full execution tree, cost and latency per model call, live traffic, golden-dataset evaluations, and pass/fail checks when you ship a new version.

```text
Your agent ──SDK──▶ AgentLens API ──▶ Dashboard
                    traces · cost · evals · versions
```

---

## Why it exists

AI agents fail in ways normal apps do not: a tool times out, a prompt regresses, a new model gets slower and more expensive. AgentLens records every run end-to-end so you can **debug**, **monitor**, and **catch quality drops** before users do.

| Without AgentLens | With AgentLens |
|-------------------|----------------|
| You only see the final reply | You see every span, tool call, and LLM call |
| “It feels worse after deploy” | Version comparison with a pass / warn / fail verdict |
| Manual spot checks | Golden datasets + CI quality gates |

---

## Features

- **Tracing** — spans, LLM calls, tool calls, events, and errors in a waterfall explorer
- **Live feed** — server-sent events; new runs appear as they are ingested
- **Analytics** — runs, success rate, latency, tokens, cost, and model mix
- **Evaluations** — datasets, 12 evaluator types, optional LLM-as-judge
- **Regression checks** — compare agent / prompt / model versions
- **Python SDK** — context managers, `@observe`, `evaluate()`, CI `require_pass_rate`
- **Self-observability** — request metrics, Prometheus export, workspace usage

---

## Quick start (local demo)

**Prerequisites:** Node.js 22+, Python 3.10+

### Windows

```powershell
git clone https://github.com/NitinPrime/AgentLens.git
cd AgentLens
.\scripts\dev.ps1
.\apps\api\.venv\Scripts\python.exe scripts\seed_demo.py
```

### macOS / Linux

```bash
git clone https://github.com/NitinPrime/AgentLens.git
cd AgentLens
cp .env.example .env
# set DATABASE_URL=sqlite+aiosqlite:///./agentlens.db and REDIS_URL=memory://
cd apps/api && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# in another terminal:
cd apps/web && npm install && npm run dev
# then from repo root:
python scripts/seed_demo.py
```

Open **http://localhost:3000**

| | |
|--|--|
| Email | `demo@agentlens.dev` |
| Password | `DemoPassword123!` |

What to click:

1. **Dashboard** — fleet KPIs and charts  
2. **Traces** — open a run, explore the waterfall  
3. **Evaluations** — baseline vs regressed golden run  
4. **Versions** — `v1.5.0` vs `v1.4.0` (quality drop)

### Live traffic (optional)

```powershell
$env:AGENTLENS_API_KEY = "al_..."   # printed by the seeder
$env:AGENTLENS_API_URL = "http://localhost:8000"
python examples\support_agent.py --runs 12
python examples\evaluate_agent.py --degrade
```

Keep **Traces** open while the support agent runs — rows appear live.

---

## Instrument an agent

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

Or wrap an existing function:

```python
@lens.observe(agent_name="support-agent", agent_version="v1.5.0")
def answer(question: str) -> str:
    return my_agent.run(question)
```

Gate deploys in CI:

```python
lens.evaluate("support-golden", answer).require_pass_rate(0.9)
```

More: [docs/sdk.md](docs/sdk.md)

---

## Architecture

| Layer | Stack |
|-------|--------|
| Dashboard | Next.js 16, TypeScript, Tailwind, shadcn/ui, TanStack Query, Recharts |
| API | FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Alembic |
| Database | PostgreSQL in production · SQLite for local demo |
| Tokens | Redis in production · in-process store locally (`memory://`) |
| SDK | Python · `httpx` only |

```text
agentlens/
├── apps/
│   ├── web/           # Dashboard + landing page
│   └── api/           # FastAPI + migrations + tests
├── packages/python-sdk/
├── examples/          # Demo agents
├── scripts/           # seed_demo.py, dev.ps1
├── docs/
└── docker-compose.yml
```

Auth: JWT for the dashboard, `al_…` API keys for the SDK. Every row is scoped by project so tenants stay isolated.

---

## Tests

| Suite | Count | Command |
|-------|------:|---------|
| API | 72 | `cd apps/api && pytest` |
| SDK | 16 | `cd packages/python-sdk && pytest` |
| Web | — | `cd apps/web && npm run lint && npm run build` |

API tests use an in-memory SQLite DB — no Postgres, Redis, or `.env` required.

CI runs on every push via [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Documentation

| Doc | Contents |
|-----|----------|
| [Architecture](docs/architecture.md) | Data model, request flow, trade-offs |
| [API](docs/api.md) | Endpoints and conventions |
| [SDK](docs/sdk.md) | Tracing, datasets, evaluations |
| [Evaluations](docs/evaluations.md) | Evaluator catalogue, LLM judge |
| [Versions](docs/versions.md) | Rollups and regression verdicts |
| [Demo](docs/demo.md) | Seeded workspace walkthrough |
| [Deployment](docs/deployment.md) | Env vars, production checklist |

Interactive API docs when running locally: http://localhost:8000/docs

---

## Deploy (free tier sketch)

For a public portfolio demo:

| Piece | Free option |
|-------|-------------|
| Dashboard | [Vercel](https://vercel.com) · root `apps/web` |
| API | [Render](https://render.com) · root `apps/api` |
| Database | [Neon](https://neon.tech) Postgres |
| Redis | `REDIS_URL=memory://` (enough for a demo) |

Set `NEXT_PUBLIC_API_URL` on Vercel to the Render URL, and `CORS_ORIGINS` on the API to the Vercel URL. Free API hosts sleep when idle — first load can take ~30s.

Details: [docs/deployment.md](docs/deployment.md)

---

## Known limits

Deliberate trade-offs, not bugs:

- Evaluation runs execute **inline** in the HTTP request (shard large LLM-judge sweeps)
- Live event bus and metrics are **per-process** (use Redis pub/sub + Prometheus to scale out)
- Without `OPENAI_API_KEY`, the LLM judge uses a labelled offline heuristic
- Model prices come from a static table in `app/core/pricing.py`

---

## License

MIT — see [LICENSE](LICENSE).

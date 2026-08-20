# Demo and seeded workspace

`scripts/seed_demo.py` fills a running AgentLens with a week of believable
traffic so every page has real data. Everything is simulated and deterministic,
so no model provider key is required.

## Seed it

Start the API (and the web app if you want to click around), then:

```powershell
Set-Location E:\AgentLens
.\apps\api\.venv\Scripts\python.exe scripts\seed_demo.py
```

```bash
python scripts/seed_demo.py
```

The script only uses the public HTTP API, so it works against SQLite, Postgres,
or a remote deployment.

| Flag | Default | Purpose |
|------|---------|---------|
| `--api-url` | `http://localhost:8000` | Target API |
| `--email` / `--password` | `demo@agentlens.dev` / `DemoPassword123!` | Demo account (created if absent, reused if present) |
| `--org` / `--project` | `Northwind AI` / `Support Agent` | Workspace names |
| `--days` / `--per-day` | `7` / `8` | Volume of backdated support traces |
| `--skip-history` | off | Only create evaluators, dataset, and runs |
| `--seed` | `11` | Randomness seed, so a re-run reproduces the same shape |

It prints the API key it created at the end. Re-running is safe: the account,
organization, project, evaluators, and dataset are reused, and a fresh API key is
issued each time.

## What you get

**Traces.** `days × per-day` support-agent traces spread across working hours,
plus six RAG traces. Each support trace has an intent-classification LLM call, an
agent span wrapping a tool call, a reply-drafting LLM call, and lifecycle events.
Failed runs carry a `ToolTimeout` on both the tool call and its parent span.

**A deliberate regression.** The newest third of the days run `v1.5.0` /
`support-reply-v4`: roughly twice the latency, a 16% error rate instead of 4%, and
30% of replies degraded to a generic "our team is looking into it". The older days
run `v1.4.0` / `support-reply-v3` cleanly. The Versions page returns a `fail`
verdict comparing the two.

**Evaluators.** Six of them, covering similarity, required content, forbidden
hedging, error-free completion, a four-second latency budget, and an LLM judge.

**A golden dataset.** `support-golden`, twelve items with expected answers.

**Four evaluation runs.** Two over stored traces (one per agent version) and two
over the golden dataset (one clean, one with a regressed prompt). Comparing the
two dataset runs shows the individual items that flipped to failing.

Because production traces have no expected output, the trace runs deliberately
select only the evaluators that work without a reference answer. The similarity
and judge checks belong to the dataset runs.

## Then drive it live

Export the key the seeder printed:

```powershell
$env:AGENTLENS_API_KEY = "al_..."
$env:AGENTLENS_API_URL = "http://localhost:8000"
```

| Script | What it does |
|--------|-------------|
| `examples/minimal_trace.py` | Smallest possible trace: one span, one tool call, one LLM call |
| `examples/support_agent.py` | Tool-using support agent; `--runs`, `--agent-version`, `--error-rate`, `--latency-scale`, `--break-tools` |
| `examples/rag_agent.py` | RAG pipeline with retrieval, rerank, and generation spans; the last question is unanswerable and hedges |
| `examples/evaluate_agent.py` | CI-style quality gate; `--degrade` fails it on purpose, `--upload` (re)creates the dataset |
| `examples/demo_data.py` | Shared tickets, knowledge base, and golden items used by all of the above |

Open `/traces` in the dashboard before running `support_agent.py`: the live
indicator turns green and rows appear as they are ingested over the server-sent
event stream.

To watch a bad deploy land:

```powershell
python examples\support_agent.py --runs 12 --agent-version v1.6.0 --break-tools
```

Then compare `v1.5.0` against `v1.6.0` on `/versions`.

To watch a quality gate fail:

```powershell
python examples\evaluate_agent.py --degrade
```

The process exits non-zero, and the new run appears on `/evaluations` ready to be
compared against the previous one.

## Starting over

The demo lives in ordinary tables, so deleting the project removes it. On a local
SQLite setup you can also stop the API, delete `apps/api/agentlens.db`, and start
again from an empty database.

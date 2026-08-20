# Python SDK

Instrument any Python agent, send structured traces to AgentLens, and score it
against datasets from CI.

## Install

```powershell
Set-Location E:\AgentLens\packages\python-sdk
pip install -e .
```

```bash
pip install -e packages/python-sdk
```

Only dependency: `httpx`.

## Configure

```powershell
$env:AGENTLENS_API_KEY = "al_..."
$env:AGENTLENS_API_URL = "http://localhost:8000"
```

Create the key in the dashboard under **Projects → project → API keys**. It is
shown once. `AgentLens(api_key=..., base_url=...)` overrides the environment.

```python
from agentlens import AgentLens

lens = AgentLens()                 # reads the environment
print(lens.verify())               # {'project_name': ..., 'key_prefix': 'al_...'}
```

The client is a plain object holding an `httpx.Client`. Use it as a context
manager, or call `lens.close()`, to release the connection pool.

## Tracing

```python
with lens.trace(
    "customer_support_task",
    agent_name="support-agent",
    session_id="conv-4821",
    input={"question": "Where is my order?"},
    agent_version="v1.5.0",
    prompt_version="support-reply-v4",
    model_version="gpt-4o",
) as trace:
    with trace.span("planning", type="AGENT") as span:
        span.set_output({"plan": ["lookup", "reply"]})

    with trace.tool_call("order_lookup", {"order_id": "NW-10231"}) as tool:
        tool.set_output({"status": "in_transit"})

    with trace.llm_call(
        model="gpt-4o",
        provider="openai",
        messages=[{"role": "user", "content": "Where is my order?"}],
        input_tokens=1200,
        temperature=0.2,
    ) as call:
        call.set_completion("Your order is in transit.")
        call.set_usage(output_tokens=80)

    trace.event("resolved", {"channel": "email"})
    trace.set_output("Your order is in transit.")

print(trace.total_tokens, trace.total_cost)   # server-computed, available after close
```

Nesting is automatic: a span opened inside another span becomes its child, which
is what produces the waterfall in the trace explorer. Span types are `LLM`,
`TOOL`, `RETRIEVAL`, `AGENT`, `CHAIN`, and `CUSTOM`.

An exception escaping a `with` block marks that span and the trace as errors and
records the type and message. `trace.mark_error(exc)` records a failure you caught
yourself, for when a batch runner should not crash but the trace is not a success.

Cost is estimated server-side from the model name and token counts, so you never
have to send money amounts.

### The decorator

Fastest way to instrument an existing entry point:

```python
@lens.observe(agent_name="support-agent", agent_version="v1.5.0")
def answer(question: str) -> str:
    return my_agent.run(question)
```

Each call becomes one trace with the arguments as input and the return value as
output. Pass `capture_input=False` or `capture_output=False` to keep payloads out
of AgentLens.

## Datasets

```python
lens.upload_dataset(
    "support-golden",
    [
        {"name": "order-status", "input": "Where is NW-10231?", "expected_output": "in transit"},
        {"name": "refund-window", "input": "Can I return it?", "expected_output": "30 days"},
    ],
    replace=True,      # replace the existing items instead of appending
)

items = lens.get_dataset("support-golden")
datasets = lens.list_datasets()
```

`upload_dataset` creates the dataset when the name is unknown, so a CI job can own
its fixtures without a manual setup step.

## Evaluations

Run the agent locally, let the server score it:

```python
run = lens.evaluate(
    "support-golden",
    lambda item: my_agent.answer(item.input),
    name="nightly golden",
    evaluators=["answer-similarity", "no-hedging"],   # omit for all active evaluators
    agent_version="v1.5.0",
)
print(run)                      # 11/12 passed (91.7%), avg score 0.94
run.require_pass_rate(0.9)      # raises EvaluationFailed below the bar
```

`require_pass_rate` raising an exception is what turns this into a CI gate:

```python
from agentlens import EvaluationFailed

try:
    lens.evaluate("support-golden", agent).require_pass_rate(0.9)
except EvaluationFailed as exc:
    raise SystemExit(str(exc))
```

Every item is traced by default so a failing score links back to the run that
produced it. Pass `trace=False` to keep evaluation runs out of your production
version rollups.

Score traces that already exist, with no local execution:

```python
run = lens.evaluate_traces(
    "production sweep",
    evaluators=["completed-without-error", "under-4s"],
    agent_name="support-agent",
    agent_version="v1.5.0",
    limit=200,
)
```

See [evaluations.md](evaluations.md) for the evaluator catalogue.

## Escape hatch

Anything the typed helpers do not cover:

```python
lens.get("/sdk/datasets")
lens.post("/traces", {"name": "manual", "status": "success"})
```

Both raise `AgentLensError` with the server's message on a non-2xx response.

## Behaviour to expect

- **Synchronous and blocking.** Every span boundary is an HTTP request. That keeps
  the SDK trivial to reason about and correct under exceptions, at the cost of
  latency in the traced path. For hot loops, trace at a coarser granularity.
- **Failures are loud.** A rejected write raises `AgentLensError` rather than being
  swallowed. Wrap instrumentation in `try`/`except` if telemetry must never break
  the agent.
- **Ids are client-generated** UUIDs, so you can correlate with your own logs
  before the server has seen anything.
- **Writes are idempotent** by id: re-posting a span updates it instead of
  duplicating it.

## Endpoints used

| Purpose | Endpoint |
|---------|----------|
| Verify key | `GET /api/v1/sdk/verify` |
| Ingest | `POST /api/v1/traces`, `/spans`, `/llm-calls`, `/tool-calls`, `/events` |
| Datasets | `GET|POST /api/v1/sdk/datasets/{name}/items`, `GET /api/v1/sdk/datasets` |
| Evaluations | `POST /api/v1/sdk/evaluation-runs` |

All of them authenticate with `Authorization: Bearer al_...`.

## Examples

`examples/minimal_trace.py`, `examples/support_agent.py`, `examples/rag_agent.py`,
and `examples/evaluate_agent.py`. See [demo.md](demo.md).

# AgentLens Python SDK

Instrument any Python agent, send structured traces to AgentLens, and score it
against datasets from CI. `httpx` is the only dependency.

Full reference: [docs/sdk.md](../../docs/sdk.md).

## Install

```powershell
Set-Location E:\AgentLens\packages\python-sdk
pip install -e .
```

```bash
pip install -e packages/python-sdk
```

## Configure

```powershell
$env:AGENTLENS_API_KEY = "al_..."
$env:AGENTLENS_API_URL = "http://localhost:8000"
```

Create the key in the dashboard under **Projects → project → API keys**; it is
shown once. Constructor arguments override the environment.

## Trace an agent

```python
from agentlens import AgentLens

lens = AgentLens()

with lens.trace(
    "customer_support_task",
    agent_name="support-agent",
    input={"message": "Where is my order?"},
    agent_version="v1.5.0",
    prompt_version="support-reply-v4",
) as trace:
    with trace.span("planning", type="AGENT") as span:
        span.set_output({"plan": "look up the order then reply"})

    with trace.tool_call("order_lookup", {"order_id": "NW-10231"}) as tool:
        tool.set_output({"status": "in_transit"})

    with trace.llm_call(
        model="gpt-4o",
        provider="openai",
        messages=[{"role": "user", "content": "Where is my order?"}],
        input_tokens=1200,
    ) as call:
        call.set_completion("Your order is in transit.")
        call.set_usage(output_tokens=80)

    trace.event("resolved", {"channel": "email"})
    trace.set_output("Your order is in transit.")

print(trace.total_tokens, trace.total_cost)
```

Spans nest automatically, an escaping exception marks the span and trace as
errors, and cost is estimated server-side from the model and token counts.

Or wrap an existing entry point:

```python
@lens.observe(agent_name="support-agent", agent_version="v1.5.0")
def answer(question: str) -> str:
    return my_agent.run(question)
```

## Evaluate it

```python
lens.upload_dataset(
    "support-golden",
    [{"name": "order-status", "input": "Where is NW-10231?", "expected_output": "in transit"}],
    replace=True,
)

run = lens.evaluate("support-golden", lambda item: my_agent.answer(item.input))
print(run)                    # 11/12 passed (91.7%), avg score 0.94
run.require_pass_rate(0.9)    # raises EvaluationFailed, so CI goes red
```

Score traces that already exist, without running anything locally:

```python
run = lens.evaluate_traces(
    "production sweep",
    evaluators=["completed-without-error", "under-4s"],
    agent_version="v1.5.0",
    limit=200,
)
```

## Behaviour to expect

Calls are synchronous and blocking (one HTTP request per span boundary), failures
raise `AgentLensError` rather than being swallowed, ids are client-generated
UUIDs, and writes are idempotent by id so a run can be opened as `running` and
completed later.

## Tests

No server required — the API is faked:

```bash
pip install -e ".[dev]"
pytest
```

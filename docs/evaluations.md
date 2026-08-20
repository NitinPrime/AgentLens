# Evaluations

An evaluation run takes a set of **subjects** (dataset items with expected
outputs, or traces already ingested from production), scores each one with every
selected **evaluator**, and stores the results so two runs can be diffed.

A subject passes a run only when every evaluator that scored it passed. That
makes the run-level pass rate strict on purpose: one broken check is a failure.

## The pieces

| Concept | What it is | Created by |
|---------|-----------|------------|
| Dataset | Named collection of test cases for one project | Dashboard or `lens.upload_dataset()` |
| Dataset item | One `input` plus its `expected_output` | Dashboard paste box or SDK |
| Evaluator | A scorer with a config and a pass threshold | Dashboard (`/evaluations`) |
| Evaluation run | One scoring pass over subjects | Dashboard or SDK |
| Evaluation result | One evaluator's verdict on one subject | Produced by a run |

Datasets and evaluators are scoped to a project. Deleting a dataset keeps the
runs that used it, so history survives cleanup.

## Evaluator types

Every evaluator returns a score in `[0, 1]`, a pass flag, a failure category
label, and human-readable reasoning. Pass means `score >= threshold`.

| Type | Scores | Needs expected output | Default threshold |
|------|--------|----------------------|-------------------|
| `exact_match` | Output equals expected after optional trim/case fold | yes | 1.0 |
| `contains` | Output contains `value`, or the expected output when `value` is empty | only when `value` is empty | 1.0 |
| `not_contains` | Output does **not** contain `value` | no | 1.0 |
| `regex` | Output matches `pattern` | no | 1.0 |
| `json_field_match` | Field at `path` equals `expected` | only when `expected` is unset | 1.0 |
| `numeric_tolerance` | Number is within `tolerance` of expected | yes | 1.0 |
| `similarity` | Token-overlap F1 against expected | yes | 0.8 |
| `valid_json` | Output parses as a JSON object or array | no | 1.0 |
| `no_error` | Run did not end in an error status | no | 1.0 |
| `latency_under` | Duration under `max_ms` | no | 1.0 |
| `cost_under` | Cost under `max_cost` USD | no | 1.0 |
| `llm_judge` | A model scores the output against `criteria` | no | 0.7 |

`GET /api/v1/evaluator-types` returns this table with each type's default config,
which is what the dashboard form prefills.

Evaluators that need an expected output are **skipped**, not failed, when a
subject has none. The run detail lists them under `skipped_evaluators` so a
trace-based run does not silently look worse than it is. This is why runs over
production traces usually select only the checks that work without a reference
answer (`no_error`, `latency_under`, `cost_under`, `not_contains`, `regex`,
`valid_json`, `llm_judge`).

## LLM as judge

`llm_judge` posts to an OpenAI-compatible `/chat/completions` endpoint and asks
for `{"score": <0..1>, "reasoning": "..."}`. Configure it with:

```
OPENAI_API_KEY=sk-...
JUDGE_MODEL=gpt-4o-mini
JUDGE_BASE_URL=https://api.openai.com/v1
```

Scores above 1 are treated as a 0–10 rating and divided by ten.

**Without an API key the judge still runs**, using a documented offline
heuristic instead of failing the run: token-overlap F1 against the expected
output when there is one, otherwise how much of the criteria vocabulary the
output covers combined with response depth. The reasoning field always says the
heuristic was used, so an offline score is never mistaken for a model verdict.
Treat heuristic scores as a smoke test, not a quality bar.

## Running an evaluation

### Against a dataset, from the SDK

Only you can call your models and tools, so the agent runs locally and AgentLens
scores the outputs it returns.

```python
from agentlens import AgentLens

lens = AgentLens(api_key="al_...")

def agent(item):
    return my_agent.answer(item.input)

run = lens.evaluate(
    "support-golden",
    agent,
    name="nightly golden",
    evaluators=["answer-similarity", "no-hedging"],   # omit to use all active
    agent_version="v1.5.0",
    prompt_version="support-reply-v4",
)
print(run)                       # 11/12 passed (91.7%), avg score 0.94
run.require_pass_rate(0.9)       # raises EvaluationFailed -> non-zero exit in CI
```

Each item is traced by default, so a failing score links back to the run that
produced it. Pass `trace=False` when you do not want evaluation runs mixed into
your production version rollups.

### Against stored traces

No local execution: the server scores traces that already match a selector.

```python
run = lens.evaluate_traces(
    "production sweep v1.5.0",
    evaluators=["completed-without-error", "under-4s"],
    agent_name="support-agent",
    agent_version="v1.5.0",
    limit=200,
)
```

The dashboard's **Run on recent traces** panel does the same thing over HTTP.

## Comparing two runs

`GET /api/v1/evaluation-runs/{run_id}/compare?baseline={other_run_id}` returns:

- `metrics` — pass rate, average score, average latency, total cost, each with a
  delta and a regression flag
- `evaluator_deltas` — per-evaluator pass rate before and after
- `newly_failing` / `newly_passing` — the individual `(subject, evaluator)` pairs
  that flipped, with the reasoning attached
- `verdict` and `summary`

The verdict is `fail` when the pass rate drops more than `max_pass_rate_drop`
(default 5 points), `warn` when the overall rate holds but individual checks
regressed or latency/cost got materially worse, and `pass` otherwise. Both
tolerances are query parameters.

Metrics with data on only one side are reported without a verdict rather than
counted as a regression.

## Prompt versions

`POST /api/v1/projects/{project_id}/prompt-versions` stores a named template with
a version label and optional notes. Activating one deactivates the others with
the same name, so `is_active` always identifies the current template. Pass the
same label as `prompt_version` on your traces to line prompt changes up with the
quality and latency they produced — see [versions.md](versions.md).

## Endpoints

Dashboard (JWT):

- `GET /api/v1/evaluator-types`
- `GET|POST /api/v1/projects/{project_id}/datasets`
- `GET|PATCH|DELETE /api/v1/datasets/{dataset_id}`
- `GET|POST /api/v1/datasets/{dataset_id}/items`
- `GET|POST /api/v1/projects/{project_id}/evaluators`
- `PATCH|DELETE /api/v1/evaluators/{evaluator_id}`
- `GET|POST /api/v1/projects/{project_id}/evaluation-runs`
- `GET /api/v1/evaluation-runs/{run_id}`
- `GET /api/v1/evaluation-runs/{run_id}/results?only_failures=true`
- `GET /api/v1/evaluation-runs/{run_id}/compare?baseline={run_id}`
- `GET|POST /api/v1/projects/{project_id}/prompt-versions`

SDK (API key):

- `GET /api/v1/sdk/datasets`
- `GET|POST /api/v1/sdk/datasets/{name}/items` — POST creates the dataset if new
- `POST /api/v1/sdk/evaluation-runs`

## Limits

`MAX_EVALUATION_ITEMS` (default 2000) caps the subjects one run will score.
Evaluation runs execute inline in the request, so a large dataset with an LLM
judge will keep the connection open; keep CI runs to a few hundred items or
shard them.

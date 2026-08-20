# Versions and regression testing

Every trace can carry three optional labels:

| Label | Meaning |
|-------|---------|
| `agent_version` | The build of your agent, e.g. `v1.5.0` |
| `prompt_version` | The prompt template that produced the run, e.g. `support-reply-v4` |
| `model_version` | The model behind the run, e.g. `gpt-4o` |

Send them and the **Versions** page can roll production traffic up by any of
them and diff two values against each other. Send none and the page has nothing
to show, which is the most common reason it looks empty.

```python
with lens.trace(
    "support_ticket",
    agent_name="support-agent",
    agent_version="v1.5.0",
    prompt_version="support-reply-v4",
    model_version="gpt-4o",
) as trace:
    ...
```

## Rollup

`GET /api/v1/projects/{project_id}/versions?dimension=agent_version&range=30d`

Per distinct value, over the window: run count, success and error counts and
rates, average and p50/p95 latency, total and average tokens, total and average
cost, and first/last seen timestamps. `dimension` also accepts `prompt_version`,
`model_version`, and `agent_name`.

Percentiles are computed in the API from up to 50,000 sampled durations rather
than in SQL, so the numbers are identical on SQLite and PostgreSQL.

## Comparison

`GET /api/v1/projects/{project_id}/versions/compare?dimension=agent_version&baseline=v1.4.0&candidate=v1.5.0&range=30d`

Compares six metrics and returns a verdict:

| Metric | Direction | Default tolerance |
|--------|-----------|-------------------|
| `success_rate` | higher is better | 5 points absolute |
| `error_rate` | lower is better | 5 points absolute |
| `p95_latency_ms` | lower is better | 25% relative |
| `avg_latency_ms` | lower is better | 25% relative |
| `avg_cost` | lower is better | 25% relative |
| `avg_tokens` | lower is better | 25% relative |

- `fail` — a quality metric regressed (success rate or error rate)
- `warn` — quality held but latency, cost, or tokens got materially worse
- `pass` — nothing regressed beyond tolerance

Tolerances are query parameters: `max_success_rate_drop`, `max_latency_increase`,
`max_cost_increase`. Both versions need traces inside the window, otherwise the
request returns 404 naming the missing side.

## Two kinds of regression check

These are complementary and answer different questions:

**Version comparison** (this page) works on production traffic with no labels
required beyond the version string. It answers "did the deploy make things worse
for real users?" — success rate, latency, cost.

**Evaluation run comparison** (see [evaluations.md](evaluations.md)) works on a
fixed dataset with expected outputs. It answers "did quality drop on the cases we
care about?" and can point at the exact items that flipped.

Ship a version, watch the version comparison for latency and error regressions,
and gate the deploy itself on an evaluation run in CI.

## In the dashboard

`/versions` shows the rollup table with `base` / `cand` buttons on each row and a
regression card underneath. It defaults to the two most recently seen values, so
the newest build is compared against the one before it on first load.

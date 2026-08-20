"""Seed a running AgentLens with a believable demo workspace.

Creates (or reuses) a demo account, organization, project, and API key, then
writes backdated traces for two agent versions where the newer one is slower and
fails more often. Finishes by creating evaluators, a golden dataset, and four
evaluation runs so every dashboard page has something real to show.

Run the API first, then:

  python scripts/seed_demo.py

PowerShell with a custom target:

  python scripts/seed_demo.py --api-url http://localhost:8000 --days 10 --per-day 10

The script only talks to the public HTTP API, so it works against SQLite or
Postgres and against a remote deployment.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-sdk"))
sys.path.insert(0, str(ROOT / "examples"))

from agentlens import AgentLens  # noqa: E402
from demo_data import (  # noqa: E402
    GOLDEN_DATASET,
    MODELS,
    RAG_AGENT,
    RAG_QUESTIONS,
    SUPPORT_AGENT,
    TICKETS,
    golden_items,
    retrieve,
)

BASELINE_VERSION = "v1.4.0"
CANDIDATE_VERSION = "v1.5.0"
BASELINE_PROMPT = "support-reply-v3"
CANDIDATE_PROMPT = "support-reply-v4"

HEDGE = "I could not find that in the Northwind help centre."

# Production traces carry no reference answer, so only the checks that work on
# an unlabelled run are used there. Similarity and the judge belong to the
# golden dataset, where every item has an expected output.
TRACE_EVALUATORS = ["completed-without-error", "under-4s", "no-hedging"]

EVALUATORS: list[dict[str, Any]] = [
    {
        "name": "answer-similarity",
        "evaluator_type": "similarity",
        "description": "Token overlap against the golden answer.",
        "threshold": 0.6,
    },
    {
        "name": "states-the-fact",
        "evaluator_type": "contains",
        "description": "The reply must repeat the key fact from the playbook.",
        "config": {"value": "", "case_sensitive": False},
    },
    {
        "name": "no-hedging",
        "evaluator_type": "not_contains",
        "description": "Catch generic non-answers that dodge the question.",
        "config": {"value": "looking into it", "case_sensitive": False},
    },
    {
        "name": "completed-without-error",
        "evaluator_type": "no_error",
        "description": "The run itself must not end in an error.",
    },
    {
        "name": "under-4s",
        "evaluator_type": "latency_under",
        "description": "Support replies should land inside four seconds.",
        "config": {"max_ms": 4000},
    },
    {
        "name": "helpfulness-judge",
        "evaluator_type": "llm_judge",
        "description": "Scores the reply for accuracy and completeness.",
        "threshold": 0.6,
        "config": {
            "criteria": (
                "The reply answers the customer's question directly, states the specific "
                "fact (order status, policy window, claim id, or date), and does not "
                "promise a follow-up instead of answering."
            )
        },
    },
]


class Seeder:
    """Thin API client with retry-on-rate-limit and small helpers."""

    def __init__(self, base_url: str, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=60.0)
        self.token: str | None = None
        self.verbose = verbose

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Seeder":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def call(
        self,
        method: str,
        path: str,
        payload: Any = None,
        *,
        token: str | None = None,
        params: dict[str, Any] | None = None,
        allow: tuple[int, ...] = (),
    ) -> tuple[int, Any]:
        """Send one request, retrying while the API is rate limiting us."""

        url = f"{self.base_url}/api/v1{path}"
        headers = {"Content-Type": "application/json"}
        bearer = token or self.token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        for attempt in range(6):
            try:
                response = self.client.request(
                    method, url, json=payload, params=params, headers=headers
                )
            except httpx.HTTPError as exc:
                raise SystemExit(f"Cannot reach {url}: {exc}. Is the API running?") from exc

            if response.status_code == 429:
                wait = float(response.headers.get("retry-after") or 2 * (attempt + 1))
                if self.verbose:
                    print(f"    rate limited, waiting {wait:.0f}s")
                time.sleep(wait)
                continue
            break

        body: Any = None
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = response.text

        if response.status_code >= 400 and response.status_code not in allow:
            detail = body.get("detail") if isinstance(body, dict) else body
            raise SystemExit(f"{method} {path} failed ({response.status_code}): {detail}")
        return response.status_code, body

    # ------------------------------------------------------------------ setup

    def login(self, email: str, password: str, full_name: str) -> None:
        status, _ = self.call(
            "POST",
            "/auth/signup",
            {"email": email, "password": password, "full_name": full_name},
            allow=(400, 409),
        )
        if status < 400:
            print(f"Created account {email}")
        else:
            print(f"Reusing existing account {email}")

        _, tokens = self.call("POST", "/auth/login", {"email": email, "password": password})
        self.token = tokens["access_token"]

    def ensure_org(self, name: str) -> dict[str, Any]:
        _, orgs = self.call("GET", "/organizations")
        for org in orgs:
            if org["name"] == name:
                return org
        if orgs:
            # Rename the personal organization the signup created rather than
            # leaving the demo user with two workspaces.
            _, org = self.call("PATCH", f"/organizations/{orgs[0]['id']}", {"name": name})
            return org
        _, org = self.call("POST", "/organizations", {"name": name})
        return org

    def ensure_project(self, org_id: str, name: str) -> dict[str, Any]:
        _, projects = self.call("GET", f"/organizations/{org_id}/projects")
        for project in projects:
            if project["name"] == name:
                return project
        _, project = self.call(
            "POST",
            f"/organizations/{org_id}/projects",
            {"name": name, "description": "Seeded demo workspace for AgentLens"},
        )
        return project

    def create_api_key(self, project_id: str) -> str:
        _, created = self.call(
            "POST",
            f"/projects/{project_id}/api-keys",
            {"name": f"demo-seed-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"},
        )
        return created["secret"]

    def ensure_evaluators(self, project_id: str) -> list[str]:
        _, existing = self.call("GET", f"/projects/{project_id}/evaluators")
        have = {item["name"] for item in existing}
        names: list[str] = []
        for spec in EVALUATORS:
            names.append(spec["name"])
            if spec["name"] in have:
                continue
            self.call("POST", f"/projects/{project_id}/evaluators", spec, allow=(400,))
        return names

    def ensure_dataset(self, project_id: str, name: str) -> str:
        _, datasets = self.call("GET", f"/projects/{project_id}/datasets")
        dataset = next((item for item in datasets if item["name"] == name), None)
        if dataset is None:
            _, dataset = self.call(
                "POST",
                f"/projects/{project_id}/datasets",
                {"name": name, "description": "Golden support answers used by CI."},
            )
        self.call(
            "POST",
            f"/datasets/{dataset['id']}/items",
            {"items": golden_items(), "replace": True},
        )
        return dataset["id"]


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


class TraceWriter:
    """Writes backdated traces with the project API key.

    The SDK context managers stamp `now()`, which is right for a live agent but
    wrong for seeding history, so the payloads are posted directly with explicit
    timestamps. Ingest recomputes trace duration from start/end, so every span
    end time is derived from its start plus the simulated latency.
    """

    def __init__(self, seeder: Seeder, api_key: str):
        self.seeder = seeder
        self.api_key = api_key
        self.count = 0

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        _, body = self.seeder.call("POST", path, payload, token=self.api_key)
        return body

    def support_trace(
        self,
        started: datetime,
        ticket: dict[str, Any],
        *,
        agent_version: str,
        prompt_version: str,
        session_id: str,
        latency_scale: float,
        failed: bool,
        degraded: bool,
    ) -> UUID:
        trace_id = uuid4()
        classify_ms = int(180 * latency_scale)
        tool_ms = int(620 * latency_scale)
        writer_ms = int(900 * latency_scale)

        cursor = started
        self.post(
            "/traces",
            {
                "id": str(trace_id),
                "name": "support_ticket",
                "agent_name": SUPPORT_AGENT,
                "session_id": session_id,
                "status": "running",
                "start_time": _iso(started),
                "input": {"question": ticket["question"]},
                "metadata": {"intent": ticket["intent"], "channel": "email"},
                "agent_version": agent_version,
                "prompt_version": prompt_version,
                "model_version": MODELS["writer"],
            },
        )

        classify_span = uuid4()
        self.post(
            "/spans",
            {
                "id": str(classify_span),
                "trace_id": str(trace_id),
                "type": "LLM",
                "name": "classify_intent",
                "status": "success",
                "start_time": _iso(cursor),
                "end_time": _iso(cursor + timedelta(milliseconds=classify_ms)),
            },
        )
        self.post(
            "/llm-calls",
            {
                "trace_id": str(trace_id),
                "span_id": str(classify_span),
                "provider": "openai",
                "model": MODELS["classifier"],
                "messages": [{"role": "user", "content": ticket["question"]}],
                "completion": {"intent": ticket["intent"], "confidence": 0.94},
                "input_tokens": 140,
                "output_tokens": 12,
                "latency_ms": classify_ms,
                "temperature": 0.0,
            },
        )
        cursor += timedelta(milliseconds=classify_ms)

        work_span = uuid4()
        work_end = cursor + timedelta(milliseconds=tool_ms)
        self.post(
            "/spans",
            {
                "id": str(work_span),
                "trace_id": str(trace_id),
                "type": "AGENT",
                "name": "resolve_request",
                "status": "error" if failed else "success",
                "start_time": _iso(cursor),
                "end_time": _iso(work_end),
                "output": None if failed else {"resolved": True, "tool": ticket["tool"]},
                "error_type": "ToolTimeout" if failed else None,
                "error_message": f"{ticket['tool']} timed out" if failed else None,
            },
        )
        tool_span = uuid4()
        self.post(
            "/spans",
            {
                "id": str(tool_span),
                "trace_id": str(trace_id),
                "parent_span_id": str(work_span),
                "type": "TOOL",
                "name": ticket["tool"],
                "status": "error" if failed else "success",
                "start_time": _iso(cursor),
                "end_time": _iso(work_end),
                "input": ticket["tool_args"],
                "output": None if failed else ticket["tool_result"],
                "error_type": "ToolTimeout" if failed else None,
                "error_message": f"{ticket['tool']} timed out after 3 attempts" if failed else None,
            },
        )
        self.post(
            "/tool-calls",
            {
                "trace_id": str(trace_id),
                "span_id": str(tool_span),
                "name": ticket["tool"],
                "arguments": ticket["tool_args"],
                "output": None if failed else ticket["tool_result"],
                "status": "error" if failed else "success",
                "duration_ms": tool_ms,
                "error": f"{ticket['tool']} timed out after 3 attempts" if failed else None,
                "retry_count": 3 if failed else 0,
            },
        )
        cursor = work_end

        if failed:
            self.post(
                "/events",
                {
                    "trace_id": str(trace_id),
                    "span_id": str(tool_span),
                    "name": "tool_failed",
                    "body": {"tool": ticket["tool"]},
                    "timestamp": _iso(cursor),
                },
            )
            self.post(
                "/traces",
                {
                    "id": str(trace_id),
                    "name": "support_ticket",
                    "agent_name": SUPPORT_AGENT,
                    "status": "error",
                    "start_time": _iso(started),
                    "end_time": _iso(cursor),
                    "error_type": "ToolTimeout",
                    "error_message": f"{ticket['tool']} timed out after 3 attempts",
                    "agent_version": agent_version,
                    "prompt_version": prompt_version,
                },
            )
            self.count += 1
            return trace_id

        answer = (
            "Thanks for reaching out. Our team is looking into it."
            if degraded
            else ticket["answer"]
        )
        writer_span = uuid4()
        writer_end = cursor + timedelta(milliseconds=writer_ms)
        self.post(
            "/spans",
            {
                "id": str(writer_span),
                "trace_id": str(trace_id),
                "type": "LLM",
                "name": "draft_reply",
                "status": "success",
                "start_time": _iso(cursor),
                "end_time": _iso(writer_end),
                "output": answer,
            },
        )
        self.post(
            "/llm-calls",
            {
                "trace_id": str(trace_id),
                "span_id": str(writer_span),
                "provider": "openai",
                "model": MODELS["writer"],
                "messages": [
                    {"role": "system", "content": f"Reply to the customer. Prompt {prompt_version}."},
                    {"role": "user", "content": ticket["question"]},
                    {"role": "tool", "content": str(ticket["tool_result"])},
                ],
                "completion": answer,
                "input_tokens": 520 if not degraded else 380,
                "output_tokens": 90 if not degraded else 24,
                "latency_ms": writer_ms,
                "temperature": 0.2,
            },
        )
        self.post(
            "/events",
            {
                "trace_id": str(trace_id),
                "name": "reply_sent",
                "body": {"length": len(answer)},
                "timestamp": _iso(writer_end),
            },
        )
        self.post(
            "/traces",
            {
                "id": str(trace_id),
                "name": "support_ticket",
                "agent_name": SUPPORT_AGENT,
                "status": "success",
                "start_time": _iso(started),
                "end_time": _iso(writer_end),
                "output": answer,
                "agent_version": agent_version,
                "prompt_version": prompt_version,
            },
        )
        self.count += 1
        return trace_id

    def rag_trace(self, started: datetime, case: dict[str, Any], *, agent_version: str) -> UUID:
        trace_id = uuid4()
        docs = retrieve(case["question"])
        best = docs[0] if docs else None
        grounded = bool(best) and best["score"] >= 0.2
        answer = best["text"] if grounded else HEDGE

        retrieve_ms, generate_ms = 140, 760
        end = started + timedelta(milliseconds=retrieve_ms + generate_ms)

        self.post(
            "/traces",
            {
                "id": str(trace_id),
                "name": "docs_question",
                "agent_name": RAG_AGENT,
                "status": "success",
                "start_time": _iso(started),
                "end_time": _iso(end),
                "input": {"question": case["question"]},
                "output": answer,
                "metadata": {"case": case["name"], "grounded": grounded},
                "agent_version": agent_version,
                "model_version": MODELS["writer"],
            },
        )
        retrieval_span = uuid4()
        self.post(
            "/spans",
            {
                "id": str(retrieval_span),
                "trace_id": str(trace_id),
                "type": "RETRIEVAL",
                "name": "retrieve",
                "status": "success",
                "start_time": _iso(started),
                "end_time": _iso(started + timedelta(milliseconds=retrieve_ms)),
                "input": {"question": case["question"]},
                "output": {"hits": [{"id": d["id"], "score": d["score"]} for d in docs]},
                "metadata": {"index": "kb-northwind", "embedder": MODELS["embedder"]},
            },
        )
        generate_span = uuid4()
        self.post(
            "/spans",
            {
                "id": str(generate_span),
                "trace_id": str(trace_id),
                "type": "LLM",
                "name": "generate_answer",
                "status": "success",
                "start_time": _iso(started + timedelta(milliseconds=retrieve_ms)),
                "end_time": _iso(end),
                "output": answer,
            },
        )
        self.post(
            "/llm-calls",
            {
                "trace_id": str(trace_id),
                "span_id": str(generate_span),
                "provider": "openai",
                "model": MODELS["writer"],
                "messages": [{"role": "user", "content": case["question"]}],
                "completion": answer,
                "input_tokens": 260 + 40 * len(docs),
                "output_tokens": len(answer.split()) * 2,
                "latency_ms": generate_ms,
                "temperature": 0.1,
            },
        )
        if not grounded:
            self.post(
                "/events",
                {
                    "trace_id": str(trace_id),
                    "name": "no_context",
                    "body": {"question": case["question"]},
                    "timestamp": _iso(end),
                },
            )
        self.count += 1
        return trace_id


def seed_history(writer: TraceWriter, days: int, per_day: int, rng: random.Random) -> None:
    """Write `days * per_day` support traces, regressing on the final third."""

    now = datetime.now(timezone.utc)
    switch_day = max(1, days // 3)  # the newest third runs the candidate build

    for day_offset in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=day_offset)).replace(minute=0, second=0, microsecond=0)
        is_candidate = day_offset < switch_day
        version = CANDIDATE_VERSION if is_candidate else BASELINE_VERSION
        prompt = CANDIDATE_PROMPT if is_candidate else BASELINE_PROMPT
        error_rate = 0.16 if is_candidate else 0.04
        degrade_rate = 0.3 if is_candidate else 0.0
        latency_scale = 1.9 if is_candidate else 1.0

        for index in range(per_day):
            # Spread runs across a working day, oldest first.
            offset_minutes = rng.randrange(9 * 60, 19 * 60)
            started = day_start.replace(hour=0) + timedelta(minutes=offset_minutes)
            if started > now:
                started = now - timedelta(minutes=rng.randrange(1, 120))
            ticket = TICKETS[(day_offset * per_day + index) % len(TICKETS)]
            writer.support_trace(
                started,
                ticket,
                agent_version=version,
                prompt_version=prompt,
                session_id=f"sess-{day_offset:02d}-{index:02d}",
                latency_scale=latency_scale * rng.uniform(0.8, 1.25),
                failed=rng.random() < error_rate,
                degraded=rng.random() < degrade_rate,
            )
        print(f"  day -{day_offset:<2} {version}: {per_day} traces")

    for index, case in enumerate(RAG_QUESTIONS):
        writer.rag_trace(now - timedelta(hours=index + 1), case, agent_version="rag-v0.3.0")
    print(f"  rag agent: {len(RAG_QUESTIONS)} traces")


def dataset_runs(api_key: str, base_url: str) -> None:
    """Produce two comparable dataset runs through the public SDK path.

    Tracing is off here so the version rollup keeps showing production traffic
    only; ``examples/evaluate_agent.py`` leaves it on to demonstrate the link
    from a failing score back to the trace that produced it.
    """

    by_question = {ticket["question"]: ticket for ticket in TICKETS}
    # A fixed subset regresses, so the comparison view always has the same
    # "newly failing" rows no matter when the seeder runs.
    regressed = {ticket["question"] for index, ticket in enumerate(TICKETS) if index % 2 == 0}

    def answer(item: Any) -> str:
        ticket = by_question.get(str(item.input))
        return str(ticket["answer"]) if ticket else "I do not have that information."

    def degraded_answer(item: Any) -> str:
        question = str(item.input)
        if question in regressed:
            return "Thanks for reaching out. Our team is looking into it."
        return answer(item)

    with AgentLens(api_key=api_key, base_url=base_url) as lens:
        baseline = lens.evaluate(
            GOLDEN_DATASET,
            answer,
            name=f"golden {BASELINE_PROMPT}",
            agent_name=SUPPORT_AGENT,
            agent_version=BASELINE_VERSION,
            prompt_version=BASELINE_PROMPT,
            trace=False,
        )
        print(f"  baseline run: {baseline}")
        candidate = lens.evaluate(
            GOLDEN_DATASET,
            degraded_answer,
            name=f"golden {CANDIDATE_PROMPT}",
            agent_name=SUPPORT_AGENT,
            agent_version=CANDIDATE_VERSION,
            prompt_version=CANDIDATE_PROMPT,
            trace=False,
        )
        print(f"  candidate run: {candidate}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed AgentLens with demo data")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--web-url", default="http://localhost:3000")
    parser.add_argument("--email", default="demo@agentlens.dev")
    parser.add_argument("--password", default="DemoPassword123!")
    parser.add_argument("--full-name", default="AgentLens Demo")
    parser.add_argument("--org", default="Northwind AI")
    parser.add_argument("--project", default="Support Agent")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-day", type=int, default=8)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--skip-history", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    with Seeder(args.api_url, verbose=args.verbose) as seeder:
        seeder.login(args.email, args.password, args.full_name)
        _, health = seeder.call("GET", "/system/info")

        org = seeder.ensure_org(args.org)
        project = seeder.ensure_project(org["id"], args.project)
        print(f"Using organization '{org['name']}' and project '{project['name']}'")

        api_key = seeder.create_api_key(project["id"])
        print(f"Created API key {api_key[:12]}...")

        names = seeder.ensure_evaluators(project["id"])
        print(f"Evaluators ready: {', '.join(names)}")

        seeder.ensure_dataset(project["id"], GOLDEN_DATASET)
        print(f"Dataset '{GOLDEN_DATASET}' loaded with {len(golden_items())} items")

        if not args.skip_history:
            print(f"Writing {args.days * args.per_day} support traces plus RAG traces...")
            writer = TraceWriter(seeder, api_key)
            seed_history(writer, args.days, args.per_day, rng)
            print(f"Wrote {writer.count} traces")

        print("Scoring stored traces per version...")
        for version in (BASELINE_VERSION, CANDIDATE_VERSION):
            _, run = seeder.call(
                "POST",
                f"/projects/{project['id']}/evaluation-runs",
                {
                    "name": f"production traces {version}",
                    "target": "traces",
                    "agent_version": version,
                    "evaluator_names": TRACE_EVALUATORS,
                    "selector": {
                        "agent_name": SUPPORT_AGENT,
                        "agent_version": version,
                        "limit": 200,
                    },
                },
                allow=(400,),
            )
            if isinstance(run, dict) and run.get("total_items"):
                print(
                    f"  {version}: {run['passed_count']}/{run['total_items']} passed "
                    f"({run['pass_rate']:.1%})"
                )
            else:
                print(f"  {version}: nothing to score")

        print("Running the golden dataset through the SDK...")
        dataset_runs(api_key, args.api_url)

    print("\nDemo workspace ready.")
    print(f"  Dashboard : {args.web_url}/dashboard")
    print(f"  Sign in   : {args.email} / {args.password}")
    print(f"  API key   : {api_key}")
    print("\nNext:")
    print(f'  $env:AGENTLENS_API_KEY = "{api_key}"')
    print("  python examples/support_agent.py --runs 12   # watch /traces update live")
    print("  python examples/evaluate_agent.py --degrade  # see a quality gate fail")
    if isinstance(health, dict) and not health.get("judge_configured", True):
        print("\nNote: OPENAI_API_KEY is not set, so llm_judge used its offline heuristic.")


if __name__ == "__main__":
    main()

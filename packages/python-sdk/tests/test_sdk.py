import json

import pytest

from agentlens import AgentLens, AgentLensError, DatasetItem, EvaluationFailed


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode() if payload is not None else b""
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        return self._payload


class FakeApi:
    """Stands in for the AgentLens HTTP API.

    It records every call and mimics the parts of the real contract the SDK
    depends on: ingest echoes back server-computed totals, dataset reads return
    items, and evaluation runs are scored with exact match.
    """

    def __init__(self, dataset_items=None, status_code=200):
        self.calls: list[dict] = []
        self.status_code = status_code
        self.dataset_items = dataset_items or []

    @property
    def paths(self) -> list[str]:
        return [call["path"] for call in self.calls]

    def request(self, method, url, json=None, headers=None, params=None):
        path = url.split("/api/v1")[-1]
        self.calls.append(
            {"method": method, "path": path, "json": json, "headers": headers, "params": params}
        )
        if self.status_code >= 400:
            return FakeResponse({"detail": "nope"}, status_code=self.status_code)
        return FakeResponse(self._route(method, path, json or {}))

    def _route(self, method, path, payload):
        if path == "/sdk/verify":
            return {"project_id": "p1", "project_name": "Support", "key_name": "ci"}
        if path == "/traces":
            return {
                "id": payload.get("id"),
                "name": payload.get("name"),
                "status": payload.get("status", "running"),
                "total_tokens": 150,
                "total_cost": "0.0042",
            }
        if path.endswith("/items") and method == "GET":
            return self.dataset_items
        if path.endswith("/items") and method == "POST":
            return [
                {"id": f"item-{index}", **item}
                for index, item in enumerate(payload.get("items", []))
            ]
        if path == "/sdk/evaluation-runs":
            return self._score(payload)
        return {"id": payload.get("id"), "trace_id": payload.get("trace_id")}

    def _score(self, payload):
        outputs = payload.get("outputs") or []
        expected = {item.get("name"): item.get("expected_output") for item in self.dataset_items}
        passed = sum(
            1
            for output in outputs
            if output.get("status") == "success"
            and output.get("output") == expected.get(output.get("item_name"))
        )
        total = len(outputs)
        return {
            "id": "run-1",
            "name": payload.get("name"),
            "status": "completed",
            "dataset_name": payload.get("dataset_name"),
            "agent_version": payload.get("agent_version"),
            "total_items": total,
            "passed_count": passed,
            "failed_count": total - passed,
            "pass_rate": (passed / total) if total else 0.0,
            "avg_score": (passed / total) if total else 0.0,
            "total_cost": "0.0084",
        }

    def close(self):
        return None


ITEMS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "order-status",
        "input": {"message": "Where is my order?"},
        "expected_output": "Ships tomorrow.",
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "refund-policy",
        "input": {"message": "Refund?"},
        "expected_output": "Within 30 days.",
    },
]


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("AGENTLENS_API_KEY", raising=False)
    with pytest.raises(AgentLensError):
        AgentLens()


def test_api_key_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("AGENTLENS_API_KEY", "al_from_env")
    monkeypatch.setenv("AGENTLENS_API_URL", "https://agentlens.example.com/")
    lens = AgentLens(client=FakeApi())
    assert lens.api_key == "al_from_env"
    assert lens.base_url == "https://agentlens.example.com"


def test_trace_span_llm_tool_and_error():
    api = FakeApi()
    lens = AgentLens(api_key="al_test", base_url="http://localhost:8000", client=api)

    with lens.trace("customer_support_task", agent_name="support", input={"q": "hi"}) as trace:
        with trace.span("planning") as span:
            span.set_output({"plan": "search"})
        with trace.llm_call(
            model="gpt-4o",
            input_tokens=10,
            messages=[{"role": "user", "content": "hi"}],
        ) as call:
            call.set_completion("ok")
            call.set_usage(output_tokens=4)
        with trace.tool_call("search", {"query": "order"}) as tool:
            tool.set_output({"hits": 1})
        trace.set_output("done")

    assert api.paths[0] == "/traces"
    assert "/spans" in api.paths
    assert "/llm-calls" in api.paths
    assert "/tool-calls" in api.paths
    assert api.paths[-1] == "/traces"
    assert api.calls[0]["headers"]["Authorization"] == "Bearer al_test"
    assert api.calls[-1]["json"]["status"] == "success"
    assert api.calls[-1]["json"]["output"] == "done"
    assert trace.total_cost == pytest.approx(0.0042)
    assert trace.total_tokens == 150

    failing = FakeApi()
    lens2 = AgentLens(api_key="al_test", client=failing)
    with pytest.raises(RuntimeError):
        with lens2.trace("failing"):
            raise RuntimeError("boom")
    assert failing.calls[-1]["json"]["status"] == "error"
    assert failing.calls[-1]["json"]["error_message"] == "boom"


def test_mark_error_keeps_status_on_handled_failures():
    api = FakeApi()
    lens = AgentLens(api_key="al_test", client=api)
    with lens.trace("handled") as trace:
        try:
            raise ValueError("bad input")
        except ValueError as exc:
            trace.mark_error(exc)

    final = api.calls[-1]["json"]
    assert final["status"] == "error"
    assert final["error_type"] == "ValueError"
    assert final["error_message"] == "bad input"


def test_http_errors_become_agentlens_errors():
    lens = AgentLens(api_key="al_test", client=FakeApi(status_code=401))
    with pytest.raises(AgentLensError) as excinfo:
        lens.verify()
    assert "401" in str(excinfo.value)


def test_observe_decorator_traces_each_call():
    api = FakeApi()
    lens = AgentLens(api_key="al_test", client=api)

    @lens.observe(agent_name="support", agent_version="v3")
    def answer(question: str) -> str:
        return f"answer to {question}"

    assert answer("where is my order") == "answer to where is my order"
    opened, closed = api.calls[0]["json"], api.calls[1]["json"]
    assert opened["name"] == "answer"
    assert opened["agent_name"] == "support"
    assert opened["agent_version"] == "v3"
    assert opened["input"] == {"args": ["where is my order"], "kwargs": {}}
    assert closed["status"] == "success"
    assert closed["output"] == "answer to where is my order"


def test_observe_decorator_records_exceptions():
    api = FakeApi()
    lens = AgentLens(api_key="al_test", client=api)

    @lens.observe()
    def explode() -> None:
        raise KeyError("missing")

    with pytest.raises(KeyError):
        explode()
    assert api.calls[-1]["json"]["status"] == "error"
    assert api.calls[-1]["json"]["error_type"] == "KeyError"


def test_get_dataset_returns_typed_items():
    api = FakeApi(dataset_items=ITEMS)
    lens = AgentLens(api_key="al_test", client=api)

    items = lens.get_dataset("support-golden")
    assert [item.name for item in items] == ["order-status", "refund-policy"]
    assert items[0].expected_output == "Ships tomorrow."
    assert str(items[0].id) == "11111111-1111-1111-1111-111111111111"
    assert api.calls[0]["params"] == {"limit": 500}


def test_upload_dataset_accepts_dicts_and_items():
    api = FakeApi()
    lens = AgentLens(api_key="al_test", client=api)

    created = lens.upload_dataset(
        "regression",
        [
            {"name": "a", "input": "x", "expected_output": "y"},
            DatasetItem(id=None, name="b", input="p", expected_output="q"),
        ],
        replace=True,
    )
    assert len(created) == 2
    body = api.calls[0]["json"]
    assert body["replace"] is True
    assert body["items"][1]["name"] == "b"

    with pytest.raises(AgentLensError):
        lens.upload_dataset("regression", [])


def test_evaluate_runs_agent_locally_and_submits_outputs():
    api = FakeApi(dataset_items=ITEMS)
    lens = AgentLens(api_key="al_test", client=api)

    answers = {"order-status": "Ships tomorrow.", "refund-policy": "No idea."}

    run = lens.evaluate(
        "support-golden",
        lambda item: answers[item.name],
        name="ci",
        evaluators=["exact"],
        agent_version="v2",
    )

    assert run.total_items == 2
    assert run.passed_count == 1
    assert run.pass_rate == pytest.approx(0.5)
    assert "1/2 passed" in str(run)

    submitted = api.calls[-1]
    assert submitted["path"] == "/sdk/evaluation-runs"
    assert submitted["json"]["evaluator_names"] == ["exact"]
    assert submitted["json"]["agent_version"] == "v2"
    outputs = submitted["json"]["outputs"]
    assert len(outputs) == 2
    assert all(output["trace_id"] for output in outputs)
    assert all(output["cost"] == pytest.approx(0.0042) for output in outputs)
    assert api.paths.count("/traces") == 4  # one open + one close per item


def test_evaluate_records_agent_exceptions_as_failed_items():
    api = FakeApi(dataset_items=ITEMS)
    lens = AgentLens(api_key="al_test", client=api)

    def flaky(item):
        if item.name == "refund-policy":
            raise TimeoutError("model timeout")
        return "Ships tomorrow."

    run = lens.evaluate("support-golden", flaky)
    assert run.passed_count == 1

    outputs = api.calls[-1]["json"]["outputs"]
    failed = next(output for output in outputs if output["item_name"] == "refund-policy")
    assert failed["status"] == "error"
    assert failed["error_message"] == "model timeout"


def test_evaluate_can_skip_tracing():
    api = FakeApi(dataset_items=ITEMS)
    lens = AgentLens(api_key="al_test", client=api)
    lens.evaluate("support-golden", lambda item: "x", trace=False)
    assert "/traces" not in api.paths


def test_evaluate_requires_a_populated_dataset():
    lens = AgentLens(api_key="al_test", client=FakeApi(dataset_items=[]))
    with pytest.raises(AgentLensError):
        lens.evaluate("empty", lambda item: "x")


def test_require_pass_rate_gates_ci():
    api = FakeApi(dataset_items=ITEMS)
    lens = AgentLens(api_key="al_test", client=api)
    run = lens.evaluate("support-golden", lambda item: item.expected_output)
    assert run.require_pass_rate(1.0) is run

    lowered = lens.evaluate("support-golden", lambda item: "wrong")
    with pytest.raises(EvaluationFailed) as excinfo:
        lowered.require_pass_rate(0.9)
    assert "below the required" in str(excinfo.value)


def test_evaluate_traces_sends_a_selector():
    api = FakeApi(dataset_items=ITEMS)
    lens = AgentLens(api_key="al_test", client=api)
    lens.evaluate_traces("prod sweep", evaluators=["clean"], agent_name="support", limit=25)

    body = api.calls[-1]["json"]
    assert body["target"] == "traces"
    assert body["selector"]["agent_name"] == "support"
    assert body["selector"]["limit"] == 25
    assert body["evaluator_names"] == ["clean"]


def test_non_serialisable_values_do_not_break_tracing():
    api = FakeApi()
    lens = AgentLens(api_key="al_test", client=api)

    class Opaque:
        def __repr__(self) -> str:
            return "<Opaque>"

    with lens.trace("weird", input={"obj": Opaque()}) as trace:
        trace.set_output({"obj": Opaque()})

    assert api.calls[0]["json"]["input"] == {"obj": "<Opaque>"}
    assert api.calls[-1]["json"]["output"] == {"obj": "<Opaque>"}

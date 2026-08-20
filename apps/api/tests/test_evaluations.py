from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.helpers import Workspace, create_workspace

DATASET_ITEMS = [
    {
        "name": "order-status",
        "input": {"message": "Where is my order?"},
        "expected_output": "Your order ships tomorrow.",
    },
    {
        "name": "refund-policy",
        "input": {"message": "Can I get a refund?"},
        "expected_output": "Refunds are available within 30 days.",
    },
]


async def _dataset_with_items(client: AsyncClient, ws: Workspace, name: str = "support-golden") -> str:
    created = await client.post(
        f"/api/v1/projects/{ws.project_id}/datasets",
        headers=ws.auth,
        json={"name": name, "description": "Golden answers for the support agent"},
    )
    assert created.status_code == 201, created.text
    dataset_id = created.json()["id"]

    items = await client.post(
        f"/api/v1/datasets/{dataset_id}/items",
        headers=ws.auth,
        json={"items": DATASET_ITEMS},
    )
    assert items.status_code == 201, items.text
    return dataset_id


async def _evaluator(client: AsyncClient, ws: Workspace, payload: dict) -> str:
    created = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluators",
        headers=ws.auth,
        json=payload,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


@pytest.mark.asyncio
async def test_evaluator_types_are_listed(client: AsyncClient):
    ws = await create_workspace(client, "eval-types@agentlens.dev")
    response = await client.get("/api/v1/evaluator-types", headers=ws.auth)
    assert response.status_code == 200
    types = {item["type"] for item in response.json()}
    assert {"exact_match", "similarity", "llm_judge", "no_error"} <= types
    judge = next(item for item in response.json() if item["type"] == "llm_judge")
    assert judge["default_threshold"] == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_dataset_crud_and_item_listing(client: AsyncClient):
    ws = await create_workspace(client, "dataset-crud@agentlens.dev")
    dataset_id = await _dataset_with_items(client, ws)

    listed = await client.get(f"/api/v1/projects/{ws.project_id}/datasets", headers=ws.auth)
    assert listed.status_code == 200
    assert listed.json()[0]["item_count"] == 2

    renamed = await client.patch(
        f"/api/v1/datasets/{dataset_id}",
        headers=ws.auth,
        json={"name": "support-golden-v2"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "support-golden-v2"
    assert renamed.json()["item_count"] == 2

    items = await client.get(f"/api/v1/datasets/{dataset_id}/items", headers=ws.auth)
    assert [item["name"] for item in items.json()] == ["order-status", "refund-policy"]

    replaced = await client.post(
        f"/api/v1/datasets/{dataset_id}/items",
        headers=ws.auth,
        json={"items": [DATASET_ITEMS[0]], "replace": True},
    )
    assert replaced.status_code == 201
    after = await client.get(f"/api/v1/datasets/{dataset_id}/items", headers=ws.auth)
    assert len(after.json()) == 1

    duplicate = await client.post(
        f"/api/v1/projects/{ws.project_id}/datasets",
        headers=ws.auth,
        json={"name": "support-golden-v2"},
    )
    assert duplicate.status_code == 400

    deleted = await client.delete(f"/api/v1/datasets/{dataset_id}", headers=ws.auth)
    assert deleted.status_code == 204
    gone = await client.get(f"/api/v1/datasets/{dataset_id}", headers=ws.auth)
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_evaluator_validation_rejects_bad_config(client: AsyncClient):
    ws = await create_workspace(client, "eval-config@agentlens.dev")
    bad = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluators",
        headers=ws.auth,
        json={"name": "broken", "evaluator_type": "regex", "config": {"pattern": "([unclosed"}},
    )
    assert bad.status_code == 400
    assert "regex" in bad.json()["detail"].lower()

    unsupported = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluators",
        headers=ws.auth,
        json={"name": "nope", "evaluator_type": "telepathy"},
    )
    assert unsupported.status_code == 422


@pytest.mark.asyncio
async def test_evaluator_defaults_and_updates(client: AsyncClient):
    ws = await create_workspace(client, "eval-update@agentlens.dev")
    evaluator_id = await _evaluator(
        client,
        ws,
        {"name": "similar-enough", "evaluator_type": "similarity"},
    )

    created = await client.get(f"/api/v1/projects/{ws.project_id}/evaluators", headers=ws.auth)
    body = created.json()[0]
    assert body["threshold"] == pytest.approx(0.8)
    assert body["is_active"] is True

    updated = await client.patch(
        f"/api/v1/evaluators/{evaluator_id}",
        headers=ws.auth,
        json={"threshold": 0.6, "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["threshold"] == pytest.approx(0.6)
    assert updated.json()["is_active"] is False

    active_only = await client.get(
        f"/api/v1/projects/{ws.project_id}/evaluators",
        headers=ws.auth,
        params={"active_only": True},
    )
    assert active_only.json() == []

    removed = await client.delete(f"/api/v1/evaluators/{evaluator_id}", headers=ws.auth)
    assert removed.status_code == 204


@pytest.mark.asyncio
async def test_dataset_run_scores_submitted_outputs(client: AsyncClient):
    ws = await create_workspace(client, "eval-run@agentlens.dev")
    dataset_id = await _dataset_with_items(client, ws)
    await _evaluator(client, ws, {"name": "exact", "evaluator_type": "exact_match"})
    await _evaluator(client, ws, {"name": "fast", "evaluator_type": "latency_under", "config": {"max_ms": 2000}})

    items = (await client.get(f"/api/v1/datasets/{dataset_id}/items", headers=ws.auth)).json()
    by_name = {item["name"]: item["id"] for item in items}

    run = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluation-runs",
        headers=ws.auth,
        json={
            "name": "nightly",
            "target": "dataset",
            "dataset_id": dataset_id,
            "agent_version": "v1",
            "outputs": [
                {
                    "dataset_item_id": by_name["order-status"],
                    "output": "Your order ships tomorrow.",
                    "duration_ms": 900,
                    "cost": "0.001",
                },
                {
                    "dataset_item_id": by_name["refund-policy"],
                    "output": "I am not sure.",
                    "duration_ms": 4200,
                    "cost": "0.004",
                },
            ],
        },
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "completed"
    assert body["total_items"] == 2
    assert body["passed_count"] == 1
    assert body["failed_count"] == 1
    assert body["pass_rate"] == pytest.approx(0.5)
    assert float(body["total_cost"]) == pytest.approx(0.005)

    scores = {item["evaluator_name"]: item for item in body["evaluator_scores"]}
    assert scores["exact"]["passed"] == 1
    assert scores["fast"]["passed"] == 1
    labels = {item["label"] for item in body["failure_categories"]}
    assert {"mismatch", "slow"} <= labels

    failures = await client.get(
        f"/api/v1/evaluation-runs/{body['id']}/results",
        headers=ws.auth,
        params={"only_failures": True},
    )
    assert failures.status_code == 200
    assert failures.json()["total"] == 2
    assert all(result["passed"] is False for result in failures.json()["items"])


@pytest.mark.asyncio
async def test_dataset_run_requires_outputs(client: AsyncClient):
    ws = await create_workspace(client, "eval-no-outputs@agentlens.dev")
    dataset_id = await _dataset_with_items(client, ws)
    await _evaluator(client, ws, {"name": "exact", "evaluator_type": "exact_match"})

    response = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluation-runs",
        headers=ws.auth,
        json={"name": "no-outputs", "target": "dataset", "dataset_id": dataset_id},
    )
    assert response.status_code == 400
    assert "outputs" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_run_without_evaluators_is_rejected(client: AsyncClient):
    ws = await create_workspace(client, "eval-none@agentlens.dev")
    dataset_id = await _dataset_with_items(client, ws)
    response = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluation-runs",
        headers=ws.auth,
        json={
            "name": "orphan",
            "target": "dataset",
            "dataset_id": dataset_id,
            "outputs": [{"item_name": "order-status", "output": "hi"}],
        },
    )
    assert response.status_code == 400
    assert "evaluator" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trace_run_skips_evaluators_that_need_a_reference(client: AsyncClient):
    ws = await create_workspace(client, "eval-traces@agentlens.dev")
    now = datetime.now(timezone.utc)

    for index, status in enumerate(["success", "error"]):
        trace_id = str(uuid4())
        created = await client.post(
            "/api/v1/traces",
            headers=ws.key,
            json={
                "id": trace_id,
                "name": f"run-{index}",
                "agent_name": "support",
                "status": status,
                "start_time": (now - timedelta(minutes=10 + index)).isoformat(),
                "end_time": now.isoformat(),
                "duration_ms": 800 if status == "success" else 300,
                "output": "Your order ships tomorrow." if status == "success" else None,
                "error_message": None if status == "success" else "tool timeout",
            },
        )
        assert created.status_code == 200, created.text

    await _evaluator(client, ws, {"name": "clean", "evaluator_type": "no_error"})
    await _evaluator(client, ws, {"name": "exact", "evaluator_type": "exact_match"})

    run = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluation-runs",
        headers=ws.auth,
        json={
            "name": "production-sweep",
            "target": "traces",
            "selector": {"agent_name": "support", "limit": 50},
        },
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["total_items"] == 2
    assert body["passed_count"] == 1
    assert body["skipped_evaluators"] == ["exact"]
    assert [score["evaluator_name"] for score in body["evaluator_scores"]] == ["clean"]
    assert body["failure_categories"][0]["label"] == "runtime_error"


@pytest.mark.asyncio
async def test_trace_run_with_no_matches_is_rejected(client: AsyncClient):
    ws = await create_workspace(client, "eval-empty-traces@agentlens.dev")
    await _evaluator(client, ws, {"name": "clean", "evaluator_type": "no_error"})
    response = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluation-runs",
        headers=ws.auth,
        json={"name": "nothing", "target": "traces", "selector": {"agent_name": "ghost"}},
    )
    assert response.status_code == 400
    assert "nothing to evaluate" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_compare_runs_detects_regression(client: AsyncClient):
    ws = await create_workspace(client, "eval-compare@agentlens.dev")
    dataset_id = await _dataset_with_items(client, ws)
    await _evaluator(client, ws, {"name": "exact", "evaluator_type": "exact_match"})

    items = (await client.get(f"/api/v1/datasets/{dataset_id}/items", headers=ws.auth)).json()
    by_name = {item["name"]: item["id"] for item in items}

    async def make_run(name: str, second_answer: str, version: str) -> dict:
        response = await client.post(
            f"/api/v1/projects/{ws.project_id}/evaluation-runs",
            headers=ws.auth,
            json={
                "name": name,
                "target": "dataset",
                "dataset_id": dataset_id,
                "agent_version": version,
                "outputs": [
                    {
                        "dataset_item_id": by_name["order-status"],
                        "output": "Your order ships tomorrow.",
                        "duration_ms": 800,
                    },
                    {
                        "dataset_item_id": by_name["refund-policy"],
                        "output": second_answer,
                        "duration_ms": 800,
                    },
                ],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    baseline = await make_run("baseline", "Refunds are available within 30 days.", "v1")
    candidate = await make_run("candidate", "We never give refunds.", "v2")

    assert baseline["pass_rate"] == pytest.approx(1.0)
    assert candidate["pass_rate"] == pytest.approx(0.5)

    comparison = await client.get(
        f"/api/v1/evaluation-runs/{candidate['id']}/compare",
        headers=ws.auth,
        params={"baseline": baseline["id"]},
    )
    assert comparison.status_code == 200, comparison.text
    body = comparison.json()
    assert body["verdict"] == "fail"
    assert len(body["newly_failing"]) == 1
    assert body["newly_failing"][0]["subject_name"] == "refund-policy"
    assert body["newly_passing"] == []
    pass_rate = next(item for item in body["metrics"] if item["metric"] == "pass_rate")
    assert pass_rate["regression"] is True
    assert pass_rate["delta"] == pytest.approx(-0.5)

    clean = await client.get(
        f"/api/v1/evaluation-runs/{baseline['id']}/compare",
        headers=ws.auth,
        params={"baseline": baseline["id"]},
    )
    assert clean.json()["verdict"] == "pass"


@pytest.mark.asyncio
async def test_evaluation_run_listing_and_detail(client: AsyncClient):
    ws = await create_workspace(client, "eval-list@agentlens.dev")
    dataset_id = await _dataset_with_items(client, ws)
    await _evaluator(client, ws, {"name": "exact", "evaluator_type": "exact_match"})

    created = await client.post(
        f"/api/v1/projects/{ws.project_id}/evaluation-runs",
        headers=ws.auth,
        json={
            "name": "listed",
            "target": "dataset",
            "dataset_name": "support-golden",
            "evaluator_names": ["exact"],
            "outputs": [{"item_name": "order-status", "output": "Your order ships tomorrow."}],
        },
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]

    listed = await client.get(
        f"/api/v1/projects/{ws.project_id}/evaluation-runs",
        headers=ws.auth,
        params={"dataset_id": dataset_id},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["dataset_name"] == "support-golden"

    detail = await client.get(f"/api/v1/evaluation-runs/{run_id}", headers=ws.auth)
    assert detail.status_code == 200
    assert detail.json()["results"][0]["evaluator_name"] == "exact"

    missing = await client.get(f"/api/v1/evaluation-runs/{uuid4()}", headers=ws.auth)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_prompt_versions_track_active_revision(client: AsyncClient):
    ws = await create_workspace(client, "prompt-versions@agentlens.dev")
    first = await client.post(
        f"/api/v1/projects/{ws.project_id}/prompt-versions",
        headers=ws.auth,
        json={
            "name": "support-system",
            "version": "v1",
            "template": "You are a helpful support agent.",
            "is_active": True,
        },
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/projects/{ws.project_id}/prompt-versions",
        headers=ws.auth,
        json={
            "name": "support-system",
            "version": "v2",
            "template": "You are a concise support agent.",
            "is_active": True,
        },
    )
    assert second.status_code == 201

    duplicate = await client.post(
        f"/api/v1/projects/{ws.project_id}/prompt-versions",
        headers=ws.auth,
        json={"name": "support-system", "version": "v2", "template": "again"},
    )
    assert duplicate.status_code == 400

    listed = await client.get(
        f"/api/v1/projects/{ws.project_id}/prompt-versions",
        headers=ws.auth,
        params={"name": "support-system"},
    )
    active = [item for item in listed.json() if item["is_active"]]
    assert len(active) == 1
    assert active[0]["version"] == "v2"


@pytest.mark.asyncio
async def test_sdk_can_read_datasets_and_submit_runs(client: AsyncClient):
    ws = await create_workspace(client, "eval-sdk@agentlens.dev")
    await _dataset_with_items(client, ws)
    await _evaluator(client, ws, {"name": "exact", "evaluator_type": "exact_match"})

    datasets = await client.get("/api/v1/sdk/datasets", headers=ws.key)
    assert datasets.status_code == 200
    assert datasets.json()[0]["item_count"] == 2

    items = await client.get("/api/v1/sdk/datasets/support-golden/items", headers=ws.key)
    assert items.status_code == 200
    assert len(items.json()) == 2

    run = await client.post(
        "/api/v1/sdk/evaluation-runs",
        headers=ws.key,
        json={
            "name": "ci-run",
            "target": "dataset",
            "dataset_name": "support-golden",
            "outputs": [
                {"item_name": "order-status", "output": "Your order ships tomorrow."},
                {"item_name": "refund-policy", "output": "Refunds are available within 30 days."},
            ],
        },
    )
    assert run.status_code == 201, run.text
    assert run.json()["pass_rate"] == pytest.approx(1.0)

    created = await client.post(
        "/api/v1/sdk/datasets/regression-suite/items",
        headers=ws.key,
        json={"items": [{"name": "case-1", "input": "hi", "expected_output": "hello"}]},
    )
    assert created.status_code == 201
    assert created.json()[0]["name"] == "case-1"

    missing = await client.get("/api/v1/sdk/datasets/does-not-exist/items", headers=ws.key)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_evaluation_resources_are_isolated_between_tenants(client: AsyncClient):
    owner = await create_workspace(client, "eval-owner@agentlens.dev", name="Owner")
    intruder = await create_workspace(client, "eval-intruder@agentlens.dev", name="Intruder")

    dataset_id = await _dataset_with_items(client, owner)
    evaluator_id = await _evaluator(client, owner, {"name": "exact", "evaluator_type": "exact_match"})

    assert (await client.get(f"/api/v1/datasets/{dataset_id}", headers=intruder.auth)).status_code == 404
    assert (
        await client.get(f"/api/v1/datasets/{dataset_id}/items", headers=intruder.auth)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/evaluators/{evaluator_id}", headers=intruder.auth, json={"threshold": 0.1}
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/projects/{owner.project_id}/datasets", headers=intruder.auth)
    ).status_code == 404
    assert (
        await client.get("/api/v1/sdk/datasets", headers=intruder.key)
    ).json() == []

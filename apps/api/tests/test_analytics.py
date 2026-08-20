from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.test_workspace import auth_header, signup_and_login


@pytest.mark.asyncio
async def test_analytics_from_ingested_traces(client: AsyncClient):
    token = await signup_and_login(client, "analytics@agentlens.dev")
    headers = auth_header(token)
    org_id = (await client.get("/api/v1/organizations", headers=headers)).json()[0]["id"]
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": "Analytics Agent"},
    )
    project_id = project.json()["id"]
    secret = (
        await client.post(
            f"/api/v1/projects/{project_id}/api-keys",
            headers=headers,
            json={"name": "ingest"},
        )
    ).json()["secret"]
    key = {"Authorization": f"Bearer {secret}"}
    now = datetime.now(timezone.utc)

    success_id = str(uuid4())
    await client.post(
        "/api/v1/traces",
        headers=key,
        json={
            "id": success_id,
            "name": "ok-run",
            "status": "success",
            "start_time": (now - timedelta(hours=1)).isoformat(),
            "end_time": now.isoformat(),
            "duration_ms": 1200,
        },
    )
    await client.post(
        "/api/v1/llm-calls",
        headers=key,
        json={
            "trace_id": success_id,
            "model": "gpt-4o",
            "input_tokens": 100,
            "output_tokens": 50,
            "latency_ms": 800,
        },
    )
    await client.post(
        "/api/v1/traces",
        headers=key,
        json={
            "id": str(uuid4()),
            "name": "bad-run",
            "status": "error",
            "start_time": (now - timedelta(minutes=30)).isoformat(),
            "end_time": now.isoformat(),
            "duration_ms": 400,
            "error_message": "tool failed",
        },
    )

    response = await client.get(
        f"/api/v1/organizations/{org_id}/analytics",
        headers=headers,
        params={"range": "24h", "project_id": project_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_runs"] == 2
    assert payload["summary"]["success_count"] == 1
    assert payload["summary"]["error_count"] == 1
    assert payload["summary"]["success_rate"] == pytest.approx(0.5)
    assert payload["summary"]["error_rate"] == pytest.approx(0.5)
    assert payload["summary"]["total_tokens"] == 150
    assert float(payload["summary"]["total_cost"]) > 0
    assert payload["models"][0]["model"] == "gpt-4o"
    assert any(point["runs"] > 0 for point in payload["timeseries"])


@pytest.mark.asyncio
async def test_analytics_isolation(client: AsyncClient):
    token_a = await signup_and_login(client, "an-a@agentlens.dev", "A")
    token_b = await signup_and_login(client, "an-b@agentlens.dev", "B")
    org_a = (await client.get("/api/v1/organizations", headers=auth_header(token_a))).json()[0]["id"]
    forbidden = await client.get(
        f"/api/v1/organizations/{org_a}/analytics",
        headers=auth_header(token_b),
    )
    assert forbidden.status_code == 404

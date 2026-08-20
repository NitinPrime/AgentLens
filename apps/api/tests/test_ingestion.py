from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.test_workspace import auth_header, signup_and_login


async def _project_and_key(client: AsyncClient, email: str, name: str = "Support") -> tuple[str, str, str]:
    token = await signup_and_login(client, email, name)
    org_id = (await client.get("/api/v1/organizations", headers=auth_header(token))).json()[0]["id"]
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=auth_header(token),
        json={"name": "Customer Support Agent"},
    )
    project_id = project.json()["id"]
    created = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=auth_header(token),
        json={"name": "ingest"},
    )
    return token, project_id, created.json()["secret"]


@pytest.mark.asyncio
async def test_ingest_requires_api_key(client: AsyncClient):
    token = await signup_and_login(client, "jwt-ingest@agentlens.dev")
    response = await client.post(
        "/api/v1/traces",
        headers=auth_header(token),
        json={"name": "should-fail"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ingest_trace_span_llm_tool_and_read(client: AsyncClient):
    token, project_id, secret = await _project_and_key(client, "ingest@agentlens.dev")
    key_header = {"Authorization": f"Bearer {secret}"}
    trace_id = str(uuid4())
    span_id = str(uuid4())

    created = await client.post(
        "/api/v1/traces",
        headers=key_header,
        json={
            "id": trace_id,
            "name": "customer_support_task",
            "agent_name": "support",
            "status": "running",
            "input": {"message": "Where is my order?"},
        },
    )
    assert created.status_code == 200
    assert created.json()["id"] == trace_id

    span = await client.post(
        "/api/v1/spans",
        headers=key_header,
        json={
            "id": span_id,
            "trace_id": trace_id,
            "type": "LLM",
            "name": "gpt-4o",
            "status": "success",
        },
    )
    assert span.status_code == 200

    llm = await client.post(
        "/api/v1/llm-calls",
        headers=key_header,
        json={
            "trace_id": trace_id,
            "span_id": span_id,
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "completion": "hello",
            "input_tokens": 1000,
            "output_tokens": 100,
        },
    )
    assert llm.status_code == 200
    assert llm.json()["provider"] == "openai"
    assert float(llm.json()["estimated_cost"]) == pytest.approx(0.0035)

    tool = await client.post(
        "/api/v1/tool-calls",
        headers=key_header,
        json={
            "trace_id": trace_id,
            "name": "order_lookup",
            "arguments": {"order_id": "123"},
            "output": {"status": "shipped"},
            "status": "success",
            "duration_ms": 284,
        },
    )
    assert tool.status_code == 200

    event = await client.post(
        "/api/v1/events",
        headers=key_header,
        json={"trace_id": trace_id, "name": "checkpoint", "body": {"step": 1}},
    )
    assert event.status_code == 200

    await client.post(
        "/api/v1/traces",
        headers=key_header,
        json={
            "id": trace_id,
            "name": "customer_support_task",
            "agent_name": "support",
            "status": "success",
            "output": "Your order ships tomorrow.",
        },
    )

    listed = await client.get(
        f"/api/v1/projects/{project_id}/traces",
        headers=auth_header(token),
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["total_tokens"] == 1100

    detail = await client.get(f"/api/v1/traces/{trace_id}", headers=auth_header(token))
    assert detail.status_code == 200
    body = detail.json()
    assert body["output"] == "Your order ships tomorrow."
    assert len(body["spans"]) == 1
    assert body["spans"][0]["llm_call"]["model"] == "gpt-4o"
    assert len(body["events"]) == 1


@pytest.mark.asyncio
async def test_trace_isolation_between_projects(client: AsyncClient):
    _, _, secret_a = await _project_and_key(client, "iso-a@agentlens.dev", "Alice")
    token_b, project_b, _ = await _project_and_key(client, "iso-b@agentlens.dev", "Bob")

    trace_id = str(uuid4())
    created = await client.post(
        "/api/v1/traces",
        headers={"Authorization": f"Bearer {secret_a}"},
        json={"id": trace_id, "name": "secret-run", "status": "success"},
    )
    assert created.status_code == 200

    listed = await client.get(
        f"/api/v1/projects/{project_b}/traces",
        headers=auth_header(token_b),
    )
    assert listed.json()["total"] == 0

    peek = await client.get(f"/api/v1/traces/{trace_id}", headers=auth_header(token_b))
    assert peek.status_code == 404

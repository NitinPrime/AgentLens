from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.helpers import Workspace, create_workspace


async def _ingest(
    client: AsyncClient,
    ws: Workspace,
    *,
    version: str,
    status: str,
    duration_ms: int,
    minutes_ago: int,
    tokens: int = 100,
) -> str:
    # The API recomputes duration from start/end whenever both are present, so
    # the fixture has to keep the timestamps consistent with duration_ms.
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    trace_id = str(uuid4())
    created = await client.post(
        "/api/v1/traces",
        headers=ws.key,
        json={
            "id": trace_id,
            "name": "task",
            "agent_name": "support",
            "status": status,
            "agent_version": version,
            "prompt_version": f"prompt-{version}",
            "start_time": started.isoformat(),
            "end_time": (started + timedelta(milliseconds=duration_ms)).isoformat(),
        },
    )
    assert created.status_code == 200, created.text
    if tokens:
        llm = await client.post(
            "/api/v1/llm-calls",
            headers=ws.key,
            json={
                "trace_id": trace_id,
                "model": "gpt-4o-mini",
                "input_tokens": tokens,
                "output_tokens": tokens // 2,
                "latency_ms": duration_ms,
            },
        )
        assert llm.status_code == 200, llm.text
    return trace_id


@pytest.mark.asyncio
async def test_version_rollup_reports_quality_and_latency(client: AsyncClient):
    ws = await create_workspace(client, "versions-list@agentlens.dev")

    for index in range(4):
        await _ingest(client, ws, version="v1", status="success", duration_ms=500 + index * 100, minutes_ago=60 + index)
    await _ingest(client, ws, version="v1", status="error", duration_ms=900, minutes_ago=70)

    response = await client.get(
        f"/api/v1/projects/{ws.project_id}/versions",
        headers=ws.auth,
        params={"dimension": "agent_version", "range": "24h"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dimension"] == "agent_version"
    stats = body["versions"][0]
    assert stats["version"] == "v1"
    assert stats["runs"] == 5
    assert stats["success_count"] == 4
    assert stats["error_count"] == 1
    assert stats["success_rate"] == pytest.approx(0.8)
    # Durations are 500/600/700/800 (success) and 900 (error).
    assert stats["avg_latency_ms"] == pytest.approx(700)
    assert stats["p50_latency_ms"] == pytest.approx(700)
    assert stats["p95_latency_ms"] == pytest.approx(880)
    assert stats["total_tokens"] == 5 * 150
    assert float(stats["avg_cost"]) > 0
    assert stats["first_seen"] is not None


@pytest.mark.asyncio
async def test_version_comparison_fails_on_quality_drop(client: AsyncClient):
    ws = await create_workspace(client, "versions-compare@agentlens.dev")

    for index in range(5):
        await _ingest(client, ws, version="v1", status="success", duration_ms=600, minutes_ago=100 + index)
    for index in range(3):
        await _ingest(client, ws, version="v2", status="success", duration_ms=600, minutes_ago=50 + index)
    for index in range(2):
        await _ingest(client, ws, version="v2", status="error", duration_ms=600, minutes_ago=40 + index)

    response = await client.get(
        f"/api/v1/projects/{ws.project_id}/versions/compare",
        headers=ws.auth,
        params={"baseline": "v1", "candidate": "v2", "range": "24h"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] == "fail"
    assert body["baseline"]["success_rate"] == pytest.approx(1.0)
    assert body["candidate"]["success_rate"] == pytest.approx(0.6)
    success = next(item for item in body["metrics"] if item["metric"] == "success_rate")
    assert success["regression"] is True
    assert success["delta"] == pytest.approx(-0.4)
    assert "success rate" in body["summary"].lower()


@pytest.mark.asyncio
async def test_version_comparison_warns_on_latency_only(client: AsyncClient):
    ws = await create_workspace(client, "versions-latency@agentlens.dev")

    for index in range(4):
        await _ingest(client, ws, version="fast", status="success", duration_ms=400, minutes_ago=120 + index)
    for index in range(4):
        await _ingest(client, ws, version="slow", status="success", duration_ms=1600, minutes_ago=60 + index)

    response = await client.get(
        f"/api/v1/projects/{ws.project_id}/versions/compare",
        headers=ws.auth,
        params={"baseline": "fast", "candidate": "slow", "range": "24h"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] == "warn"
    latency = next(item for item in body["metrics"] if item["metric"] == "p95_latency_ms")
    assert latency["regression"] is True
    assert latency["pct_change"] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_version_comparison_passes_when_stable(client: AsyncClient):
    ws = await create_workspace(client, "versions-stable@agentlens.dev")
    for index in range(3):
        await _ingest(client, ws, version="v1", status="success", duration_ms=500, minutes_ago=90 + index)
    for index in range(3):
        await _ingest(client, ws, version="v2", status="success", duration_ms=520, minutes_ago=30 + index)

    response = await client.get(
        f"/api/v1/projects/{ws.project_id}/versions/compare",
        headers=ws.auth,
        params={"baseline": "v1", "candidate": "v2", "range": "24h"},
    )
    assert response.json()["verdict"] == "pass"


@pytest.mark.asyncio
async def test_version_endpoints_validate_input_and_isolate_tenants(client: AsyncClient):
    ws = await create_workspace(client, "versions-guard@agentlens.dev")
    intruder = await create_workspace(client, "versions-intruder@agentlens.dev", name="Intruder")
    await _ingest(client, ws, version="v1", status="success", duration_ms=500, minutes_ago=10)

    bad_dimension = await client.get(
        f"/api/v1/projects/{ws.project_id}/versions",
        headers=ws.auth,
        params={"dimension": "vibes"},
    )
    assert bad_dimension.status_code == 400

    unknown_baseline = await client.get(
        f"/api/v1/projects/{ws.project_id}/versions/compare",
        headers=ws.auth,
        params={"baseline": "does-not-exist", "candidate": "v1"},
    )
    assert unknown_baseline.status_code == 404

    forbidden = await client.get(
        f"/api/v1/projects/{ws.project_id}/versions", headers=intruder.auth
    )
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_prompt_version_dimension_is_supported(client: AsyncClient):
    ws = await create_workspace(client, "versions-prompt@agentlens.dev")
    await _ingest(client, ws, version="v1", status="success", duration_ms=500, minutes_ago=20)
    response = await client.get(
        f"/api/v1/projects/{ws.project_id}/versions",
        headers=ws.auth,
        params={"dimension": "prompt_version", "range": "24h"},
    )
    assert response.status_code == 200
    assert response.json()["versions"][0]["version"] == "prompt-v1"

import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse

from app.core.events import EventBus
from tests.helpers import create_workspace


@pytest.mark.asyncio
async def test_health_and_readiness_are_public(client: AsyncClient):
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"


@pytest.mark.asyncio
async def test_responses_carry_request_id_and_security_headers(client: AsyncClient):
    response = await client.get("/health")
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-response-time"].endswith("ms")


@pytest.mark.asyncio
async def test_incoming_request_id_is_echoed(client: AsyncClient):
    response = await client.get("/health", headers={"X-Request-ID": "trace-me-123"})
    assert response.headers["x-request-id"] == "trace-me-123"


@pytest.mark.asyncio
async def test_system_endpoints_require_authentication(client: AsyncClient):
    assert (await client.get("/api/v1/system/info")).status_code == 401
    assert (await client.get("/api/v1/system/metrics")).status_code == 401


@pytest.mark.asyncio
async def test_system_info_and_metrics(client: AsyncClient):
    ws = await create_workspace(client, "system-metrics@agentlens.dev")

    info = await client.get("/api/v1/system/info", headers=ws.auth)
    assert info.status_code == 200
    body = info.json()
    assert body["database_backend"] in {"sqlite", "postgresql"}
    assert body["judge_configured"] is False
    assert body["uptime_seconds"] >= 0

    metrics = await client.get("/api/v1/system/metrics", headers=ws.auth)
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["requests"] > 0
    assert payload["p95_ms"] is not None
    assert any("/api/v1/organizations" in route["route"] for route in payload["routes"])
    assert payload["streams"]["subscribers"] == 0

    prometheus = await client.get("/api/v1/system/metrics/prometheus", headers=ws.auth)
    assert prometheus.status_code == 200
    assert prometheus.headers["content-type"].startswith("text/plain")
    assert "agentlens_requests_total" in prometheus.text
    assert "agentlens_route_latency_ms" in prometheus.text


@pytest.mark.asyncio
async def test_organization_usage_counts_everything(client: AsyncClient):
    ws = await create_workspace(client, "system-usage@agentlens.dev")

    trace_id = str(uuid4())
    await client.post(
        "/api/v1/traces",
        headers=ws.key,
        json={"id": trace_id, "name": "run", "status": "success"},
    )
    await client.post(
        "/api/v1/llm-calls",
        headers=ws.key,
        json={
            "trace_id": trace_id,
            "model": "gpt-4o-mini",
            "input_tokens": 200,
            "output_tokens": 100,
        },
    )
    await client.post(
        f"/api/v1/projects/{ws.project_id}/datasets",
        headers=ws.auth,
        json={"name": "usage-set"},
    )

    usage = await client.get(f"/api/v1/organizations/{ws.org_id}/usage", headers=ws.auth)
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["projects"] == 1
    assert body["traces"] == 1
    assert body["llm_calls"] == 1
    assert body["datasets"] == 1
    assert body["traces_last_24h"] == 1
    assert body["tokens_last_24h"] == 300
    assert float(body["cost_last_24h"]) > 0
    assert body["newest_trace_at"] is not None


@pytest.mark.asyncio
async def test_usage_is_empty_for_a_fresh_organization(client: AsyncClient):
    ws = await create_workspace(client, "system-empty@agentlens.dev")
    created = await client.post(
        "/api/v1/organizations",
        headers=ws.auth,
        json={"name": "Second workspace"},
    )
    assert created.status_code == 201, created.text
    usage = await client.get(
        f"/api/v1/organizations/{created.json()['id']}/usage", headers=ws.auth
    )
    assert usage.status_code == 200
    assert usage.json()["projects"] == 0
    assert usage.json()["traces"] == 0


@pytest.mark.asyncio
async def test_usage_is_isolated_between_tenants(client: AsyncClient):
    owner = await create_workspace(client, "usage-owner@agentlens.dev")
    intruder = await create_workspace(client, "usage-intruder@agentlens.dev", name="Intruder")
    response = await client.get(
        f"/api/v1/organizations/{owner.org_id}/usage", headers=intruder.auth
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_oversized_request_body_is_rejected(client: AsyncClient):
    ws = await create_workspace(client, "system-large@agentlens.dev")
    huge = "x" * (6 * 1024 * 1024)
    response = await client.post(
        "/api/v1/traces",
        headers=ws.key,
        json={"name": "too-big", "output": huge},
    )
    assert response.status_code == 413
    assert "limit" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limiter_throttles_a_hot_client_and_spares_probes(monkeypatch):
    """Drive the guard middleware directly, wrapped around a trivial app.

    The suite runs with throttling off so hundreds of requests from one test
    client never trip it, so this re-enables it around a two-request budget.
    """

    from app.middleware import RequestGuardMiddleware
    from app.middleware import settings as guard_settings

    monkeypatch.setattr(guard_settings, "rate_limit_enabled", True)
    monkeypatch.setattr(guard_settings, "rate_limit_requests", 2)
    monkeypatch.setattr(guard_settings, "rate_limit_window_seconds", 60)

    async def endpoint(scope, receive, send):
        await JSONResponse({"ok": True})(scope, receive, send)

    transport = ASGITransport(app=RequestGuardMiddleware(endpoint))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        assert (await ac.get("/api/v1/traces")).status_code == 200
        assert (await ac.get("/api/v1/traces")).status_code == 200

        limited = await ac.get("/api/v1/traces")
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1

        # Probes and the long-lived stream must stay reachable while throttled.
        assert (await ac.get("/health")).status_code == 200
        assert (await ac.get("/api/v1/projects/abc/stream")).status_code == 200


@pytest.mark.asyncio
async def test_event_bus_fans_out_and_drops_under_backpressure():
    bus = EventBus()
    project_id = uuid4()

    assert bus.publish(project_id, "trace", {"id": "1"}) == 0

    first = bus.subscribe(project_id)
    second = bus.subscribe(project_id)
    assert bus.subscriber_count == 2
    assert bus.publish(project_id, "trace", {"id": "1"}) == 2

    assert (await asyncio.wait_for(first.get(), timeout=1))["data"]["id"] == "1"
    assert (await asyncio.wait_for(second.get(), timeout=1))["type"] == "trace"

    other_project = uuid4()
    assert bus.publish(other_project, "trace", {"id": "2"}) == 0
    assert first.empty()

    for index in range(500):
        bus.publish(project_id, "span", {"id": str(index)})
    assert first.qsize() <= 200
    assert bus.stats()["events_dropped"] > 0

    bus.unsubscribe(project_id, first)
    bus.unsubscribe(project_id, second)
    assert bus.subscriber_count == 0
    assert bus.project_count == 0


class _NeverDisconnects:
    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_stream_generator_emits_connected_then_live_events():
    """Drive the SSE generator directly.

    httpx's ASGI transport buffers a whole response before returning it, so an
    endless event stream cannot be exercised over the test client. Iterating the
    response body here covers the same code with deterministic timing.
    """

    from app.core.events import bus as live_bus
    from app.routers.live import stream_project_activity

    project_id = uuid4()
    response = await stream_project_activity(
        request=_NeverDisconnects(), project_id=project_id
    )
    assert response.media_type == "text/event-stream"
    assert response.headers["x-accel-buffering"] == "no"

    frames = response.body_iterator
    try:
        first = await asyncio.wait_for(anext(frames), timeout=2)
        assert "event: connected" in first
        assert str(project_id) in first

        assert live_bus.publish(project_id, "trace", {"id": "abc", "name": "live-run"}) == 1
        second = await asyncio.wait_for(anext(frames), timeout=2)
        assert second.startswith("event: trace")
        assert '"name": "live-run"' in second
    finally:
        await frames.aclose()

    assert live_bus.subscriber_count == 0


@pytest.mark.asyncio
async def test_stream_requires_a_valid_access_token(client: AsyncClient):
    ws = await create_workspace(client, "stream-auth@agentlens.dev")

    missing = await client.get(f"/api/v1/projects/{ws.project_id}/stream")
    assert missing.status_code == 422

    invalid = await client.get(
        f"/api/v1/projects/{ws.project_id}/stream", params={"token": "not-a-jwt"}
    )
    assert invalid.status_code == 401

    refresh = await client.post(
        "/api/v1/auth/login",
        json={"email": "stream-auth@agentlens.dev", "password": "securepass123"},
    )
    wrong_type = await client.get(
        f"/api/v1/projects/{ws.project_id}/stream",
        params={"token": refresh.json()["refresh_token"]},
    )
    assert wrong_type.status_code == 401

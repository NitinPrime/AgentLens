"""Server-sent events for the live trace feed.

``EventSource`` cannot set request headers, so the access token is passed as a
query parameter over the same TLS channel the rest of the API uses. The
authorization check runs in a short-lived session that is closed before
streaming begins, so an idle browser tab never pins a database connection.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.core.events import bus
from app.core.security import verify_token
from app.dependencies import get_session_factory
from app.services.auth import AuthService
from app.services.organizations import OrganizationError
from app.services.projects import ProjectService

router = APIRouter(tags=["live"])
settings = get_settings()

HEARTBEAT_SECONDS = 15.0


async def authorize_stream(
    project_id: UUID,
    token: str = Query(..., description="Access token; EventSource cannot send headers"),
    session_factory: Any = Depends(get_session_factory),
) -> UUID:
    try:
        user_id = verify_token(token, expected_type="access")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    async with session_factory() as session:
        user = await AuthService(db=session, redis_client=None).get_user_by_id(UUID(user_id))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
            )
        try:
            await ProjectService(session).get_project_for_user(project_id, user.id)
        except OrganizationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return project_id


def _frame(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/projects/{project_id}/stream")
async def stream_project_activity(
    request: Request,
    project_id: UUID = Depends(authorize_stream),
) -> StreamingResponse:
    async def publisher() -> AsyncGenerator[str, None]:
        queue = bus.subscribe(project_id)
        opened_at = time.monotonic()
        try:
            yield _frame("connected", {"project_id": str(project_id)})
            while True:
                if time.monotonic() - opened_at > settings.stream_max_seconds:
                    yield _frame("closing", {"reason": "max_duration"})
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        return
                    yield ": ping\n\n"
                    continue
                yield _frame(event["type"], event["data"])
        except asyncio.CancelledError:
            raise
        finally:
            bus.unsubscribe(project_id, queue)

    return StreamingResponse(
        publisher(),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache, no-transform",
            "connection": "keep-alive",
            "x-accel-buffering": "no",
        },
    )

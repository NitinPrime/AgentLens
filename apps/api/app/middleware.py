"""Pure ASGI middleware for request metrics, security headers, and guards.

These are implemented at the ASGI level rather than with ``BaseHTTPMiddleware``
so the server-sent-events stream is never buffered.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.core.observability import registry

settings = get_settings()

REQUEST_ID_HEADER = "x-request-id"

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}

# Long-lived or infrastructure endpoints that must not be throttled.
RATE_LIMIT_EXEMPT_SUFFIXES = ("/stream",)
RATE_LIMIT_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")


class ObservabilityMiddleware:
    """Stamp a request id, record latency, and attach security headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        request_id = _incoming_request_id(scope) or uuid4().hex
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                headers["x-response-time"] = f"{(time.perf_counter() - start) * 1000:.2f}ms"
                for key, value in SECURITY_HEADERS.items():
                    headers[key] = value
                if settings.is_production:
                    headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            route = scope.get("route")
            template = getattr(route, "path", None) or scope.get("path", "unknown")
            registry.record(scope.get("method", "GET"), str(template), status_code, duration_ms)


class RequestGuardMiddleware:
    """Reject oversized bodies and throttle abusive clients."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        content_length = _header(scope, b"content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > settings.max_request_bytes:
                await _reject(
                    scope,
                    receive,
                    send,
                    413,
                    f"Request body exceeds the {settings.max_request_bytes} byte limit.",
                )
                return

        if settings.rate_limit_enabled and not _is_exempt(path):
            client = scope.get("client")
            key = client[0] if client else "unknown"
            retry_after = self._check(key)
            if retry_after is not None:
                await _reject(
                    scope,
                    receive,
                    send,
                    429,
                    "Too many requests. Slow down and retry shortly.",
                    headers={"retry-after": str(retry_after)},
                )
                return

        await self.app(scope, receive, send)

    def _check(self, key: str) -> int | None:
        """Return seconds to wait when the caller is over budget, else ``None``."""

        now = time.monotonic()
        window = settings.rate_limit_window_seconds
        with self._lock:
            hits = self._hits[key]
            cutoff = now - window
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= settings.rate_limit_requests:
                return max(1, int(window - (now - hits[0])))
            hits.append(now)
            if len(self._hits) > 10_000:
                self._prune(cutoff)
        return None

    def _prune(self, cutoff: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for key in stale:
            self._hits.pop(key, None)


def _incoming_request_id(scope: Scope) -> str | None:
    value = _header(scope, REQUEST_ID_HEADER.encode())
    if not value:
        return None
    cleaned = value.strip()[:64]
    return cleaned or None


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _is_exempt(path: str) -> bool:
    if path.endswith(RATE_LIMIT_EXEMPT_SUFFIXES):
        return True
    return path.startswith(RATE_LIMIT_EXEMPT_PREFIXES)


async def _reject(
    scope: Scope,
    receive: Receive,
    send: Send,
    status_code: int,
    detail: str,
    headers: dict[str, str] | None = None,
) -> None:
    response = JSONResponse({"detail": detail}, status_code=status_code, headers=headers)
    await response(scope, receive, send)

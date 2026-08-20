"""AgentLens observing itself.

A tiny in-memory registry records per-route request counts, error counts, and a
bounded sample of latencies so the API can report its own p50/p95 without an
external metrics backend. Samples are capped, so memory stays flat regardless of
traffic.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

SAMPLE_SIZE = 500


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass
class RouteStats:
    route: str
    requests: int = 0
    client_errors: int = 0
    server_errors: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    samples: deque[float] = field(default_factory=lambda: deque(maxlen=SAMPLE_SIZE))

    def as_dict(self) -> dict[str, object]:
        samples = list(self.samples)
        return {
            "route": self.route,
            "requests": self.requests,
            "client_errors": self.client_errors,
            "server_errors": self.server_errors,
            "avg_ms": round(self.total_ms / self.requests, 3) if self.requests else None,
            "p50_ms": round(_percentile(samples, 0.5) or 0.0, 3) if samples else None,
            "p95_ms": round(_percentile(samples, 0.95) or 0.0, 3) if samples else None,
            "max_ms": round(self.max_ms, 3),
        }


class MetricsRegistry:
    def __init__(self) -> None:
        self._routes: dict[str, RouteStats] = {}
        self._lock = Lock()
        self.started_at = time.time()

    def record(self, method: str, route: str, status_code: int, duration_ms: float) -> None:
        key = f"{method} {route}"
        with self._lock:
            stats = self._routes.get(key)
            if stats is None:
                stats = RouteStats(route=key)
                self._routes[key] = stats
            stats.requests += 1
            stats.total_ms += duration_ms
            stats.max_ms = max(stats.max_ms, duration_ms)
            stats.samples.append(duration_ms)
            if 400 <= status_code < 500:
                stats.client_errors += 1
            elif status_code >= 500:
                stats.server_errors += 1

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            routes = [stats.as_dict() for stats in self._routes.values()]
            requests = sum(stats.requests for stats in self._routes.values())
            client_errors = sum(stats.client_errors for stats in self._routes.values())
            server_errors = sum(stats.server_errors for stats in self._routes.values())
            all_samples = [value for stats in self._routes.values() for value in stats.samples]

        routes.sort(key=lambda item: item["requests"], reverse=True)  # type: ignore[arg-type,return-value]
        return {
            "uptime_seconds": round(self.uptime_seconds, 3),
            "requests": requests,
            "client_errors": client_errors,
            "server_errors": server_errors,
            "error_rate": (client_errors + server_errors) / requests if requests else 0.0,
            "p50_ms": round(_percentile(all_samples, 0.5) or 0.0, 3) if all_samples else None,
            "p95_ms": round(_percentile(all_samples, 0.95) or 0.0, 3) if all_samples else None,
            "routes": routes,
        }

    def reset(self) -> None:
        with self._lock:
            self._routes.clear()
            self.started_at = time.time()


registry = MetricsRegistry()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def prometheus_exposition(snapshot: dict[str, object]) -> str:
    """Render a snapshot in the Prometheus text exposition format."""

    lines: list[str] = [
        "# HELP agentlens_uptime_seconds Seconds since the API process started.",
        "# TYPE agentlens_uptime_seconds gauge",
        f"agentlens_uptime_seconds {snapshot['uptime_seconds']}",
        "# HELP agentlens_requests_total Total HTTP requests handled.",
        "# TYPE agentlens_requests_total counter",
        f"agentlens_requests_total {snapshot['requests']}",
        "# HELP agentlens_request_errors_total HTTP responses with a 4xx or 5xx status.",
        "# TYPE agentlens_request_errors_total counter",
        f'agentlens_request_errors_total{{class="client"}} {snapshot["client_errors"]}',
        f'agentlens_request_errors_total{{class="server"}} {snapshot["server_errors"]}',
        "# HELP agentlens_route_requests_total Requests per route.",
        "# TYPE agentlens_route_requests_total counter",
    ]
    routes: list[dict[str, object]] = snapshot.get("routes", [])  # type: ignore[assignment]
    for route in routes:
        label = _escape(str(route["route"]))
        lines.append(f'agentlens_route_requests_total{{route="{label}"}} {route["requests"]}')

    lines.extend(
        [
            "# HELP agentlens_route_latency_ms Route latency percentiles in milliseconds.",
            "# TYPE agentlens_route_latency_ms gauge",
        ]
    )
    for route in routes:
        label = _escape(str(route["route"]))
        for quantile, key in (("0.5", "p50_ms"), ("0.95", "p95_ms")):
            value = route.get(key)
            if value is not None:
                lines.append(
                    f'agentlens_route_latency_ms{{route="{label}",quantile="{quantile}"}} {value}'
                )
    return "\n".join(lines) + "\n"

from __future__ import annotations

import functools
import os
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any, TypeVar

import httpx

from agentlens.evaluations import DatasetItem, EvaluationRun
from agentlens.tracing import SpanType, TraceHandle
from agentlens._util import jsonable

F = TypeVar("F", bound=Callable[..., Any])


class AgentLensError(Exception):
    pass


class AgentLens:
    """Client for sending agent traces and running evaluations."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("AGENTLENS_API_KEY")
        if not self.api_key:
            raise AgentLensError("API key is required (api_key= or AGENTLENS_API_KEY)")
        self.base_url = (base_url or os.getenv("AGENTLENS_API_URL") or "http://localhost:8000").rstrip(
            "/"
        )
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "AgentLens":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/api/v1{path}"
        kwargs: dict[str, Any] = {"headers": self._headers()}
        if payload is not None:
            kwargs["json"] = jsonable(payload)
        if params is not None:
            kwargs["params"] = params

        response = self._client.request(method, url, **kwargs)
        if response.status_code >= 400:
            detail = response.text
            try:
                body = response.json()
                detail = str(body.get("detail", body))
            except Exception:
                pass
            raise AgentLensError(f"{method} {path} failed ({response.status_code}): {detail}")
        if not response.content:
            return {}
        return response.json()

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", path, payload)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def verify(self) -> dict[str, Any]:
        """Confirm the API key works and return the project it belongs to."""

        return self.get("/sdk/verify")

    # ---------------------------------------------------------------- tracing

    def trace(
        self,
        name: str,
        *,
        agent_name: str | None = None,
        session_id: str | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        agent_version: str | None = None,
        prompt_version: str | None = None,
        model_version: str | None = None,
    ) -> TraceHandle:
        return TraceHandle(
            client=self,
            name=name,
            agent_name=agent_name,
            session_id=session_id,
            input=input,
            metadata=metadata,
            agent_version=agent_version,
            prompt_version=prompt_version,
            model_version=model_version,
        )

    def observe(
        self,
        name: str | None = None,
        *,
        agent_name: str | None = None,
        session_id: str | None = None,
        agent_version: str | None = None,
        prompt_version: str | None = None,
        model_version: str | None = None,
        capture_input: bool = True,
        capture_output: bool = True,
    ) -> Callable[[F], F]:
        """Wrap a function so each call becomes a trace.

        ``@lens.observe(agent_name="support")`` is the fastest way to get an
        existing entry point into AgentLens without restructuring it.
        """

        def decorator(func: F) -> F:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                payload = None
                if capture_input:
                    payload = {"args": list(args), "kwargs": kwargs} if (args or kwargs) else None
                with self.trace(
                    name or func.__name__,
                    agent_name=agent_name,
                    session_id=session_id,
                    input=payload,
                    agent_version=agent_version,
                    prompt_version=prompt_version,
                    model_version=model_version,
                ) as handle:
                    result = func(*args, **kwargs)
                    if capture_output:
                        handle.set_output(result)
                    return result

            return wrapper  # type: ignore[return-value]

        return decorator

    # ------------------------------------------------------------- datasets

    def get_dataset(self, name: str, limit: int = 500) -> list[DatasetItem]:
        """Fetch the items of a dataset by name."""

        payload = self.get(f"/sdk/datasets/{name}/items", params={"limit": limit})
        return [DatasetItem.from_payload(item) for item in payload]

    def list_datasets(self) -> list[dict[str, Any]]:
        return self.get("/sdk/datasets")

    def upload_dataset(
        self,
        name: str,
        items: Iterable[dict[str, Any] | DatasetItem],
        *,
        replace: bool = False,
    ) -> list[DatasetItem]:
        """Create or extend a dataset. Creates it when the name is unknown."""

        payload_items: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, DatasetItem):
                payload_items.append(
                    {
                        "name": item.name,
                        "input": item.input,
                        "expected_output": item.expected_output,
                        "metadata": item.metadata or None,
                    }
                )
            else:
                payload_items.append(dict(item))
        if not payload_items:
            raise AgentLensError("upload_dataset needs at least one item")

        created = self.post(
            f"/sdk/datasets/{name}/items", {"items": payload_items, "replace": replace}
        )
        return [DatasetItem.from_payload(item) for item in created]

    # ---------------------------------------------------------- evaluations

    def evaluate(
        self,
        dataset: str,
        fn: Callable[[DatasetItem], Any],
        *,
        name: str | None = None,
        evaluators: Sequence[str] | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        prompt_version: str | None = None,
        model_version: str | None = None,
        trace: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationRun:
        """Run ``fn`` over every item in ``dataset`` and have AgentLens score it.

        The agent executes locally (only you can call your models and tools) and
        the outputs are scored server-side by the project's evaluators. Each item
        is also traced by default, so a failing score links straight to the run
        that produced it.
        """

        items = self.get_dataset(dataset)
        if not items:
            raise AgentLensError(f"Dataset '{dataset}' has no items to evaluate")

        run_name = name or f"{dataset} evaluation"
        outputs: list[dict[str, Any]] = []

        for item in items:
            started = time.perf_counter()
            output: Any = None
            status = "success"
            error_message: str | None = None
            trace_id: Any = None
            cost: float | None = None
            tokens = 0

            if trace:
                with self.trace(
                    item.name or run_name,
                    agent_name=agent_name,
                    input=item.input,
                    metadata={"evaluation": run_name, "dataset": dataset},
                    agent_version=agent_version,
                    prompt_version=prompt_version,
                    model_version=model_version,
                ) as handle:
                    trace_id = handle.id
                    try:
                        output = fn(item)
                        handle.set_output(output)
                    except Exception as exc:
                        status = "error"
                        error_message = str(exc)
                        handle.mark_error(exc)
                cost = handle.total_cost
                tokens = handle.total_tokens
            else:
                try:
                    output = fn(item)
                except Exception as exc:
                    status = "error"
                    error_message = str(exc)

            outputs.append(
                {
                    "dataset_item_id": item.id,
                    "item_name": item.name,
                    "output": output,
                    "trace_id": trace_id,
                    "status": status,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "cost": cost,
                    "total_tokens": tokens,
                    "error_message": error_message,
                }
            )

        payload: dict[str, Any] = {
            "name": run_name,
            "target": "dataset",
            "dataset_name": dataset,
            "outputs": outputs,
            "agent_version": agent_version,
            "prompt_version": prompt_version,
            "model_version": model_version,
            "metadata": metadata,
        }
        if evaluators:
            payload["evaluator_names"] = list(evaluators)

        return EvaluationRun.from_payload(self.post("/sdk/evaluation-runs", payload))

    def evaluate_traces(
        self,
        name: str,
        *,
        evaluators: Sequence[str] | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        prompt_version: str | None = None,
        status: str | None = None,
        limit: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationRun:
        """Score traces already stored in AgentLens, with no local execution."""

        payload: dict[str, Any] = {
            "name": name,
            "target": "traces",
            "selector": {
                "agent_name": agent_name,
                "agent_version": agent_version,
                "prompt_version": prompt_version,
                "status": status,
                "limit": limit,
            },
            "agent_version": agent_version,
            "prompt_version": prompt_version,
            "metadata": metadata,
        }
        if evaluators:
            payload["evaluator_names"] = list(evaluators)
        return EvaluationRun.from_payload(self.post("/sdk/evaluation-runs", payload))


__all__ = ["AgentLens", "AgentLensError", "SpanType"]

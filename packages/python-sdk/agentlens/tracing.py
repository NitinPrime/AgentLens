from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Any, Literal
from uuid import UUID, uuid4

from agentlens._util import utcnow

SpanType = Literal["LLM", "TOOL", "RETRIEVAL", "AGENT", "CHAIN", "CUSTOM"]


class SpanHandle:
    def __init__(
        self,
        client: Any,
        *,
        trace_id: UUID,
        name: str,
        span_type: SpanType = "CUSTOM",
        parent_span_id: UUID | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        stack: list["SpanHandle"] | None = None,
    ) -> None:
        self._client = client
        self.trace_id = trace_id
        self.id = uuid4()
        self.name = name
        self.span_type: SpanType = span_type
        self.parent_span_id = parent_span_id
        self.input = input
        self.output: Any = None
        self.metadata = metadata or {}
        self.status = "running"
        self.error_type: str | None = None
        self.error_message: str | None = None
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self._stack = stack if stack is not None else []

    def set_input(self, value: Any) -> None:
        self.input = value

    def set_output(self, value: Any) -> None:
        self.output = value

    def set_metadata(self, **values: Any) -> None:
        self.metadata.update(values)

    def _payload(self) -> dict[str, Any]:
        duration_ms = None
        if self.start_time and self.end_time:
            duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        return {
            "id": self.id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "type": self.span_type,
            "name": self.name,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": duration_ms,
            "input": self.input,
            "output": self.output,
            "metadata": self.metadata or None,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }

    def __enter__(self) -> "SpanHandle":
        self.start_time = utcnow()
        self._client.post("/spans", self._payload())
        self._stack.append(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.end_time = utcnow()
        if exc is not None:
            self.status = "error"
            self.error_type = exc_type.__name__ if exc_type else "Error"
            self.error_message = str(exc)
        elif self.status == "running":
            self.status = "success"
        if self._stack and self._stack[-1] is self:
            self._stack.pop()
        self._client.post("/spans", self._payload())


class LLMCallHandle(SpanHandle):
    def __init__(
        self,
        client: Any,
        *,
        trace_id: UUID,
        model: str,
        provider: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        temperature: float | None = None,
        messages: Any = None,
        parent_span_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        stack: list[SpanHandle] | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(
            client,
            trace_id=trace_id,
            name=name or model,
            span_type="LLM",
            parent_span_id=parent_span_id,
            input=messages,
            metadata=metadata,
            stack=stack,
        )
        self.call_id = uuid4()
        self.model = model
        self.provider = provider
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.temperature = temperature
        self.messages = messages
        self.completion: Any = None

    def set_usage(self, input_tokens: int | None = None, output_tokens: int | None = None) -> None:
        if input_tokens is not None:
            self.input_tokens = input_tokens
        if output_tokens is not None:
            self.output_tokens = output_tokens

    def set_completion(self, value: Any) -> None:
        self.completion = value
        self.output = value

    def _llm_payload(self) -> dict[str, Any]:
        latency_ms = None
        if self.start_time and self.end_time:
            latency_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        return {
            "id": self.call_id,
            "trace_id": self.trace_id,
            "span_id": self.id,
            "provider": self.provider,
            "model": self.model,
            "messages": self.messages if self.messages is not None else self.input,
            "completion": self.completion if self.completion is not None else self.output,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": latency_ms,
            "temperature": self.temperature,
            "metadata": self.metadata or None,
        }

    def __enter__(self) -> "LLMCallHandle":
        super().__enter__()
        self._client.post("/llm-calls", self._llm_payload())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc, tb)
        self._client.post("/llm-calls", self._llm_payload())


class ToolCallHandle(SpanHandle):
    def __init__(
        self,
        client: Any,
        *,
        trace_id: UUID,
        name: str,
        arguments: Any = None,
        retry_count: int = 0,
        parent_span_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        stack: list[SpanHandle] | None = None,
    ) -> None:
        super().__init__(
            client,
            trace_id=trace_id,
            name=name,
            span_type="TOOL",
            parent_span_id=parent_span_id,
            input=arguments,
            metadata=metadata,
            stack=stack,
        )
        self.call_id = uuid4()
        self.arguments = arguments
        self.retry_count = retry_count

    def _tool_payload(self) -> dict[str, Any]:
        duration_ms = None
        if self.start_time and self.end_time:
            duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        return {
            "id": self.call_id,
            "trace_id": self.trace_id,
            "span_id": self.id,
            "name": self.name,
            "arguments": self.arguments if self.arguments is not None else self.input,
            "output": self.output,
            "status": self.status,
            "duration_ms": duration_ms,
            "error": self.error_message,
            "retry_count": self.retry_count,
            "metadata": self.metadata or None,
        }

    def __enter__(self) -> "ToolCallHandle":
        super().__enter__()
        self._client.post("/tool-calls", self._tool_payload())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc, tb)
        self._client.post("/tool-calls", self._tool_payload())


class TraceHandle:
    def __init__(
        self,
        client: Any,
        *,
        name: str,
        agent_name: str | None = None,
        session_id: str | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        agent_version: str | None = None,
        prompt_version: str | None = None,
        model_version: str | None = None,
    ) -> None:
        self._client = client
        self.id = uuid4()
        self.name = name
        self.agent_name = agent_name
        self.session_id = session_id
        self.input = input
        self.output: Any = None
        self.metadata = metadata or {}
        self.agent_version = agent_version
        self.prompt_version = prompt_version
        self.model_version = model_version
        self.status = "running"
        self.error_type: str | None = None
        self.error_message: str | None = None
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.summary: dict[str, Any] = {}
        self._span_stack: list[SpanHandle] = []

    def set_input(self, value: Any) -> None:
        self.input = value

    def set_output(self, value: Any) -> None:
        self.output = value

    def set_metadata(self, **values: Any) -> None:
        self.metadata.update(values)

    def mark_error(self, error: BaseException | str) -> None:
        """Record a failure that the caller handled itself.

        Useful when a batch runner catches an exception but the trace should
        still be stored as an error rather than a success.
        """

        self.status = "error"
        if isinstance(error, BaseException):
            self.error_type = type(error).__name__
            self.error_message = str(error)
        else:
            self.error_type = self.error_type or "Error"
            self.error_message = str(error)

    @property
    def total_cost(self) -> float:
        """Server-computed cost for this trace, available after it closes."""

        return float(self.summary.get("total_cost") or 0)

    @property
    def total_tokens(self) -> int:
        return int(self.summary.get("total_tokens") or 0)

    def _parent_id(self) -> UUID | None:
        if not self._span_stack:
            return None
        return self._span_stack[-1].id

    def span(
        self,
        name: str,
        *,
        type: SpanType = "CUSTOM",
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanHandle:
        return SpanHandle(
            self._client,
            trace_id=self.id,
            name=name,
            span_type=type,
            parent_span_id=self._parent_id(),
            input=input,
            metadata=metadata,
            stack=self._span_stack,
        )

    def llm_call(
        self,
        *,
        model: str,
        provider: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        temperature: float | None = None,
        messages: Any = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> LLMCallHandle:
        return LLMCallHandle(
            self._client,
            trace_id=self.id,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            temperature=temperature,
            messages=messages,
            parent_span_id=self._parent_id(),
            metadata=metadata,
            stack=self._span_stack,
            name=name,
        )

    def tool_call(
        self,
        name: str,
        arguments: Any = None,
        *,
        retry_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> ToolCallHandle:
        return ToolCallHandle(
            self._client,
            trace_id=self.id,
            name=name,
            arguments=arguments,
            retry_count=retry_count,
            parent_span_id=self._parent_id(),
            metadata=metadata,
            stack=self._span_stack,
        )

    def event(self, name: str, body: Any = None) -> None:
        self._client.post(
            "/events",
            {
                "trace_id": self.id,
                "span_id": self._parent_id(),
                "name": name,
                "body": body,
                "timestamp": utcnow(),
            },
        )

    def _payload(self) -> dict[str, Any]:
        duration_ms = None
        if self.start_time and self.end_time:
            duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        return {
            "id": self.id,
            "name": self.name,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": duration_ms,
            "input": self.input,
            "output": self.output,
            "metadata": self.metadata or None,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "agent_version": self.agent_version,
            "prompt_version": self.prompt_version,
            "model_version": self.model_version,
        }

    def __enter__(self) -> "TraceHandle":
        self.start_time = utcnow()
        self.summary = self._client.post("/traces", self._payload()) or {}
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.end_time = utcnow()
        if exc is not None:
            self.status = "error"
            self.error_type = exc_type.__name__ if exc_type else "Error"
            self.error_message = str(exc)
        elif self.status == "running":
            self.status = "success"
        self.summary = self._client.post("/traces", self._payload()) or {}

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


class EvaluationFailed(Exception):
    """Raised when an evaluation run misses a quality gate."""


def _maybe_uuid(value: Any) -> UUID | str | None:
    """Parse an identifier without letting an unexpected format break the client."""

    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return str(value)


@dataclass
class DatasetItem:
    """One test case pulled from an AgentLens dataset."""

    id: UUID | str | None
    name: str | None
    input: Any = None
    expected_output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DatasetItem":
        return cls(
            id=_maybe_uuid(payload.get("id")),
            name=payload.get("name"),
            input=payload.get("input"),
            expected_output=payload.get("expected_output"),
            metadata=payload.get("metadata") or {},
        )


@dataclass
class EvaluationRun:
    """Server-side scoring result for one evaluation run."""

    id: UUID | str | None
    name: str
    status: str
    total_items: int
    passed_count: int
    failed_count: int
    pass_rate: float
    avg_score: float | None
    total_cost: float
    dataset_name: str | None = None
    agent_version: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EvaluationRun":
        return cls(
            id=_maybe_uuid(payload.get("id")),
            name=payload.get("name", ""),
            status=payload.get("status", "unknown"),
            total_items=int(payload.get("total_items") or 0),
            passed_count=int(payload.get("passed_count") or 0),
            failed_count=int(payload.get("failed_count") or 0),
            pass_rate=float(payload.get("pass_rate") or 0.0),
            avg_score=(
                float(payload["avg_score"]) if payload.get("avg_score") is not None else None
            ),
            total_cost=float(payload.get("total_cost") or 0),
            dataset_name=payload.get("dataset_name"),
            agent_version=payload.get("agent_version"),
            error_message=payload.get("error_message"),
            raw=payload,
        )

    def require_pass_rate(self, minimum: float) -> "EvaluationRun":
        """Fail the calling process when the run drops below ``minimum``.

        Intended for CI: ``lens.evaluate(...).require_pass_rate(0.9)``.
        """

        if self.pass_rate < minimum:
            raise EvaluationFailed(
                f"Evaluation '{self.name}' passed {self.pass_rate:.1%} of "
                f"{self.total_items} items, below the required {minimum:.1%}."
            )
        return self

    def __str__(self) -> str:
        score = f"{self.avg_score:.3f}" if self.avg_score is not None else "n/a"
        return (
            f"{self.name}: {self.passed_count}/{self.total_items} passed "
            f"({self.pass_rate:.1%}), avg score {score}"
        )

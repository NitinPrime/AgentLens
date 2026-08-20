"""Evaluator implementations used by the evaluation runner.

Every evaluator receives an :class:`EvalSubject` (the thing being judged) and
returns an :class:`EvalOutcome` with a normalised score in ``[0, 1]``, a pass
flag, a failure category label, and human-readable reasoning.

Deterministic evaluators run entirely offline. ``llm_judge`` calls an
OpenAI-compatible chat completions endpoint when ``OPENAI_API_KEY`` is
configured and otherwise falls back to a documented offline heuristic so
evaluations remain runnable without third-party credentials.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

JUDGE_SYSTEM_PROMPT = (
    "You are a strict evaluator of AI agent outputs. "
    "Score how well the output satisfies the criteria. "
    'Reply with JSON only: {"score": <number between 0 and 1>, "reasoning": "<one or two sentences>"}'
)


@dataclass
class EvalSubject:
    """A single unit under evaluation: one dataset item or one trace."""

    key: str
    input: Any = None
    output: Any = None
    expected_output: Any = None
    status: str = "success"
    duration_ms: int | None = None
    cost: Decimal = Decimal("0")
    total_tokens: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalOutcome:
    score: float
    passed: bool
    label: str
    reasoning: str


@dataclass(frozen=True)
class EvaluatorSpec:
    type: str
    title: str
    description: str
    requires_expected_output: bool = False
    default_threshold: float = 1.0
    default_config: dict[str, Any] = field(default_factory=dict)


EVALUATOR_SPECS: dict[str, EvaluatorSpec] = {
    "exact_match": EvaluatorSpec(
        type="exact_match",
        title="Exact match",
        description="Output must equal the expected output after optional trimming and case folding.",
        requires_expected_output=True,
        default_config={"case_sensitive": False, "trim": True},
    ),
    "contains": EvaluatorSpec(
        type="contains",
        title="Contains text",
        description="Output must contain a required substring (defaults to the expected output).",
        default_config={"value": "", "case_sensitive": False},
    ),
    "not_contains": EvaluatorSpec(
        type="not_contains",
        title="Does not contain text",
        description="Output must not contain a forbidden substring.",
        default_config={"value": "", "case_sensitive": False},
    ),
    "regex": EvaluatorSpec(
        type="regex",
        title="Regex match",
        description="Output must match a regular expression.",
        default_config={"pattern": ".+", "ignore_case": True},
    ),
    "json_field_match": EvaluatorSpec(
        type="json_field_match",
        title="JSON field match",
        description="A field inside a JSON output must equal an expected value.",
        default_config={"path": "", "expected": None},
    ),
    "numeric_tolerance": EvaluatorSpec(
        type="numeric_tolerance",
        title="Numeric tolerance",
        description="Numeric output must be within a tolerance of the expected number.",
        requires_expected_output=True,
        default_config={"tolerance": 0.01, "relative": False, "path": ""},
    ),
    "similarity": EvaluatorSpec(
        type="similarity",
        title="Token similarity",
        description="Token-overlap F1 between output and expected output.",
        requires_expected_output=True,
        default_threshold=0.8,
        default_config={"path": ""},
    ),
    "valid_json": EvaluatorSpec(
        type="valid_json",
        title="Valid JSON",
        description="Output must be a JSON object or array (or parse as one).",
        default_config={"require_object": False},
    ),
    "no_error": EvaluatorSpec(
        type="no_error",
        title="No error",
        description="The run must finish without an error status.",
    ),
    "latency_under": EvaluatorSpec(
        type="latency_under",
        title="Latency budget",
        description="Run duration must stay under a millisecond budget.",
        default_config={"max_ms": 5000},
    ),
    "cost_under": EvaluatorSpec(
        type="cost_under",
        title="Cost budget",
        description="Run cost must stay under a USD budget.",
        default_config={"max_cost": 0.05},
    ),
    "llm_judge": EvaluatorSpec(
        type="llm_judge",
        title="LLM as judge",
        description="An LLM scores the output against written criteria.",
        default_threshold=0.7,
        default_config={
            "criteria": "The answer is accurate, relevant, and complete.",
            "model": "",
        },
    ),
}

EVALUATOR_TYPES = tuple(EVALUATOR_SPECS)


class EvaluatorConfigError(ValueError):
    """Raised when an evaluator is created with an unusable configuration."""


def needs_expected_output(evaluator_type: str, config: dict[str, Any] | None) -> bool:
    """Whether this evaluator can only score subjects that have a reference answer.

    Most evaluators are decided by the static spec, but two are conditional:
    ``contains`` falls back to the expected output when no substring is
    configured, and ``json_field_match`` falls back to it when no literal is
    given. Runs over raw traces have no reference answer, so those must be
    skipped rather than reported as evaluator errors.
    """

    spec = EVALUATOR_SPECS.get(evaluator_type)
    if spec is None:
        return False
    if spec.requires_expected_output:
        return True
    merged = {**spec.default_config, **(config or {})}
    if evaluator_type == "contains":
        return not str(merged.get("value") or "").strip()
    if evaluator_type == "json_field_match":
        return merged.get("expected") is None
    return False


def validate_evaluator(evaluator_type: str, config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a normalised config for ``evaluator_type`` or raise on bad input."""

    spec = EVALUATOR_SPECS.get(evaluator_type)
    if spec is None:
        raise EvaluatorConfigError(
            f"Unknown evaluator type '{evaluator_type}'. Supported: {', '.join(EVALUATOR_TYPES)}"
        )

    merged: dict[str, Any] = {**spec.default_config, **(config or {})}

    if evaluator_type == "regex":
        pattern = str(merged.get("pattern") or "")
        if not pattern:
            raise EvaluatorConfigError("regex evaluator requires a 'pattern'")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise EvaluatorConfigError(f"Invalid regex pattern: {exc}") from exc

    if evaluator_type in {"contains", "not_contains"}:
        if evaluator_type == "not_contains" and not str(merged.get("value") or ""):
            raise EvaluatorConfigError("not_contains evaluator requires a 'value'")

    if evaluator_type == "json_field_match" and not str(merged.get("path") or ""):
        raise EvaluatorConfigError("json_field_match evaluator requires a 'path'")

    if evaluator_type == "numeric_tolerance":
        try:
            merged["tolerance"] = float(merged.get("tolerance", 0.01))
        except (TypeError, ValueError) as exc:
            raise EvaluatorConfigError("numeric_tolerance requires a numeric 'tolerance'") from exc

    if evaluator_type == "latency_under":
        try:
            merged["max_ms"] = int(merged.get("max_ms", 5000))
        except (TypeError, ValueError) as exc:
            raise EvaluatorConfigError("latency_under requires an integer 'max_ms'") from exc
        if merged["max_ms"] <= 0:
            raise EvaluatorConfigError("latency_under requires 'max_ms' greater than zero")

    if evaluator_type == "cost_under":
        try:
            merged["max_cost"] = float(merged.get("max_cost", 0.05))
        except (TypeError, ValueError) as exc:
            raise EvaluatorConfigError("cost_under requires a numeric 'max_cost'") from exc
        if merged["max_cost"] <= 0:
            raise EvaluatorConfigError("cost_under requires 'max_cost' greater than zero")

    if evaluator_type == "llm_judge" and not str(merged.get("criteria") or "").strip():
        raise EvaluatorConfigError("llm_judge evaluator requires 'criteria'")

    return merged


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def resolve_path(value: Any, path: str | None) -> Any:
    """Resolve a dotted path such as ``answer.items.0.label`` inside a JSON value."""

    if not path:
        return value
    current = value
    if isinstance(current, str):
        current = _try_parse_json(current)
    for part in str(path).split("."):
        if part == "":
            continue
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _try_parse_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{\"":
        return text
    try:
        return json.loads(stripped)
    except (TypeError, ValueError):
        return text


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def token_f1(actual: str, expected: str) -> float:
    left = Counter(_tokens(actual))
    right = Counter(_tokens(expected))
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    overlap = sum((left & right).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(left.values())
    recall = overlap / sum(right.values())
    return (2 * precision * recall) / (precision + recall)


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def _normalise(text: str, *, case_sensitive: bool, trim: bool) -> str:
    result = text.strip() if trim else text
    return result if case_sensitive else result.lower()


def _outcome(score: float, threshold: float, pass_label: str, fail_label: str, reasoning: str) -> EvalOutcome:
    clamped = min(max(float(score), 0.0), 1.0)
    passed = clamped >= threshold - 1e-9
    return EvalOutcome(
        score=clamped,
        passed=passed,
        label=pass_label if passed else fail_label,
        reasoning=reasoning,
    )


async def run_evaluator(
    evaluator_type: str,
    config: dict[str, Any] | None,
    threshold: float,
    subject: EvalSubject,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> EvalOutcome:
    """Score ``subject`` with one evaluator, never raising for bad data."""

    cfg = {**EVALUATOR_SPECS[evaluator_type].default_config, **(config or {})} if evaluator_type in EVALUATOR_SPECS else dict(config or {})
    try:
        handler = _HANDLERS.get(evaluator_type)
        if handler is None:
            return EvalOutcome(
                score=0.0,
                passed=False,
                label="evaluator_error",
                reasoning=f"Unknown evaluator type '{evaluator_type}'.",
            )
        if evaluator_type == "llm_judge":
            return await _judge(cfg, threshold, subject, http_client=http_client)
        return handler(cfg, threshold, subject)
    except Exception as exc:  # defensive: one bad item must not kill a run
        return EvalOutcome(
            score=0.0,
            passed=False,
            label="evaluator_error",
            reasoning=f"{type(exc).__name__}: {exc}",
        )


def _exact_match(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    case_sensitive = bool(cfg.get("case_sensitive", False))
    trim = bool(cfg.get("trim", True))
    actual = as_text(resolve_path(subject.output, cfg.get("path")))
    expected = as_text(resolve_path(subject.expected_output, cfg.get("path")))
    left = _normalise(actual, case_sensitive=case_sensitive, trim=trim)
    right = _normalise(expected, case_sensitive=case_sensitive, trim=trim)
    score = 1.0 if left == right else 0.0
    reasoning = (
        "Output matched the expected value exactly."
        if score
        else f"Expected {right[:120]!r} but got {left[:120]!r}."
    )
    return _outcome(score, threshold, "pass", "mismatch", reasoning)


def _contains(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    case_sensitive = bool(cfg.get("case_sensitive", False))
    needle = str(cfg.get("value") or "") or as_text(subject.expected_output)
    haystack = as_text(resolve_path(subject.output, cfg.get("path")))
    if not needle:
        return EvalOutcome(
            score=0.0,
            passed=False,
            label="evaluator_error",
            reasoning="No substring configured and the item has no expected output.",
        )
    left = haystack if case_sensitive else haystack.lower()
    right = needle if case_sensitive else needle.lower()
    score = 1.0 if right in left else 0.0
    reasoning = (
        f"Output contains {needle[:80]!r}."
        if score
        else f"Output is missing required text {needle[:80]!r}."
    )
    return _outcome(score, threshold, "pass", "missing_content", reasoning)


def _not_contains(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    case_sensitive = bool(cfg.get("case_sensitive", False))
    needle = str(cfg.get("value") or "")
    haystack = as_text(resolve_path(subject.output, cfg.get("path")))
    if not needle:
        return EvalOutcome(
            score=0.0,
            passed=False,
            label="evaluator_error",
            reasoning="not_contains requires a configured 'value'.",
        )
    left = haystack if case_sensitive else haystack.lower()
    right = needle if case_sensitive else needle.lower()
    score = 0.0 if right in left else 1.0
    reasoning = (
        f"Output does not contain {needle[:80]!r}."
        if score
        else f"Output contains forbidden text {needle[:80]!r}."
    )
    return _outcome(score, threshold, "pass", "forbidden_content", reasoning)


def _regex(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    pattern = str(cfg.get("pattern") or "")
    if not pattern:
        return EvalOutcome(0.0, False, "evaluator_error", "regex evaluator has no pattern.")
    flags = re.IGNORECASE if cfg.get("ignore_case", True) else 0
    if cfg.get("multiline"):
        flags |= re.MULTILINE
    text = as_text(resolve_path(subject.output, cfg.get("path")))
    score = 1.0 if re.search(pattern, text, flags) else 0.0
    reasoning = (
        f"Output matched /{pattern}/."
        if score
        else f"Output did not match /{pattern}/."
    )
    return _outcome(score, threshold, "pass", "format_violation", reasoning)


def _json_field_match(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    path = str(cfg.get("path") or "")
    if not path:
        return EvalOutcome(0.0, False, "evaluator_error", "json_field_match requires a 'path'.")
    actual = resolve_path(subject.output, path)
    expected = cfg["expected"] if "expected" in cfg and cfg["expected"] is not None else resolve_path(
        subject.expected_output, path
    )
    if actual is None and expected is None:
        return _outcome(0.0, threshold, "pass", "missing_field", f"Field '{path}' is absent from both sides.")
    score = 1.0 if as_text(actual).strip().lower() == as_text(expected).strip().lower() else 0.0
    reasoning = (
        f"Field '{path}' matched."
        if score
        else f"Field '{path}': expected {as_text(expected)[:80]!r}, got {as_text(actual)[:80]!r}."
    )
    return _outcome(score, threshold, "pass", "mismatch", reasoning)


def _numeric_tolerance(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    tolerance = float(cfg.get("tolerance", 0.01))
    relative = bool(cfg.get("relative", False))
    actual = _to_float(resolve_path(subject.output, cfg.get("path")))
    expected = _to_float(resolve_path(subject.expected_output, cfg.get("path")))
    if actual is None or expected is None:
        return EvalOutcome(
            score=0.0,
            passed=False,
            label="invalid_format",
            reasoning="Could not read a number from the output or expected output.",
        )
    diff = abs(actual - expected)
    allowed = tolerance * abs(expected) if relative else tolerance
    score = 1.0 if diff <= allowed + 1e-12 else 0.0
    reasoning = (
        f"{actual} is within {allowed} of {expected}."
        if score
        else f"{actual} differs from {expected} by {diff}, allowed {allowed}."
    )
    return _outcome(score, threshold, "pass", "numeric_drift", reasoning)


def _similarity(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    actual = as_text(resolve_path(subject.output, cfg.get("path")))
    expected = as_text(resolve_path(subject.expected_output, cfg.get("path")))
    if not expected:
        return EvalOutcome(
            score=0.0,
            passed=False,
            label="evaluator_error",
            reasoning="similarity requires an expected output.",
        )
    score = token_f1(actual, expected)
    return _outcome(
        score,
        threshold,
        "pass",
        "low_similarity",
        f"Token overlap F1 is {score:.2f} against a threshold of {threshold:.2f}.",
    )


def _valid_json(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    value = resolve_path(subject.output, cfg.get("path"))
    if isinstance(value, str):
        value = _try_parse_json(value)
    require_object = bool(cfg.get("require_object", False))
    ok = isinstance(value, dict) if require_object else isinstance(value, (dict, list))
    score = 1.0 if ok else 0.0
    wanted = "object" if require_object else "object or array"
    reasoning = f"Output is a JSON {wanted}." if score else f"Output is not a JSON {wanted}."
    return _outcome(score, threshold, "pass", "invalid_format", reasoning)


def _no_error(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    failed = subject.status in {"error", "failed"} or bool(subject.error_message)
    score = 0.0 if failed else 1.0
    reasoning = (
        "Run completed without an error."
        if score
        else f"Run failed with status '{subject.status}': {(subject.error_message or 'no message')[:120]}"
    )
    return _outcome(score, threshold, "pass", "runtime_error", reasoning)


def _latency_under(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    max_ms = int(cfg.get("max_ms", 5000))
    if subject.duration_ms is None:
        return EvalOutcome(
            score=0.0,
            passed=False,
            label="missing_metric",
            reasoning="No duration recorded for this run.",
        )
    score = 1.0 if subject.duration_ms <= max_ms else 0.0
    reasoning = f"Duration {subject.duration_ms}ms against a {max_ms}ms budget."
    return _outcome(score, threshold, "pass", "slow", reasoning)


def _cost_under(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    max_cost = float(cfg.get("max_cost", 0.05))
    actual = float(subject.cost or 0)
    score = 1.0 if actual <= max_cost + 1e-12 else 0.0
    reasoning = f"Cost ${actual:.6f} against a ${max_cost:.6f} budget."
    return _outcome(score, threshold, "pass", "expensive", reasoning)


def _heuristic_judge(cfg: dict[str, Any], threshold: float, subject: EvalSubject) -> EvalOutcome:
    """Offline stand-in for a hosted judge model.

    With an expected output it reports token-overlap F1. Without one it measures
    how much of the criteria vocabulary the output covers, so the score still
    moves with output quality instead of being a constant.
    """

    output_text = as_text(subject.output)
    expected_text = as_text(subject.expected_output)
    criteria = str(cfg.get("criteria") or "")

    if not output_text.strip():
        return _outcome(0.0, threshold, "pass", "empty_output", "Offline judge: the output was empty.")

    if expected_text.strip():
        score = token_f1(output_text, expected_text)
        detail = f"overlap with the expected answer is {score:.2f}"
    else:
        criteria_tokens = {token for token in _tokens(criteria) if len(token) > 3}
        output_tokens = set(_tokens(output_text))
        coverage = (
            len(criteria_tokens & output_tokens) / len(criteria_tokens) if criteria_tokens else 0.0
        )
        length_signal = min(len(_tokens(output_text)) / 40.0, 1.0)
        score = 0.5 * length_signal + 0.5 * coverage
        detail = f"criteria coverage {coverage:.2f}, response depth {length_signal:.2f}"

    return _outcome(
        score,
        threshold,
        "pass",
        "quality",
        f"Offline heuristic judge (no OPENAI_API_KEY configured): {detail}.",
    )


def _parse_judge_payload(content: str) -> tuple[float | None, str]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None, text[:500]
        return float(match.group(0)), text[:500]
    if not isinstance(data, dict):
        return None, text[:500]
    score = _to_float(data.get("score"))
    reasoning = str(data.get("reasoning") or data.get("explanation") or "").strip()
    return score, reasoning[:2000]


async def _judge(
    cfg: dict[str, Any],
    threshold: float,
    subject: EvalSubject,
    *,
    http_client: httpx.AsyncClient | None,
) -> EvalOutcome:
    api_key = settings.openai_api_key
    if not api_key:
        return _heuristic_judge(cfg, threshold, subject)

    criteria = str(cfg.get("criteria") or "The answer is accurate and relevant.")
    model = str(cfg.get("model") or "") or settings.judge_model
    user_prompt = "\n\n".join(
        part
        for part in [
            f"Criteria:\n{criteria}",
            f"Agent input:\n{as_text(subject.input)[:4000]}" if subject.input is not None else "",
            f"Agent output:\n{as_text(subject.output)[:4000]}",
            f"Reference answer:\n{as_text(subject.expected_output)[:4000]}"
            if subject.expected_output is not None
            else "",
        ]
        if part
    )

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=settings.judge_timeout_seconds)
    try:
        response = await client.post(
            f"{settings.judge_base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code >= 400:
            return EvalOutcome(
                score=0.0,
                passed=False,
                label="judge_error",
                reasoning=f"Judge model returned HTTP {response.status_code}: {response.text[:200]}",
            )
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except Exception as exc:
        return EvalOutcome(
            score=0.0,
            passed=False,
            label="judge_error",
            reasoning=f"Judge model call failed ({type(exc).__name__}): {exc}",
        )
    finally:
        if owns_client:
            await client.aclose()

    score, reasoning = _parse_judge_payload(content)
    if score is None or math.isnan(score):
        return EvalOutcome(
            score=0.0,
            passed=False,
            label="judge_error",
            reasoning=f"Could not read a score from the judge response: {reasoning[:200]}",
        )
    if score > 1.0:
        score = score / 10.0 if score <= 10.0 else 1.0
    return _outcome(score, threshold, "pass", "quality", reasoning or f"Judge scored {score:.2f}.")


_HANDLERS = {
    "exact_match": _exact_match,
    "contains": _contains,
    "not_contains": _not_contains,
    "regex": _regex,
    "json_field_match": _json_field_match,
    "numeric_tolerance": _numeric_tolerance,
    "similarity": _similarity,
    "valid_json": _valid_json,
    "no_error": _no_error,
    "latency_under": _latency_under,
    "cost_under": _cost_under,
    "llm_judge": _judge,
}

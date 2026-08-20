from decimal import Decimal

import pytest

from app.core.evaluators import (
    EVALUATOR_SPECS,
    EvalSubject,
    EvaluatorConfigError,
    resolve_path,
    run_evaluator,
    token_f1,
    validate_evaluator,
)


def subject(**overrides) -> EvalSubject:
    defaults = {
        "key": "item-1",
        "input": "Where is my order?",
        "output": "Your order ships tomorrow.",
        "expected_output": "Your order ships tomorrow.",
        "status": "success",
        "duration_ms": 1200,
        "cost": Decimal("0.002"),
    }
    defaults.update(overrides)
    return EvalSubject(**defaults)


@pytest.mark.asyncio
async def test_exact_match_passes_and_fails():
    passing = await run_evaluator("exact_match", {}, 1.0, subject())
    assert passing.passed is True
    assert passing.score == 1.0
    assert passing.label == "pass"

    failing = await run_evaluator("exact_match", {}, 1.0, subject(output="No idea."))
    assert failing.passed is False
    assert failing.label == "mismatch"


@pytest.mark.asyncio
async def test_exact_match_is_case_insensitive_by_default():
    outcome = await run_evaluator("exact_match", {}, 1.0, subject(output="YOUR ORDER SHIPS TOMORROW."))
    assert outcome.passed is True

    strict = await run_evaluator(
        "exact_match", {"case_sensitive": True}, 1.0, subject(output="YOUR ORDER SHIPS TOMORROW.")
    )
    assert strict.passed is False


@pytest.mark.asyncio
async def test_contains_falls_back_to_expected_output():
    outcome = await run_evaluator("contains", {}, 1.0, subject(output="Great news: your order ships tomorrow."))
    assert outcome.passed is True

    explicit = await run_evaluator("contains", {"value": "refund"}, 1.0, subject())
    assert explicit.passed is False
    assert explicit.label == "missing_content"


@pytest.mark.asyncio
async def test_not_contains_flags_forbidden_text():
    outcome = await run_evaluator(
        "not_contains", {"value": "as an AI language model"}, 1.0, subject()
    )
    assert outcome.passed is True

    violated = await run_evaluator(
        "not_contains",
        {"value": "as an AI language model"},
        1.0,
        subject(output="As an AI language model I cannot help."),
    )
    assert violated.passed is False
    assert violated.label == "forbidden_content"


@pytest.mark.asyncio
async def test_regex_matches_structured_output():
    outcome = await run_evaluator(
        "regex", {"pattern": r"ships (today|tomorrow)"}, 1.0, subject()
    )
    assert outcome.passed is True

    failed = await run_evaluator("regex", {"pattern": r"^ORDER-\d+$"}, 1.0, subject())
    assert failed.passed is False
    assert failed.label == "format_violation"


@pytest.mark.asyncio
async def test_json_field_match_uses_dotted_paths():
    payload = {"answer": {"status": "shipped", "eta_days": 1}}
    outcome = await run_evaluator(
        "json_field_match",
        {"path": "answer.status", "expected": "shipped"},
        1.0,
        subject(output=payload, expected_output=None),
    )
    assert outcome.passed is True

    mismatch = await run_evaluator(
        "json_field_match",
        {"path": "answer.status", "expected": "delayed"},
        1.0,
        subject(output=payload, expected_output=None),
    )
    assert mismatch.passed is False


@pytest.mark.asyncio
async def test_numeric_tolerance_absolute_and_relative():
    close = await run_evaluator(
        "numeric_tolerance",
        {"tolerance": 0.5},
        1.0,
        subject(output="42.2", expected_output="42.0"),
    )
    assert close.passed is True

    far = await run_evaluator(
        "numeric_tolerance",
        {"tolerance": 0.1},
        1.0,
        subject(output="50", expected_output="42"),
    )
    assert far.passed is False
    assert far.label == "numeric_drift"

    relative = await run_evaluator(
        "numeric_tolerance",
        {"tolerance": 0.25, "relative": True},
        1.0,
        subject(output="50", expected_output="42"),
    )
    assert relative.passed is True


@pytest.mark.asyncio
async def test_similarity_scores_partial_overlap():
    outcome = await run_evaluator(
        "similarity", {}, 0.5, subject(output="Your order will ship tomorrow morning.")
    )
    assert 0.5 <= outcome.score < 1.0
    assert outcome.passed is True

    poor = await run_evaluator("similarity", {}, 0.8, subject(output="Completely unrelated text."))
    assert poor.passed is False
    assert poor.label == "low_similarity"


@pytest.mark.asyncio
async def test_valid_json_accepts_objects_and_json_strings():
    parsed = await run_evaluator("valid_json", {}, 1.0, subject(output={"ok": True}))
    assert parsed.passed is True

    from_string = await run_evaluator("valid_json", {}, 1.0, subject(output='{"ok": true}'))
    assert from_string.passed is True

    prose = await run_evaluator("valid_json", {}, 1.0, subject(output="not json"))
    assert prose.passed is False
    assert prose.label == "invalid_format"


@pytest.mark.asyncio
async def test_no_error_reflects_run_status():
    ok = await run_evaluator("no_error", {}, 1.0, subject())
    assert ok.passed is True

    failed = await run_evaluator(
        "no_error", {}, 1.0, subject(status="error", error_message="tool timeout")
    )
    assert failed.passed is False
    assert failed.label == "runtime_error"
    assert "tool timeout" in failed.reasoning


@pytest.mark.asyncio
async def test_latency_and_cost_budgets():
    fast = await run_evaluator("latency_under", {"max_ms": 2000}, 1.0, subject())
    assert fast.passed is True

    slow = await run_evaluator("latency_under", {"max_ms": 500}, 1.0, subject())
    assert slow.passed is False
    assert slow.label == "slow"

    cheap = await run_evaluator("cost_under", {"max_cost": 0.01}, 1.0, subject())
    assert cheap.passed is True

    pricey = await run_evaluator("cost_under", {"max_cost": 0.0001}, 1.0, subject())
    assert pricey.passed is False
    assert pricey.label == "expensive"


@pytest.mark.asyncio
async def test_llm_judge_uses_offline_heuristic_without_api_key():
    good = await run_evaluator(
        "llm_judge", {"criteria": "The answer states the shipping date."}, 0.7, subject()
    )
    assert good.passed is True
    assert "heuristic" in good.reasoning.lower()

    empty = await run_evaluator("llm_judge", {"criteria": "Anything."}, 0.7, subject(output=""))
    assert empty.passed is False
    assert empty.label == "empty_output"


@pytest.mark.asyncio
async def test_unknown_evaluator_type_is_reported_not_raised():
    outcome = await run_evaluator("does_not_exist", {}, 1.0, subject())
    assert outcome.passed is False
    assert outcome.label == "evaluator_error"


def test_validate_evaluator_rejects_bad_config():
    with pytest.raises(EvaluatorConfigError):
        validate_evaluator("regex", {"pattern": "([unclosed"})
    with pytest.raises(EvaluatorConfigError):
        validate_evaluator("json_field_match", {})
    with pytest.raises(EvaluatorConfigError):
        validate_evaluator("latency_under", {"max_ms": 0})
    with pytest.raises(EvaluatorConfigError):
        validate_evaluator("llm_judge", {"criteria": "   "})
    with pytest.raises(EvaluatorConfigError):
        validate_evaluator("nope", {})


def test_validate_evaluator_merges_defaults():
    config = validate_evaluator("exact_match", {"case_sensitive": True})
    assert config == {"case_sensitive": True, "trim": True}


def test_every_spec_has_a_handler():
    from app.core.evaluators import _HANDLERS

    assert set(EVALUATOR_SPECS) == set(_HANDLERS)


def test_resolve_path_walks_lists_and_json_strings():
    assert resolve_path({"a": {"b": [1, 2, 3]}}, "a.b.1") == 2
    assert resolve_path('{"a": 5}', "a") == 5
    assert resolve_path({"a": 1}, "missing") is None


def test_token_f1_bounds():
    assert token_f1("same words", "same words") == 1.0
    assert token_f1("nothing alike", "totally different") == 0.0

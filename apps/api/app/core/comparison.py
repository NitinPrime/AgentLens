"""Shared metric-delta maths for regression checks.

Used by both evaluation-run comparison and version comparison so the two
surfaces agree on what counts as a regression.
"""

from __future__ import annotations

from app.schemas.evaluations import MetricDelta


def metric_delta(
    metric: str,
    baseline: float | None,
    candidate: float | None,
    higher_is_better: bool,
    tolerance: float,
    *,
    relative: bool = False,
) -> MetricDelta:
    """Compare one metric between a baseline and a candidate.

    ``tolerance`` is an absolute allowance unless ``relative`` is set, in which
    case it is a fraction of the baseline value. A metric with no data on either
    side is reported without a verdict rather than as a regression.
    """

    delta: float | None = None
    pct: float | None = None
    regression = False

    if baseline is not None and candidate is not None:
        delta = candidate - baseline
        if baseline:
            pct = delta / abs(baseline)
        if higher_is_better:
            regression = -delta > tolerance
        elif relative:
            regression = pct is not None and pct > tolerance
        else:
            regression = delta > tolerance

    return MetricDelta(
        metric=metric,
        baseline=baseline,
        candidate=candidate,
        delta=delta,
        pct_change=pct,
        higher_is_better=higher_is_better,
        regression=regression,
    )

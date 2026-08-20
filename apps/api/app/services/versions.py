"""Version rollups and regression detection over ingested traces.

Every agent run carries optional ``agent_version``, ``prompt_version``, and
``model_version`` labels. These helpers turn those labels into comparable
quality/cost/latency profiles so a candidate build can be checked against a
known-good baseline before it ships.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.comparison import metric_delta
from app.models.trace import Trace
from app.schemas.versions import VersionComparison, VersionListResponse, VersionStats
from app.services.analytics import resolve_window
from app.services.organizations import OrganizationError

PERCENTILE_SAMPLE_LIMIT = 50_000

DIMENSIONS = {
    "agent_version": Trace.agent_version,
    "prompt_version": Trace.prompt_version,
    "model_version": Trace.model_version,
    "agent_name": Trace.agent_name,
}


def _percentile(sorted_values: list[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


class VersionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _column(self, dimension: str):
        column = DIMENSIONS.get(dimension)
        if column is None:
            raise OrganizationError(
                f"Invalid dimension. Use one of: {', '.join(DIMENSIONS)}", status_code=400
            )
        return column

    async def _stats(
        self,
        project_id: UUID,
        dimension: str,
        window_start: datetime,
        window_end: datetime,
        only: str | None = None,
    ) -> list[VersionStats]:
        column = self._column(dimension)
        filters = [
            Trace.project_id == project_id,
            Trace.start_time >= window_start,
            Trace.start_time < window_end,
            column.is_not(None),
        ]
        if only is not None:
            filters.append(column == only)

        rows = await self.db.execute(
            select(
                column,
                func.count(Trace.id),
                func.coalesce(func.sum(case((Trace.status == "success", 1), else_=0)), 0),
                func.coalesce(func.sum(case((Trace.status == "error", 1), else_=0)), 0),
                func.avg(Trace.duration_ms),
                func.coalesce(func.sum(Trace.total_tokens), 0),
                func.coalesce(func.sum(Trace.total_cost), 0),
                func.min(Trace.start_time),
                func.max(Trace.start_time),
            )
            .where(*filters)
            .group_by(column)
            .order_by(func.count(Trace.id).desc())
        )

        samples = await self.db.execute(
            select(column, Trace.duration_ms)
            .where(*filters, Trace.duration_ms.is_not(None))
            .order_by(Trace.start_time.desc())
            .limit(PERCENTILE_SAMPLE_LIMIT)
        )
        durations: dict[str, list[float]] = {}
        for version, duration in samples.all():
            durations.setdefault(str(version), []).append(float(duration))

        stats: list[VersionStats] = []
        for row in rows.all():
            version = str(row[0])
            runs = int(row[1] or 0)
            success = int(row[2] or 0)
            errors = int(row[3] or 0)
            total_tokens = int(row[5] or 0)
            total_cost = Decimal(str(row[6] or 0))
            sample = sorted(durations.get(version, []))
            stats.append(
                VersionStats(
                    version=version,
                    runs=runs,
                    success_count=success,
                    error_count=errors,
                    success_rate=(success / runs) if runs else 0.0,
                    error_rate=(errors / runs) if runs else 0.0,
                    avg_latency_ms=float(row[4]) if row[4] is not None else None,
                    p50_latency_ms=_percentile(sample, 0.5),
                    p95_latency_ms=_percentile(sample, 0.95),
                    total_tokens=total_tokens,
                    avg_tokens=(total_tokens / runs) if runs else None,
                    total_cost=total_cost,
                    avg_cost=(total_cost / runs) if runs else Decimal("0"),
                    first_seen=row[7],
                    last_seen=row[8],
                )
            )
        return stats

    async def list_versions(
        self,
        project_id: UUID,
        *,
        dimension: str = "agent_version",
        range_key: str = "30d",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> VersionListResponse:
        window_start, window_end, _grain, label = resolve_window(range_key, start, end)
        return VersionListResponse(
            dimension=dimension,
            range=label,
            start=window_start,
            end=window_end,
            versions=await self._stats(project_id, dimension, window_start, window_end),
        )

    async def compare(
        self,
        project_id: UUID,
        *,
        dimension: str,
        baseline: str,
        candidate: str,
        range_key: str = "30d",
        start: datetime | None = None,
        end: datetime | None = None,
        max_success_rate_drop: float = 0.05,
        max_latency_increase: float = 0.25,
        max_cost_increase: float = 0.25,
    ) -> VersionComparison:
        window_start, window_end, _grain, label = resolve_window(range_key, start, end)

        baseline_stats = await self._stats(project_id, dimension, window_start, window_end, only=baseline)
        candidate_stats = await self._stats(project_id, dimension, window_start, window_end, only=candidate)
        if not baseline_stats:
            raise OrganizationError(f"No runs found for baseline '{baseline}'", status_code=404)
        if not candidate_stats:
            raise OrganizationError(f"No runs found for candidate '{candidate}'", status_code=404)

        before = baseline_stats[0]
        after = candidate_stats[0]

        metrics = [
            metric_delta("success_rate", before.success_rate, after.success_rate, True, max_success_rate_drop),
            metric_delta("error_rate", before.error_rate, after.error_rate, False, max_success_rate_drop),
            metric_delta(
                "p95_latency_ms",
                before.p95_latency_ms,
                after.p95_latency_ms,
                False,
                max_latency_increase,
                relative=True,
            ),
            metric_delta(
                "avg_latency_ms",
                before.avg_latency_ms,
                after.avg_latency_ms,
                False,
                max_latency_increase,
                relative=True,
            ),
            metric_delta(
                "avg_cost",
                float(before.avg_cost),
                float(after.avg_cost),
                False,
                max_cost_increase,
                relative=True,
            ),
            metric_delta(
                "avg_tokens",
                before.avg_tokens,
                after.avg_tokens,
                False,
                max_cost_increase,
                relative=True,
            ),
        ]

        quality_regressions = [m for m in metrics if m.regression and m.metric in {"success_rate", "error_rate"}]
        other_regressions = [m for m in metrics if m.regression and m not in quality_regressions]

        if quality_regressions:
            verdict = "fail"
            change = (after.success_rate - before.success_rate) * 100
            summary = (
                f"{candidate} regressed against {baseline}: success rate moved "
                f"{before.success_rate * 100:.1f}% to {after.success_rate * 100:.1f}% "
                f"({change:+.1f} points)."
            )
        elif other_regressions:
            verdict = "warn"
            names = ", ".join(m.metric for m in other_regressions)
            summary = f"{candidate} holds quality but got worse on {names}."
        else:
            verdict = "pass"
            summary = (
                f"{candidate} is clean against {baseline} across "
                f"{after.runs} runs versus {before.runs} baseline runs."
            )

        return VersionComparison(
            dimension=dimension,
            range=label,
            start=window_start,
            end=window_end,
            baseline=before,
            candidate=after,
            metrics=metrics,
            verdict=verdict,
            summary=summary,
        )

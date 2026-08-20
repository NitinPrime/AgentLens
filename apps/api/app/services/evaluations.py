from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from statistics import fmean
from uuid import UUID

import httpx
from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.comparison import metric_delta
from app.core.evaluators import (
    EVALUATOR_SPECS,
    EvalSubject,
    EvaluatorConfigError,
    needs_expected_output,
    run_evaluator,
    validate_evaluator,
)
from app.models.evaluation import (
    Dataset,
    DatasetItem,
    EvaluationResult,
    EvaluationRun,
    Evaluator,
    PromptVersion,
)
from app.models.trace import Trace
from app.schemas.evaluations import (
    DatasetCreate,
    DatasetItemBulkCreate,
    DatasetItemResponse,
    DatasetResponse,
    DatasetUpdate,
    EvaluationResultResponse,
    EvaluationRunCreate,
    EvaluationRunDetail,
    EvaluationRunResponse,
    EvaluatorCreate,
    EvaluatorResponse,
    EvaluatorDelta,
    EvaluatorScore,
    EvaluatorUpdate,
    FailureCategory,
    PromptVersionCreate,
    PromptVersionResponse,
    RunComparison,
    SubjectChange,
    TraceSelector,
)
from app.services.organizations import OrganizationError

settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pass_rate(passed: int, total: int) -> float:
    return (passed / total) if total else 0.0


def dataset_to_response(dataset: Dataset, item_count: int = 0) -> DatasetResponse:
    return DatasetResponse(
        id=dataset.id,
        project_id=dataset.project_id,
        name=dataset.name,
        description=dataset.description,
        item_count=item_count,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


def item_to_response(item: DatasetItem) -> DatasetItemResponse:
    return DatasetItemResponse(
        id=item.id,
        dataset_id=item.dataset_id,
        name=item.name,
        input=item.input,
        expected_output=item.expected_output,
        metadata=item.extra_metadata,
        created_at=item.created_at,
    )


def evaluator_to_response(evaluator: Evaluator) -> EvaluatorResponse:
    return EvaluatorResponse.model_validate(evaluator)


def result_to_response(result: EvaluationResult) -> EvaluationResultResponse:
    return EvaluationResultResponse(
        id=result.id,
        run_id=result.run_id,
        evaluator_id=result.evaluator_id,
        evaluator_name=result.evaluator_name,
        evaluator_type=result.evaluator_type,
        dataset_item_id=result.dataset_item_id,
        trace_id=result.trace_id,
        subject_key=result.subject_key,
        score=result.score,
        passed=result.passed,
        label=result.label,
        reasoning=result.reasoning,
        output=result.output,
        expected_output=result.expected_output,
        latency_ms=result.latency_ms,
        cost=result.cost,
        created_at=result.created_at,
    )


def run_to_response(run: EvaluationRun, dataset_name: str | None = None) -> EvaluationRunResponse:
    return EvaluationRunResponse(
        id=run.id,
        project_id=run.project_id,
        dataset_id=run.dataset_id,
        dataset_name=dataset_name,
        name=run.name,
        target=run.target,
        status=run.status,
        agent_version=run.agent_version,
        prompt_version=run.prompt_version,
        model_version=run.model_version,
        total_items=run.total_items,
        passed_count=run.passed_count,
        failed_count=run.failed_count,
        pass_rate=_pass_rate(run.passed_count, run.total_items),
        avg_score=run.avg_score,
        total_cost=run.total_cost,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


def prompt_version_to_response(version: PromptVersion) -> PromptVersionResponse:
    return PromptVersionResponse(
        id=version.id,
        project_id=version.project_id,
        name=version.name,
        version=version.version,
        template=version.template,
        notes=version.notes,
        is_active=version.is_active,
        metadata=version.extra_metadata,
        created_at=version.created_at,
    )


class EvaluationService:
    """Datasets, evaluators, and the evaluation runner.

    Callers must verify project access before invoking these methods; every
    query is additionally scoped by ``project_id`` so a wrong id surfaces as a
    404 rather than leaking another tenant's data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------------- datasets

    async def create_dataset(self, project_id: UUID, data: DatasetCreate) -> Dataset:
        dataset = Dataset(
            project_id=project_id,
            name=data.name.strip(),
            description=data.description,
        )
        self.db.add(dataset)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise OrganizationError("A dataset with that name already exists", status_code=400) from exc
        await self.db.refresh(dataset)
        return dataset

    async def list_datasets(self, project_id: UUID) -> list[tuple[Dataset, int]]:
        counts = await self.db.execute(
            select(DatasetItem.dataset_id, func.count(DatasetItem.id))
            .where(DatasetItem.project_id == project_id)
            .group_by(DatasetItem.dataset_id)
        )
        count_map = {row[0]: int(row[1]) for row in counts.all()}
        result = await self.db.execute(
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .order_by(Dataset.created_at.desc())
        )
        return [(dataset, count_map.get(dataset.id, 0)) for dataset in result.scalars().all()]

    async def get_dataset(self, project_id: UUID, dataset_id: UUID) -> Dataset:
        result = await self.db.execute(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
        )
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise OrganizationError("Dataset not found", status_code=404)
        return dataset

    async def get_dataset_by_name(self, project_id: UUID, name: str) -> Dataset:
        result = await self.db.execute(
            select(Dataset).where(Dataset.project_id == project_id, Dataset.name == name)
        )
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise OrganizationError("Dataset not found", status_code=404)
        return dataset

    async def count_items(self, dataset_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(DatasetItem.id)).where(DatasetItem.dataset_id == dataset_id)
        )
        return int(result.scalar_one())

    async def update_dataset(self, project_id: UUID, dataset_id: UUID, data: DatasetUpdate) -> Dataset:
        dataset = await self.get_dataset(project_id, dataset_id)
        if data.name is not None:
            dataset.name = data.name.strip()
        if data.description is not None:
            dataset.description = data.description
        await self.db.flush()
        await self.db.refresh(dataset)
        return dataset

    async def delete_dataset(self, project_id: UUID, dataset_id: UUID) -> None:
        dataset = await self.get_dataset(project_id, dataset_id)
        await self.db.delete(dataset)
        await self.db.flush()

    async def add_items(
        self, project_id: UUID, dataset_id: UUID, data: DatasetItemBulkCreate
    ) -> list[DatasetItem]:
        dataset = await self.get_dataset(project_id, dataset_id)
        if data.replace:
            await self.db.execute(delete(DatasetItem).where(DatasetItem.dataset_id == dataset.id))
        created: list[DatasetItem] = []
        for payload in data.items:
            item = DatasetItem(
                dataset_id=dataset.id,
                project_id=project_id,
                name=payload.name,
                input=payload.input,
                expected_output=payload.expected_output,
                extra_metadata=payload.metadata,
            )
            self.db.add(item)
            created.append(item)
        await self.db.flush()
        for item in created:
            await self.db.refresh(item)
        return created

    async def list_items(
        self, project_id: UUID, dataset_id: UUID, limit: int = 100, offset: int = 0
    ) -> tuple[list[DatasetItem], int]:
        await self.get_dataset(project_id, dataset_id)
        total = int(
            (
                await self.db.execute(
                    select(func.count(DatasetItem.id)).where(DatasetItem.dataset_id == dataset_id)
                )
            ).scalar_one()
        )
        result = await self.db.execute(
            select(DatasetItem)
            .where(DatasetItem.dataset_id == dataset_id)
            .order_by(DatasetItem.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    # -------------------------------------------------------------- evaluators

    async def create_evaluator(self, project_id: UUID, data: EvaluatorCreate) -> Evaluator:
        try:
            config = validate_evaluator(data.evaluator_type, data.config)
        except EvaluatorConfigError as exc:
            raise OrganizationError(str(exc), status_code=400) from exc

        spec = EVALUATOR_SPECS[data.evaluator_type]
        evaluator = Evaluator(
            project_id=project_id,
            name=data.name.strip(),
            evaluator_type=data.evaluator_type,
            description=data.description,
            config=config,
            threshold=data.threshold if data.threshold is not None else spec.default_threshold,
            is_active=data.is_active,
        )
        self.db.add(evaluator)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise OrganizationError("An evaluator with that name already exists", status_code=400) from exc
        await self.db.refresh(evaluator)
        return evaluator

    async def list_evaluators(self, project_id: UUID, active_only: bool = False) -> list[Evaluator]:
        filters = [Evaluator.project_id == project_id]
        if active_only:
            filters.append(Evaluator.is_active.is_(True))
        result = await self.db.execute(
            select(Evaluator).where(*filters).order_by(Evaluator.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_evaluator(self, project_id: UUID, evaluator_id: UUID) -> Evaluator:
        result = await self.db.execute(
            select(Evaluator).where(Evaluator.id == evaluator_id, Evaluator.project_id == project_id)
        )
        evaluator = result.scalar_one_or_none()
        if not evaluator:
            raise OrganizationError("Evaluator not found", status_code=404)
        return evaluator

    async def update_evaluator(
        self, project_id: UUID, evaluator_id: UUID, data: EvaluatorUpdate
    ) -> Evaluator:
        evaluator = await self.get_evaluator(project_id, evaluator_id)
        if data.name is not None:
            evaluator.name = data.name.strip()
        if data.description is not None:
            evaluator.description = data.description
        if data.config is not None:
            try:
                evaluator.config = validate_evaluator(evaluator.evaluator_type, data.config)
            except EvaluatorConfigError as exc:
                raise OrganizationError(str(exc), status_code=400) from exc
        if data.threshold is not None:
            evaluator.threshold = data.threshold
        if data.is_active is not None:
            evaluator.is_active = data.is_active
        await self.db.flush()
        await self.db.refresh(evaluator)
        return evaluator

    async def delete_evaluator(self, project_id: UUID, evaluator_id: UUID) -> None:
        evaluator = await self.get_evaluator(project_id, evaluator_id)
        await self.db.delete(evaluator)
        await self.db.flush()

    # --------------------------------------------------------- prompt versions

    async def create_prompt_version(self, project_id: UUID, data: PromptVersionCreate) -> PromptVersion:
        if data.is_active:
            existing = await self.db.execute(
                select(PromptVersion).where(
                    PromptVersion.project_id == project_id, PromptVersion.name == data.name.strip()
                )
            )
            for row in existing.scalars().all():
                row.is_active = False

        version = PromptVersion(
            project_id=project_id,
            name=data.name.strip(),
            version=data.version.strip(),
            template=data.template,
            notes=data.notes,
            is_active=data.is_active,
            extra_metadata=data.metadata,
        )
        self.db.add(version)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise OrganizationError("That prompt version already exists", status_code=400) from exc
        await self.db.refresh(version)
        return version

    async def list_prompt_versions(self, project_id: UUID, name: str | None = None) -> list[PromptVersion]:
        filters = [PromptVersion.project_id == project_id]
        if name:
            filters.append(PromptVersion.name == name)
        result = await self.db.execute(
            select(PromptVersion).where(*filters).order_by(PromptVersion.created_at.desc())
        )
        return list(result.scalars().all())

    # --------------------------------------------------------------- run setup

    async def _resolve_evaluators(
        self,
        project_id: UUID,
        evaluator_ids: list[UUID] | None,
        evaluator_names: list[str] | None = None,
    ) -> list[Evaluator]:
        selected_ids = list(evaluator_ids or [])

        if evaluator_names:
            wanted = list(dict.fromkeys(evaluator_names))
            by_name = await self.db.execute(
                select(Evaluator).where(
                    Evaluator.project_id == project_id, Evaluator.name.in_(wanted)
                )
            )
            found = list(by_name.scalars().all())
            missing = sorted(set(wanted) - {evaluator.name for evaluator in found})
            if missing:
                raise OrganizationError(
                    f"Evaluator not found: {', '.join(missing)}", status_code=404
                )
            selected_ids.extend(evaluator.id for evaluator in found)

        if selected_ids:
            unique_ids = list(dict.fromkeys(selected_ids))
            result = await self.db.execute(
                select(Evaluator).where(
                    Evaluator.project_id == project_id, Evaluator.id.in_(unique_ids)
                )
            )
            found = list(result.scalars().all())
            if len(found) != len(unique_ids):
                raise OrganizationError("Evaluator not found", status_code=404)
            return found

        evaluators = await self.list_evaluators(project_id, active_only=True)
        if not evaluators:
            raise OrganizationError(
                "No active evaluators for this project. Create one before running an evaluation.",
                status_code=400,
            )
        return evaluators

    async def _dataset_subjects(
        self, project_id: UUID, data: EvaluationRunCreate
    ) -> tuple[Dataset, list[tuple[EvalSubject, DatasetItem | None]]]:
        if data.dataset_id:
            dataset = await self.get_dataset(project_id, data.dataset_id)
        elif data.dataset_name:
            dataset = await self.get_dataset_by_name(project_id, data.dataset_name)
        else:
            raise OrganizationError(
                "dataset_id or dataset_name is required for dataset runs", status_code=400
            )
        if not data.outputs:
            raise OrganizationError(
                "Dataset runs need agent outputs. Run the agent with the SDK helper "
                "AgentLens.evaluate() and submit its outputs, or use target='traces'.",
                status_code=400,
            )

        items, _ = await self.list_items(project_id, dataset.id, limit=settings.max_evaluation_items)
        by_id = {item.id: item for item in items}
        by_name = {item.name: item for item in items if item.name}

        subjects: list[tuple[EvalSubject, DatasetItem | None]] = []
        for index, submitted in enumerate(data.outputs[: settings.max_evaluation_items]):
            item: DatasetItem | None = None
            if submitted.dataset_item_id:
                item = by_id.get(submitted.dataset_item_id)
                if item is None:
                    raise OrganizationError(
                        f"Dataset item {submitted.dataset_item_id} is not part of this dataset",
                        status_code=400,
                    )
            elif submitted.item_name:
                item = by_name.get(submitted.item_name)

            subject = EvalSubject(
                key=str(item.id) if item else f"output-{index}",
                input=item.input if item else None,
                output=submitted.output,
                expected_output=item.expected_output if item else None,
                status=submitted.status,
                duration_ms=submitted.duration_ms,
                cost=Decimal(str(submitted.cost)) if submitted.cost is not None else Decimal("0"),
                total_tokens=submitted.total_tokens,
                error_message=submitted.error_message,
                metadata={
                    "subject_name": (item.name if item else None) or submitted.item_name or f"output-{index}",
                    **(submitted.metadata or {}),
                },
            )
            subjects.append((subject, item))
        return dataset, subjects

    async def _trace_subjects(
        self, project_id: UUID, selector: TraceSelector | None
    ) -> list[tuple[EvalSubject, Trace]]:
        selector = selector or TraceSelector()
        filters = [Trace.project_id == project_id]
        if selector.agent_name:
            filters.append(Trace.agent_name == selector.agent_name)
        if selector.status:
            filters.append(Trace.status == selector.status)
        if selector.agent_version:
            filters.append(Trace.agent_version == selector.agent_version)
        if selector.prompt_version:
            filters.append(Trace.prompt_version == selector.prompt_version)
        if selector.model_version:
            filters.append(Trace.model_version == selector.model_version)
        if selector.session_id:
            filters.append(Trace.session_id == selector.session_id)
        if selector.since:
            filters.append(Trace.start_time >= selector.since)
        if selector.until:
            filters.append(Trace.start_time < selector.until)

        result = await self.db.execute(
            select(Trace)
            .where(*filters)
            .order_by(Trace.start_time.desc())
            .limit(min(selector.limit, settings.max_evaluation_items))
        )
        traces = list(result.scalars().all())
        subjects: list[tuple[EvalSubject, Trace]] = []
        for trace in traces:
            subjects.append(
                (
                    EvalSubject(
                        key=str(trace.id),
                        input=trace.input,
                        output=trace.output,
                        expected_output=None,
                        status=trace.status,
                        duration_ms=trace.duration_ms,
                        cost=trace.total_cost or Decimal("0"),
                        total_tokens=trace.total_tokens,
                        error_message=trace.error_message,
                        metadata={"subject_name": trace.name},
                    ),
                    trace,
                )
            )
        return subjects

    async def create_and_execute_run(self, project_id: UUID, data: EvaluationRunCreate) -> EvaluationRun:
        evaluators = await self._resolve_evaluators(
            project_id, data.evaluator_ids, data.evaluator_names
        )

        dataset: Dataset | None = None
        pairs: list[tuple[EvalSubject, DatasetItem | None, Trace | None]] = []

        if data.target == "dataset":
            dataset, dataset_pairs = await self._dataset_subjects(project_id, data)
            pairs = [(subject, item, None) for subject, item in dataset_pairs]
        else:
            if data.dataset_id:
                dataset = await self.get_dataset(project_id, data.dataset_id)
            elif data.dataset_name:
                dataset = await self.get_dataset_by_name(project_id, data.dataset_name)
            trace_pairs = await self._trace_subjects(project_id, data.selector)
            pairs = [(subject, None, trace) for subject, trace in trace_pairs]

        if not pairs:
            raise OrganizationError("Nothing to evaluate: no traces or outputs matched", status_code=400)

        run = EvaluationRun(
            project_id=project_id,
            dataset_id=dataset.id if dataset else None,
            name=data.name.strip(),
            target=data.target,
            status="running",
            agent_version=data.agent_version,
            prompt_version=data.prompt_version,
            model_version=data.model_version,
            extra_metadata=data.metadata,
            started_at=_now(),
        )
        self.db.add(run)
        await self.db.flush()

        needs_judge = any(evaluator.evaluator_type == "llm_judge" for evaluator in evaluators)
        client: httpx.AsyncClient | None = None
        if needs_judge and settings.openai_api_key:
            client = httpx.AsyncClient(timeout=settings.judge_timeout_seconds)

        skipped: set[str] = set()
        all_scores: list[float] = []
        passed_subjects = 0
        evaluated_subjects = 0
        total_cost = Decimal("0")

        try:
            for subject, item, trace in pairs:
                subject_results = 0
                subject_passed = True
                for evaluator in evaluators:
                    if subject.expected_output is None and needs_expected_output(
                        evaluator.evaluator_type, evaluator.config
                    ):
                        skipped.add(evaluator.name)
                        continue

                    outcome = await run_evaluator(
                        evaluator.evaluator_type,
                        evaluator.config or {},
                        evaluator.threshold,
                        subject,
                        http_client=client,
                    )
                    self.db.add(
                        EvaluationResult(
                            run_id=run.id,
                            project_id=project_id,
                            evaluator_id=evaluator.id,
                            evaluator_name=evaluator.name,
                            evaluator_type=evaluator.evaluator_type,
                            dataset_item_id=item.id if item else None,
                            trace_id=trace.id if trace else None,
                            subject_key=subject.key,
                            score=outcome.score,
                            passed=outcome.passed,
                            label=outcome.label,
                            reasoning=outcome.reasoning,
                            output=subject.output,
                            expected_output=subject.expected_output,
                            latency_ms=subject.duration_ms,
                            cost=subject.cost or Decimal("0"),
                            extra_metadata=subject.metadata or None,
                        )
                    )
                    all_scores.append(outcome.score)
                    subject_results += 1
                    if not outcome.passed:
                        subject_passed = False

                if subject_results:
                    evaluated_subjects += 1
                    total_cost += subject.cost or Decimal("0")
                    if subject_passed:
                        passed_subjects += 1
        except Exception as exc:
            run.status = "failed"
            run.error_message = f"{type(exc).__name__}: {exc}"
            run.completed_at = _now()
            await self.db.flush()
            raise
        finally:
            if client is not None:
                await client.aclose()

        if not evaluated_subjects:
            run.status = "failed"
            run.error_message = (
                "Every evaluator needs an expected output but no dataset references were available."
            )
            run.completed_at = _now()
            await self.db.flush()
            await self.db.refresh(run)
            return run

        run.total_items = evaluated_subjects
        run.passed_count = passed_subjects
        run.failed_count = evaluated_subjects - passed_subjects
        run.avg_score = fmean(all_scores) if all_scores else None
        run.total_cost = total_cost
        run.status = "completed"
        run.completed_at = _now()
        if skipped:
            run.extra_metadata = {**(run.extra_metadata or {}), "skipped_evaluators": sorted(skipped)}
        await self.db.flush()
        await self.db.refresh(run)
        return run

    # ------------------------------------------------------------- run reading

    async def list_runs(
        self,
        project_id: UUID,
        limit: int = 50,
        offset: int = 0,
        dataset_id: UUID | None = None,
    ) -> tuple[list[tuple[EvaluationRun, str | None]], int]:
        filters = [EvaluationRun.project_id == project_id]
        if dataset_id:
            filters.append(EvaluationRun.dataset_id == dataset_id)
        total = int(
            (
                await self.db.execute(select(func.count(EvaluationRun.id)).where(*filters))
            ).scalar_one()
        )
        result = await self.db.execute(
            select(EvaluationRun, Dataset.name)
            .join(Dataset, Dataset.id == EvaluationRun.dataset_id, isouter=True)
            .where(*filters)
            .order_by(EvaluationRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return [(run, name) for run, name in result.all()], total

    async def get_run(self, project_id: UUID, run_id: UUID) -> tuple[EvaluationRun, str | None]:
        result = await self.db.execute(
            select(EvaluationRun, Dataset.name)
            .join(Dataset, Dataset.id == EvaluationRun.dataset_id, isouter=True)
            .where(EvaluationRun.id == run_id, EvaluationRun.project_id == project_id)
        )
        row = result.one_or_none()
        if not row:
            raise OrganizationError("Evaluation run not found", status_code=404)
        return row[0], row[1]

    async def list_results(
        self,
        project_id: UUID,
        run_id: UUID,
        limit: int = 200,
        offset: int = 0,
        only_failures: bool = False,
    ) -> tuple[list[EvaluationResult], int]:
        await self.get_run(project_id, run_id)
        filters = [EvaluationResult.run_id == run_id, EvaluationResult.project_id == project_id]
        if only_failures:
            filters.append(EvaluationResult.passed.is_(False))
        total = int(
            (
                await self.db.execute(select(func.count(EvaluationResult.id)).where(*filters))
            ).scalar_one()
        )
        result = await self.db.execute(
            select(EvaluationResult)
            .where(*filters)
            .order_by(EvaluationResult.passed.asc(), EvaluationResult.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def evaluator_scores(self, run_id: UUID) -> list[EvaluatorScore]:
        rows = await self.db.execute(
            select(
                EvaluationResult.evaluator_id,
                EvaluationResult.evaluator_name,
                EvaluationResult.evaluator_type,
                func.count(EvaluationResult.id),
                func.coalesce(func.sum(case((EvaluationResult.passed.is_(True), 1), else_=0)), 0),
                func.avg(EvaluationResult.score),
            )
            .where(EvaluationResult.run_id == run_id)
            .group_by(
                EvaluationResult.evaluator_id,
                EvaluationResult.evaluator_name,
                EvaluationResult.evaluator_type,
            )
            .order_by(EvaluationResult.evaluator_name)
        )
        scores: list[EvaluatorScore] = []
        for evaluator_id, name, etype, count, passed, avg in rows.all():
            total = int(count or 0)
            passed_count = int(passed or 0)
            scores.append(
                EvaluatorScore(
                    evaluator_id=evaluator_id,
                    evaluator_name=name,
                    evaluator_type=etype,
                    count=total,
                    passed=passed_count,
                    failed=total - passed_count,
                    pass_rate=_pass_rate(passed_count, total),
                    avg_score=float(avg or 0.0),
                )
            )
        return scores

    async def failure_categories(self, run_id: UUID) -> list[FailureCategory]:
        rows = await self.db.execute(
            select(EvaluationResult.label, func.count(EvaluationResult.id))
            .where(EvaluationResult.run_id == run_id, EvaluationResult.passed.is_(False))
            .group_by(EvaluationResult.label)
            .order_by(func.count(EvaluationResult.id).desc())
        )
        return [
            FailureCategory(label=label or "unlabelled", count=int(count or 0))
            for label, count in rows.all()
        ]

    async def get_run_detail(
        self, project_id: UUID, run_id: UUID, result_limit: int = 200
    ) -> EvaluationRunDetail:
        run, dataset_name = await self.get_run(project_id, run_id)
        results, _ = await self.list_results(project_id, run_id, limit=result_limit)
        base = run_to_response(run, dataset_name)
        metadata = run.extra_metadata if isinstance(run.extra_metadata, dict) else {}
        skipped = metadata.get("skipped_evaluators") or []
        return EvaluationRunDetail(
            **base.model_dump(),
            evaluator_scores=await self.evaluator_scores(run_id),
            failure_categories=await self.failure_categories(run_id),
            skipped_evaluators=[str(name) for name in skipped],
            results=[result_to_response(item) for item in results],
        )

    # ------------------------------------------------------------- comparisons

    async def compare_runs(
        self,
        project_id: UUID,
        baseline_id: UUID,
        candidate_id: UUID,
        *,
        max_pass_rate_drop: float = 0.05,
        max_score_drop: float = 0.05,
    ) -> RunComparison:
        baseline, baseline_dataset = await self.get_run(project_id, baseline_id)
        candidate, candidate_dataset = await self.get_run(project_id, candidate_id)

        baseline_results, _ = await self.list_results(
            project_id, baseline_id, limit=settings.max_evaluation_items * 4
        )
        candidate_results, _ = await self.list_results(
            project_id, candidate_id, limit=settings.max_evaluation_items * 4
        )

        baseline_pass_rate = _pass_rate(baseline.passed_count, baseline.total_items)
        candidate_pass_rate = _pass_rate(candidate.passed_count, candidate.total_items)

        metrics = [
            metric_delta("pass_rate", baseline_pass_rate, candidate_pass_rate, True, max_pass_rate_drop),
            metric_delta("avg_score", baseline.avg_score, candidate.avg_score, True, max_score_drop),
            metric_delta(
                "avg_latency_ms",
                _mean_or_none([r.latency_ms for r in baseline_results if r.latency_ms is not None]),
                _mean_or_none([r.latency_ms for r in candidate_results if r.latency_ms is not None]),
                False,
                0.25,
                relative=True,
            ),
            metric_delta(
                "total_cost",
                float(baseline.total_cost or 0),
                float(candidate.total_cost or 0),
                False,
                0.25,
                relative=True,
            ),
        ]

        baseline_by_evaluator = _group_by_evaluator(baseline_results)
        candidate_by_evaluator = _group_by_evaluator(candidate_results)
        evaluator_deltas: list[EvaluatorDelta] = []
        for name in sorted(set(baseline_by_evaluator) | set(candidate_by_evaluator)):
            before = baseline_by_evaluator.get(name)
            after = candidate_by_evaluator.get(name)
            before_rate = before.pass_rate if before else None
            after_rate = after.pass_rate if after else None
            delta = (
                (after_rate - before_rate) if before_rate is not None and after_rate is not None else None
            )
            evaluator_deltas.append(
                EvaluatorDelta(
                    evaluator_name=name,
                    evaluator_type=(after or before).evaluator_type,
                    baseline_pass_rate=before_rate,
                    candidate_pass_rate=after_rate,
                    baseline_avg_score=before.avg_score if before else None,
                    candidate_avg_score=after.avg_score if after else None,
                    pass_rate_delta=delta,
                    regression=bool(delta is not None and delta < -max_pass_rate_drop),
                )
            )

        baseline_map = {(r.subject_key, r.evaluator_name): r for r in baseline_results}
        candidate_map = {(r.subject_key, r.evaluator_name): r for r in candidate_results}

        newly_failing: list[SubjectChange] = []
        newly_passing: list[SubjectChange] = []
        for key, after in candidate_map.items():
            before = baseline_map.get(key)
            if before is None:
                continue
            if before.passed and not after.passed:
                newly_failing.append(_subject_change(after, before))
            elif not before.passed and after.passed:
                newly_passing.append(_subject_change(after, before))

        pass_rate_drop = baseline_pass_rate - candidate_pass_rate
        if pass_rate_drop > max_pass_rate_drop or any(m.regression for m in metrics if m.metric == "pass_rate"):
            verdict = "fail"
            summary = (
                f"Pass rate dropped {pass_rate_drop * 100:.1f} points "
                f"({baseline_pass_rate * 100:.1f}% to {candidate_pass_rate * 100:.1f}%)."
            )
        elif newly_failing or any(m.regression for m in metrics):
            verdict = "warn"
            reasons = []
            if newly_failing:
                reasons.append(f"{len(newly_failing)} checks regressed")
            slow_or_costly = [m.metric for m in metrics if m.regression]
            if slow_or_costly:
                reasons.append(f"{', '.join(slow_or_costly)} got worse")
            summary = "Overall pass rate held, but " + " and ".join(reasons) + "."
        else:
            verdict = "pass"
            summary = (
                f"No regressions detected. Pass rate {candidate_pass_rate * 100:.1f}% "
                f"versus {baseline_pass_rate * 100:.1f}% on the baseline."
            )

        return RunComparison(
            baseline=run_to_response(baseline, baseline_dataset),
            candidate=run_to_response(candidate, candidate_dataset),
            metrics=metrics,
            evaluator_deltas=evaluator_deltas,
            newly_failing=sorted(newly_failing, key=lambda item: item.subject_key)[:100],
            newly_passing=sorted(newly_passing, key=lambda item: item.subject_key)[:100],
            verdict=verdict,
            summary=summary,
        )


def _mean_or_none(values: list[int] | list[float]) -> float | None:
    return fmean(values) if values else None


def _group_by_evaluator(results: list[EvaluationResult]) -> dict[str, EvaluatorScore]:
    buckets: dict[str, list[EvaluationResult]] = {}
    for result in results:
        buckets.setdefault(result.evaluator_name, []).append(result)
    grouped: dict[str, EvaluatorScore] = {}
    for name, rows in buckets.items():
        passed = sum(1 for row in rows if row.passed)
        grouped[name] = EvaluatorScore(
            evaluator_id=rows[0].evaluator_id,
            evaluator_name=name,
            evaluator_type=rows[0].evaluator_type,
            count=len(rows),
            passed=passed,
            failed=len(rows) - passed,
            pass_rate=_pass_rate(passed, len(rows)),
            avg_score=fmean(row.score for row in rows),
        )
    return grouped


def _subject_change(after: EvaluationResult, before: EvaluationResult) -> SubjectChange:
    metadata = after.extra_metadata if isinstance(after.extra_metadata, dict) else {}
    return SubjectChange(
        subject_key=after.subject_key,
        subject_name=metadata.get("subject_name"),
        evaluator_name=after.evaluator_name,
        baseline_score=before.score,
        candidate_score=after.score,
        label=after.label,
        reasoning=after.reasoning,
        dataset_item_id=after.dataset_item_id,
        trace_id=after.trace_id,
    )

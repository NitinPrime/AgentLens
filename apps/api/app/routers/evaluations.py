from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.evaluators import EVALUATOR_SPECS
from app.database import get_db
from app.dependencies import get_api_key, get_current_user
from app.models.evaluation import Dataset, EvaluationRun, Evaluator
from app.models.project import ApiKey
from app.models.user import User
from app.schemas.evaluations import (
    DatasetCreate,
    DatasetItemBulkCreate,
    DatasetItemResponse,
    DatasetResponse,
    DatasetUpdate,
    EvaluationResultListResponse,
    EvaluationRunCreate,
    EvaluationRunDetail,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    EvaluatorCreate,
    EvaluatorResponse,
    EvaluatorTypeInfo,
    EvaluatorUpdate,
    PromptVersionCreate,
    PromptVersionResponse,
    RunComparison,
)
from app.services.evaluations import (
    EvaluationService,
    dataset_to_response,
    evaluator_to_response,
    item_to_response,
    prompt_version_to_response,
    result_to_response,
    run_to_response,
)
from app.services.organizations import OrganizationError
from app.services.projects import ProjectService

router = APIRouter(tags=["evaluations"])
sdk_router = APIRouter(prefix="/sdk", tags=["sdk"])


def _http(exc: OrganizationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


async def _require_project(db: AsyncSession, project_id: UUID, user: User) -> UUID:
    await ProjectService(db).get_project_for_user(project_id, user.id)
    return project_id


async def _project_of(db: AsyncSession, model, entity_id: UUID, missing: str) -> UUID:
    result = await db.execute(select(model.project_id).where(model.id == entity_id))
    project_id = result.scalar_one_or_none()
    if not project_id:
        raise OrganizationError(missing, status_code=404)
    return project_id


@router.get("/evaluator-types", response_model=list[EvaluatorTypeInfo])
async def list_evaluator_types(
    current_user: User = Depends(get_current_user),
) -> list[EvaluatorTypeInfo]:
    return [
        EvaluatorTypeInfo(
            type=spec.type,
            title=spec.title,
            description=spec.description,
            requires_expected_output=spec.requires_expected_output,
            default_threshold=spec.default_threshold,
            default_config=spec.default_config,
        )
        for spec in EVALUATOR_SPECS.values()
    ]


# ------------------------------------------------------------------- datasets


@router.get("/projects/{project_id}/datasets", response_model=list[DatasetResponse])
async def list_datasets(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetResponse]:
    try:
        await _require_project(db, project_id, current_user)
        pairs = await EvaluationService(db).list_datasets(project_id)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return [dataset_to_response(dataset, count) for dataset, count in pairs]


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset(
    project_id: UUID,
    data: DatasetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetResponse:
    try:
        await _require_project(db, project_id, current_user)
        dataset = await EvaluationService(db).create_dataset(project_id, data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return dataset_to_response(dataset, 0)


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetResponse:
    try:
        project_id = await _project_of(db, Dataset, dataset_id, "Dataset not found")
        await _require_project(db, project_id, current_user)
        service = EvaluationService(db)
        dataset = await service.get_dataset(project_id, dataset_id)
        count = await service.count_items(dataset_id)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return dataset_to_response(dataset, count)


@router.patch("/datasets/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: UUID,
    data: DatasetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetResponse:
    try:
        project_id = await _project_of(db, Dataset, dataset_id, "Dataset not found")
        await _require_project(db, project_id, current_user)
        service = EvaluationService(db)
        dataset = await service.update_dataset(project_id, dataset_id, data)
        count = await service.count_items(dataset_id)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return dataset_to_response(dataset, count)


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        project_id = await _project_of(db, Dataset, dataset_id, "Dataset not found")
        await _require_project(db, project_id, current_user)
        await EvaluationService(db).delete_dataset(project_id, dataset_id)
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.get("/datasets/{dataset_id}/items", response_model=list[DatasetItemResponse])
async def list_dataset_items(
    dataset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[DatasetItemResponse]:
    try:
        project_id = await _project_of(db, Dataset, dataset_id, "Dataset not found")
        await _require_project(db, project_id, current_user)
        items, _ = await EvaluationService(db).list_items(
            project_id, dataset_id, limit=limit, offset=offset
        )
    except OrganizationError as exc:
        raise _http(exc) from exc
    return [item_to_response(item) for item in items]


@router.post(
    "/datasets/{dataset_id}/items",
    response_model=list[DatasetItemResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_dataset_items(
    dataset_id: UUID,
    data: DatasetItemBulkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetItemResponse]:
    try:
        project_id = await _project_of(db, Dataset, dataset_id, "Dataset not found")
        await _require_project(db, project_id, current_user)
        items = await EvaluationService(db).add_items(project_id, dataset_id, data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return [item_to_response(item) for item in items]


# ----------------------------------------------------------------- evaluators


@router.get("/projects/{project_id}/evaluators", response_model=list[EvaluatorResponse])
async def list_evaluators(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    active_only: bool = False,
) -> list[EvaluatorResponse]:
    try:
        await _require_project(db, project_id, current_user)
        evaluators = await EvaluationService(db).list_evaluators(project_id, active_only=active_only)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return [evaluator_to_response(evaluator) for evaluator in evaluators]


@router.post(
    "/projects/{project_id}/evaluators",
    response_model=EvaluatorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluator(
    project_id: UUID,
    data: EvaluatorCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvaluatorResponse:
    try:
        await _require_project(db, project_id, current_user)
        evaluator = await EvaluationService(db).create_evaluator(project_id, data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return evaluator_to_response(evaluator)


@router.patch("/evaluators/{evaluator_id}", response_model=EvaluatorResponse)
async def update_evaluator(
    evaluator_id: UUID,
    data: EvaluatorUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvaluatorResponse:
    try:
        project_id = await _project_of(db, Evaluator, evaluator_id, "Evaluator not found")
        await _require_project(db, project_id, current_user)
        evaluator = await EvaluationService(db).update_evaluator(project_id, evaluator_id, data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return evaluator_to_response(evaluator)


@router.delete("/evaluators/{evaluator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluator(
    evaluator_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        project_id = await _project_of(db, Evaluator, evaluator_id, "Evaluator not found")
        await _require_project(db, project_id, current_user)
        await EvaluationService(db).delete_evaluator(project_id, evaluator_id)
    except OrganizationError as exc:
        raise _http(exc) from exc


# ------------------------------------------------------------ evaluation runs


@router.get("/projects/{project_id}/evaluation-runs", response_model=EvaluationRunListResponse)
async def list_evaluation_runs(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    dataset_id: UUID | None = None,
) -> EvaluationRunListResponse:
    try:
        await _require_project(db, project_id, current_user)
        rows, total = await EvaluationService(db).list_runs(
            project_id, limit=limit, offset=offset, dataset_id=dataset_id
        )
    except OrganizationError as exc:
        raise _http(exc) from exc
    return EvaluationRunListResponse(
        items=[run_to_response(run, name) for run, name in rows], total=total
    )


@router.post(
    "/projects/{project_id}/evaluation-runs",
    response_model=EvaluationRunDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluation_run(
    project_id: UUID,
    data: EvaluationRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvaluationRunDetail:
    try:
        await _require_project(db, project_id, current_user)
        service = EvaluationService(db)
        run = await service.create_and_execute_run(project_id, data)
        return await service.get_run_detail(project_id, run.id)
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.get("/evaluation-runs/{run_id}", response_model=EvaluationRunDetail)
async def get_evaluation_run(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    result_limit: int = Query(default=200, ge=1, le=1000),
) -> EvaluationRunDetail:
    try:
        project_id = await _project_of(db, EvaluationRun, run_id, "Evaluation run not found")
        await _require_project(db, project_id, current_user)
        return await EvaluationService(db).get_run_detail(project_id, run_id, result_limit=result_limit)
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.get("/evaluation-runs/{run_id}/results", response_model=EvaluationResultListResponse)
async def list_evaluation_results(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    only_failures: bool = False,
) -> EvaluationResultListResponse:
    try:
        project_id = await _project_of(db, EvaluationRun, run_id, "Evaluation run not found")
        await _require_project(db, project_id, current_user)
        results, total = await EvaluationService(db).list_results(
            project_id, run_id, limit=limit, offset=offset, only_failures=only_failures
        )
    except OrganizationError as exc:
        raise _http(exc) from exc
    return EvaluationResultListResponse(
        items=[result_to_response(result) for result in results], total=total
    )


@router.get("/evaluation-runs/{run_id}/compare", response_model=RunComparison)
async def compare_evaluation_runs(
    run_id: UUID,
    baseline: UUID = Query(..., description="Run id to compare against"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    max_pass_rate_drop: float = Query(default=0.05, ge=0, le=1),
    max_score_drop: float = Query(default=0.05, ge=0, le=1),
) -> RunComparison:
    try:
        project_id = await _project_of(db, EvaluationRun, run_id, "Evaluation run not found")
        await _require_project(db, project_id, current_user)
        return await EvaluationService(db).compare_runs(
            project_id,
            baseline,
            run_id,
            max_pass_rate_drop=max_pass_rate_drop,
            max_score_drop=max_score_drop,
        )
    except OrganizationError as exc:
        raise _http(exc) from exc


# ---------------------------------------------------------- prompt versions


@router.get("/projects/{project_id}/prompt-versions", response_model=list[PromptVersionResponse])
async def list_prompt_versions(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    name: str | None = None,
) -> list[PromptVersionResponse]:
    try:
        await _require_project(db, project_id, current_user)
        versions = await EvaluationService(db).list_prompt_versions(project_id, name=name)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return [prompt_version_to_response(version) for version in versions]


@router.post(
    "/projects/{project_id}/prompt-versions",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt_version(
    project_id: UUID,
    data: PromptVersionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptVersionResponse:
    try:
        await _require_project(db, project_id, current_user)
        version = await EvaluationService(db).create_prompt_version(project_id, data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return prompt_version_to_response(version)


# ------------------------------------------------------------- SDK (API key)


@sdk_router.get("/datasets", response_model=list[DatasetResponse])
async def sdk_list_datasets(
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetResponse]:
    pairs = await EvaluationService(db).list_datasets(api_key.project_id)
    return [dataset_to_response(dataset, count) for dataset, count in pairs]


@sdk_router.get("/datasets/{name}/items", response_model=list[DatasetItemResponse])
async def sdk_list_dataset_items(
    name: str,
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[DatasetItemResponse]:
    service = EvaluationService(db)
    try:
        dataset = await service.get_dataset_by_name(api_key.project_id, name)
        items, _ = await service.list_items(
            api_key.project_id, dataset.id, limit=limit, offset=offset
        )
    except OrganizationError as exc:
        raise _http(exc) from exc
    return [item_to_response(item) for item in items]


@sdk_router.post(
    "/datasets/{name}/items",
    response_model=list[DatasetItemResponse],
    status_code=status.HTTP_201_CREATED,
)
async def sdk_upsert_dataset_items(
    name: str,
    data: DatasetItemBulkCreate,
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetItemResponse]:
    service = EvaluationService(db)
    try:
        try:
            dataset = await service.get_dataset_by_name(api_key.project_id, name)
        except OrganizationError:
            dataset = await service.create_dataset(api_key.project_id, DatasetCreate(name=name))
        items = await service.add_items(api_key.project_id, dataset.id, data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return [item_to_response(item) for item in items]


@sdk_router.post(
    "/evaluation-runs",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def sdk_create_evaluation_run(
    data: EvaluationRunCreate,
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
) -> EvaluationRunResponse:
    service = EvaluationService(db)
    try:
        run = await service.create_and_execute_run(api_key.project_id, data)
        _, dataset_name = await service.get_run(api_key.project_id, run.id)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return run_to_response(run, dataset_name)

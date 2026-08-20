from fastapi import APIRouter, Depends

from app.dependencies import get_api_key
from app.models.project import ApiKey
from app.schemas.workspace import ApiKeyVerifyResponse

router = APIRouter(prefix="/sdk", tags=["sdk"])


@router.get("/verify", response_model=ApiKeyVerifyResponse)
async def verify_sdk_key(api_key: ApiKey = Depends(get_api_key)) -> ApiKeyVerifyResponse:
    return ApiKeyVerifyResponse(
        project_id=api_key.project_id,
        organization_id=api_key.project.organization_id,
        project_name=api_key.project.name,
        key_name=api_key.name,
        key_prefix=api_key.key_prefix,
    )

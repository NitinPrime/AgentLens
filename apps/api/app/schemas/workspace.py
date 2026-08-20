from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class OrganizationMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email: EmailStr | None = None
    full_name: str | None = None
    role: str
    created_at: datetime


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None = None
    role: str | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationInvite(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern="^(owner|admin|member)$")


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    slug: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    key_prefix: str
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    is_revoked: bool
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    secret: str


class ApiKeyVerifyResponse(BaseModel):
    project_id: UUID
    organization_id: UUID
    project_name: str
    key_name: str
    key_prefix: str

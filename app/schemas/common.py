"""Shared schema components."""

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination query parameters."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class TimestampMixin(BaseModel):
    """Common timestamp fields."""

    created_at: datetime
    updated_at: datetime


class SoftDeleteMixin(BaseModel):
    """Soft delete timestamp."""

    deleted_at: datetime | None = None


class CampaignScopedMixin(BaseModel):
    """Campaign scoping field."""

    campaign_id: UUID


class IDMixin(BaseModel):
    """ID field."""

    id: UUID


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    code: str | None = None
    extra: dict[str, Any] | None = None


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response."""

    data: T
    message: str | None = None
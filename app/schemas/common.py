"""Shared schema components."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Pagination query parameters."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedResponse[T](BaseModel):
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


class EntityKeyMixin(BaseModel):
    """Reference to the entity a specialized row belongs to.

    Deliberately narrow. The specialized models already inherit
    ``TimestampMixin``, so a mixin carrying ``created_at`` as well would put a
    second, near-identical timestamp on the wire for client-side sorting to
    disagree over. See ADR-004.
    """

    entity_id: UUID


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    code: str | None = None
    extra: dict[str, Any] | None = None


class SuccessResponse[T](BaseModel):
    """Standard success response."""

    data: T
    message: str | None = None
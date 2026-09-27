"""Fact and relationship fact schemas."""

from typing import Annotated
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin


class EntityFactBase(BaseModel):
    """Base entity fact fields."""

    fact_type: Annotated[str, Field(min_length=1, max_length=100)]
    content: str
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)] = None
    importance: Annotated[int, Field(default=0, ge=0)] = 0
    status: Annotated[str, Field(default="active", pattern="^(active|invalidated|superseded)$")] = "active"
    statement_id: UUID | None = None
    event_id: UUID | None = None
    entity_id: UUID


class EntityFactCreate(EntityFactBase):
    """Create entity fact request."""

    pass


class EntityFactUpdate(BaseModel):
    """Update entity fact request."""

    fact_type: Annotated[str | None, Field(default=None, min_length=1, max_length=100)] = None
    content: str | None = None
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)] = None
    importance: Annotated[int | None, Field(default=None, ge=0)] = None
    status: Annotated[str | None, Field(default=None, pattern="^(active|invalidated|superseded)$")] = None


class EntityFactRead(EntityFactBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin):
    """Entity fact response."""

    model_config = ConfigDict(from_attributes=True)


class EntityFactList(BaseModel):
    """Paginated entity fact list."""

    items: list[EntityFactRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class EntityFactFilter(BaseModel):
    """Entity fact filter parameters."""

    entity_id: UUID | None = None
    fact_type: str | None = None
    status: str | None = None
    event_id: UUID | None = None


class EntityRelationshipFactBase(BaseModel):
    """Base entity relationship fact fields."""

    relationship_type: Annotated[str, Field(min_length=1, max_length=100)]
    content: str
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)] = None
    importance: Annotated[int, Field(default=0, ge=0)] = 0
    status: Annotated[str, Field(default="active", pattern="^(active|invalidated|superseded)$")] = "active"
    statement_id: UUID | None = None
    event_id: UUID | None = None
    source_entity_id: UUID
    target_entity_id: UUID


class EntityRelationshipFactCreate(EntityRelationshipFactBase):
    """Create relationship fact request."""

    pass


class EntityRelationshipFactUpdate(BaseModel):
    """Update relationship fact request."""

    relationship_type: Annotated[str | None, Field(default=None, min_length=1, max_length=100)] = None
    content: str | None = None
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)] = None
    importance: Annotated[int | None, Field(default=None, ge=0)] = None
    status: Annotated[str | None, Field(default=None, pattern="^(active|invalidated|superseded)$")] = None


class EntityRelationshipFactRead(EntityRelationshipFactBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin):
    """Entity relationship fact response."""

    model_config = ConfigDict(from_attributes=True)


class EntityRelationshipFactList(BaseModel):
    """Paginated relationship fact list."""

    items: list[EntityRelationshipFactRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class EntityRelationshipFactFilter(BaseModel):
    """Relationship fact filter parameters."""

    source_entity_id: UUID | None = None
    target_entity_id: UUID | None = None
    relationship_type: str | None = None
    status: str | None = None
    event_id: UUID | None = None
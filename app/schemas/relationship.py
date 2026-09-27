"""Materialized relationship schema."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin


class EntityRelationshipRead(BaseModel):
    """Materialized relationship response."""

    id: UUID
    campaign_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: str
    relationship_fact_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EntityRelationshipList(BaseModel):
    """Materialized relationship list."""

    items: list[EntityRelationshipRead]
    total: int
    page: int
    page_size: int
    total_pages: int
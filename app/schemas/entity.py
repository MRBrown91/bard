"""Entity and alias schemas."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin


class EntityBase(BaseModel):
    """Base entity fields."""

    entity_type: Annotated[str, Field(min_length=1, max_length=50)]
    name: Annotated[str, Field(min_length=1, max_length=255)]
    description: str | None = None


class EntityCreate(EntityBase):
    """Create entity request."""

    pass


class EntityUpdate(BaseModel):
    """Update entity request."""

    entity_type: Annotated[str | None, Field(default=None, min_length=1, max_length=50)] = None
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    description: str | None = None


class EntityRead(EntityBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin):
    """Entity response."""

    model_config = ConfigDict(from_attributes=True)


class EntityList(BaseModel):
    """Paginated entity list."""

    items: list[EntityRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class EntityFilter(BaseModel):
    """Entity filter parameters."""

    entity_type: str | None = None
    name_contains: str | None = None


class EntityAliasBase(BaseModel):
    """Base entity alias fields."""

    alias: Annotated[str, Field(min_length=1, max_length=255)]


class EntityAliasCreate(EntityAliasBase):
    """Create alias request."""

    pass


class EntityAliasRead(EntityAliasBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Alias response."""

    entity_id: UUID

    model_config = ConfigDict(from_attributes=True)


class EntityWithAliasesRead(EntityRead):
    """Entity with aliases loaded."""

    aliases: list[EntityAliasRead] = []
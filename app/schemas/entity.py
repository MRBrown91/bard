"""Entity and alias schemas."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import (
    CampaignScopedMixin,
    IDMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class EntityType(StrEnum):
    """The six entity types, each with exactly one specialization table.

    An NPC is an ``actor``; there is no separate ``npc`` type. The value is
    fixed at creation — see ADR-020.
    """

    ACTOR = "actor"
    PLAYER = "player"
    PLAYER_CHARACTER = "player_character"
    LOCATION = "location"
    ITEM = "item"
    FACTION = "faction"


class EntityBase(BaseModel):
    """Base entity fields."""

    entity_type: EntityType
    name: Annotated[str, Field(min_length=1, max_length=255)]
    description: str | None = None


class EntityCreate(EntityBase):
    """Create entity request."""

    aliases: list["EntityAliasCreate"] = Field(default_factory=list)


class EntityUpdate(BaseModel):
    """Update entity request.

    ``entity_type`` is accepted only so it can be rejected. A client that tries
    to change the type is told so, rather than having the field quietly
    ignored and believing the change took effect.
    """

    entity_type: EntityType | None = None
    name: Annotated[
        str | None, Field(default=None, min_length=1, max_length=255)
    ] = None
    description: str | None = None

    @field_validator("entity_type")
    @classmethod
    def _reject_type_change(cls, value: EntityType | None) -> None:
        if value is not None:
            raise ValueError(
                "entity_type is immutable and cannot be changed after creation. "
                "Delete the entity and create a new one with the correct type."
            )


class EntityRead(
    EntityBase, IDMixin, TimestampMixin, SoftDeleteMixin, CampaignScopedMixin
):
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

    entity_type: EntityType | None = None
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

    aliases: list[EntityAliasRead] = Field(default_factory=list)

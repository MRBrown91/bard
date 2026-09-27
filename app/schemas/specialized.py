"""Specialized entity type schemas."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin


class ActorBase(BaseModel):
    """Base actor fields."""

    voice_instructions: str | None = None
    personality: str | None = None
    motivation: str | None = None
    appearance: str | None = None


class ActorCreate(ActorBase):
    """Create actor request."""

    pass


class ActorUpdate(BaseModel):
    """Update actor request."""

    voice_instructions: str | None = None
    personality: str | None = None
    motivation: str | None = None
    appearance: str | None = None


class ActorRead(ActorBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Actor response."""

    model_config = ConfigDict(from_attributes=True)


class PlayerBase(BaseModel):
    """Base player fields."""

    user_id: UUID
    status: Annotated[str, Field(min_length=1, max_length=30)] = "active"


class PlayerCreate(PlayerBase):
    """Create player request."""

    pass


class PlayerUpdate(BaseModel):
    """Update player request."""

    status: Annotated[str | None, Field(default=None, min_length=1, max_length=30)] = None


class PlayerRead(PlayerBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Player response."""

    model_config = ConfigDict(from_attributes=True)


class PlayerCharacterBase(BaseModel):
    """Base player character fields."""

    player_id: UUID


class PlayerCharacterCreate(PlayerCharacterBase):
    """Create player character request."""

    pass


class PlayerCharacterRead(PlayerCharacterBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Player character response."""

    model_config = ConfigDict(from_attributes=True)


class LocationBase(BaseModel):
    """Base location fields."""

    environment: str | None = None
    atmosphere: str | None = None


class LocationCreate(LocationBase):
    """Create location request."""

    pass


class LocationUpdate(BaseModel):
    """Update location request."""

    environment: str | None = None
    atmosphere: str | None = None


class LocationRead(LocationBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Location response."""

    model_config = ConfigDict(from_attributes=True)


class ItemBase(BaseModel):
    """Base item fields."""

    physical_description: str | None = None
    effect_description: str | None = None


class ItemCreate(ItemBase):
    """Create item request."""

    pass


class ItemUpdate(BaseModel):
    """Update item request."""

    physical_description: str | None = None
    effect_description: str | None = None


class ItemRead(ItemBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Item response."""

    model_config = ConfigDict(from_attributes=True)


class FactionBase(BaseModel):
    """Base faction fields."""

    purpose: str | None = None
    description: str | None = None


class FactionCreate(FactionBase):
    """Create faction request."""

    pass


class FactionUpdate(BaseModel):
    """Update faction request."""

    purpose: str | None = None
    description: str | None = None


class FactionRead(FactionBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Faction response."""

    model_config = ConfigDict(from_attributes=True)
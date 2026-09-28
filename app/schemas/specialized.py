"""Specialized entity type schemas.

Every specialized read model is keyed on ``entity_id`` rather than ``id``,
because that is the only key these tables have, and embeds the base entity so a
list endpoint is usable in one request and client-side sorting has a single
``created_at`` to read. See ADR-004 and ADR-021.
"""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import EntityKeyMixin
from app.schemas.entity import EntityRead


class SpecializedRead(EntityKeyMixin):
    """Base specialized response: the row plus its entity.

    Deliberately carries no timestamps of its own. The entity is embedded, and
    its ``created_at`` is the canonical one for sorting; adding a second
    near-identical value from the specialization row would leave a client
    choosing between two that differ by a few milliseconds. See ADR-004.
    """

    entity: EntityRead

    model_config = ConfigDict(from_attributes=True)


class SpecializedList[T](BaseModel):
    """Paginated specialized list."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class SpecializedRequest(BaseModel):
    """Base for specialized create requests.

    Forbids unknown fields. These tables have few columns, so a client that
    guesses a field name would otherwise get a 201 and a response that looks
    like the value was saved, when in fact it was dropped on the way in.
    """

    model_config = ConfigDict(extra="forbid")


class ActorBase(BaseModel):
    """Base actor fields."""

    voice_instructions: str | None = None
    personality: str | None = None
    motivation: str | None = None
    appearance: str | None = None


class ActorCreate(SpecializedRequest, ActorBase):
    """Create actor request.

    ``entity_id`` names the entity this row attaches to. The entity itself is
    created separately through /entities, so it must already exist.
    """

    entity_id: UUID


class ActorUpdate(ActorBase):
    """Update actor request."""

    pass


class ActorRead(ActorBase, SpecializedRead):
    """Actor response."""

    pass


class PlayerBase(BaseModel):
    """Base player fields."""

    user_id: UUID
    status: Annotated[str, Field(min_length=1, max_length=30)] = "active"


class PlayerCreate(SpecializedRequest, PlayerBase):
    """Create player request. ``entity_id`` must already exist."""

    entity_id: UUID


class PlayerUpdate(BaseModel):
    """Update player request.

    ``user_id`` is not a field here at all. Omitting it is what makes the link
    immutable, and ``extra="forbid"`` turns an attempt to change it into a 422
    naming the offending field, instead of silently dropping it and reporting
    success.
    """

    model_config = ConfigDict(extra="forbid")

    status: Annotated[
        str | None, Field(default=None, min_length=1, max_length=30)
    ] = None


class PlayerRead(PlayerBase, SpecializedRead):
    """Player response."""

    pass


class PlayerCharacterBase(BaseModel):
    """Base player character fields."""

    player_id: UUID


class PlayerCharacterCreate(SpecializedRequest, PlayerCharacterBase):
    """Create player character request. ``entity_id`` must already exist."""

    entity_id: UUID


class PlayerCharacterUpdate(BaseModel):
    """Update player character request.

    The row has no updatable columns beyond its fixed ``player_id``, so there
    is nothing to patch. The link is kept immutable by not being a field, and
    ``extra="forbid"`` rejects any attempt to change it rather than ignoring
    it.
    """

    model_config = ConfigDict(extra="forbid")


class PlayerCharacterRead(PlayerCharacterBase, SpecializedRead):
    """Player character response."""

    pass


class LocationBase(BaseModel):
    """Base location fields."""

    environment: str | None = None
    atmosphere: str | None = None


class LocationCreate(SpecializedRequest, LocationBase):
    """Create location request. ``entity_id`` must already exist."""

    entity_id: UUID


class LocationUpdate(LocationBase):
    """Update location request."""

    pass


class LocationRead(LocationBase, SpecializedRead):
    """Location response."""

    pass


class ItemBase(BaseModel):
    """Base item fields."""

    physical_description: str | None = None
    effect_description: str | None = None


class ItemCreate(SpecializedRequest, ItemBase):
    """Create item request. ``entity_id`` must already exist."""

    entity_id: UUID


class ItemUpdate(ItemBase):
    """Update item request."""

    pass


class ItemRead(ItemBase, SpecializedRead):
    """Item response."""

    pass


class FactionBase(BaseModel):
    """Base faction fields."""

    purpose: str | None = None
    description: str | None = None


class FactionCreate(SpecializedRequest, FactionBase):
    """Create faction request. ``entity_id`` must already exist."""

    entity_id: UUID


class FactionUpdate(FactionBase):
    """Update faction request."""

    pass


class FactionRead(FactionBase, SpecializedRead):
    """Faction response."""

    pass

"""Fact schemas.

``entity_id`` is owned by the path, not the body, so it is absent from the
create and update schemas. ``extra="forbid"`` means a body carrying
``campaign_id`` or ``entity_id`` is rejected with a 422 rather than silently
ignored, which is the same rule documents use.

``status`` accepts any of the three values from any other. The vocabulary is
still moving, and P1D.5 keys materialization off the value rather than off the
transition, so a state machine here would only be a guess that P1D.5 inherits.

``deleted_at`` is not exposed. Every read filters soft-deleted rows out, so
returning the column would advertise a state no read can produce.
"""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.audience import FactAudienceRead
from app.schemas.common import CampaignScopedMixin, IDMixin, TimestampMixin

FACT_STATUSES = ("active", "invalidated", "superseded")

StatusField = Annotated[
    str, Field(pattern="^(active|invalidated|superseded)$")
]
OptionalStatusField = Annotated[
    str | None, Field(default=None, pattern="^(active|invalidated|superseded)$")
]


class EntityFactBase(BaseModel):
    """Fields a caller may set on a fact."""

    model_config = ConfigDict(extra="forbid")

    fact_type: Annotated[str, Field(min_length=1, max_length=100)]
    content: str
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)] = None
    importance: Annotated[int, Field(default=0, ge=0)] = 0
    status: StatusField = "active"


class EntityFactCreate(EntityFactBase):
    """Create entity fact request.

    The entity comes from the path and the campaign from the authorized scope.
    """

    statement_id: UUID | None = None
    event_id: UUID | None = None


class EntityFactUpdate(BaseModel):
    """Update entity fact request.

    Only fields the caller actually sends are changed; an absent field is left
    alone rather than blanked. ``fact_type`` is immutable because a fact is
    classified when it is extracted, and reclassifying it in place would
    silently move it between extraction categories. ``statement_id`` and
    ``event_id`` are provenance and cannot be repointed after the fact exists.
    """

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)] = None
    importance: Annotated[int | None, Field(default=None, ge=0)] = None
    status: OptionalStatusField = None


class EntityFactRead(EntityFactBase, IDMixin, TimestampMixin, CampaignScopedMixin):
    """Entity fact response."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    statement_id: UUID | None = None
    event_id: UUID | None = None


class EntityFactWithAudiencesRead(EntityFactRead):
    """Entity fact response including its audience rules."""

    audiences: list[FactAudienceRead] = Field(default_factory=list)


class EntityFactList(BaseModel):
    """Paginated entity fact list."""

    items: list[EntityFactRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class EntityFactFilter(BaseModel):
    """Entity fact filter parameters."""

    fact_type: str | None = None
    status: str | None = None
    event_id: UUID | None = None


class EntityRelationshipFactBase(BaseModel):
    """Fields a caller may set on a relationship fact."""

    model_config = ConfigDict(extra="forbid")

    relationship_type: Annotated[str, Field(min_length=1, max_length=100)]
    content: str
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)] = None
    importance: Annotated[int, Field(default=0, ge=0)] = 0
    status: StatusField = "active"


class EntityRelationshipFactCreate(EntityRelationshipFactBase):
    """Create relationship fact request."""

    statement_id: UUID | None = None
    event_id: UUID | None = None
    source_entity_id: UUID
    target_entity_id: UUID


class EntityRelationshipFactUpdate(BaseModel):
    """Update relationship fact request."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    confidence: Annotated[float | None, Field(default=None, ge=0.0, le=1.0)] = None
    importance: Annotated[int | None, Field(default=None, ge=0)] = None
    status: OptionalStatusField = None


class EntityRelationshipFactRead(
    EntityRelationshipFactBase, IDMixin, TimestampMixin, CampaignScopedMixin
):
    """Entity relationship fact response."""

    model_config = ConfigDict(from_attributes=True)

    statement_id: UUID | None = None
    event_id: UUID | None = None
    source_entity_id: UUID
    target_entity_id: UUID


class EntityRelationshipFactList(BaseModel):
    """Paginated relationship fact list."""

    items: list[EntityRelationshipFactRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class EntityRelationshipFactFilter(BaseModel):
    """Relationship fact filter parameters."""

    relationship_type: str | None = None
    status: str | None = None
    event_id: UUID | None = None

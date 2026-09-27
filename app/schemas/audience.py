"""Audience/visibility schemas."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import IDMixin, TimestampMixin, SoftDeleteMixin


class FactAudienceBase(BaseModel):
    """Base fact audience fields."""

    audience_type: Annotated[str, Field(default="general", pattern="^(general|player|dm)$")] = "general"
    player_id: UUID | None = None
    fact_id: UUID


class FactAudienceCreate(FactAudienceBase):
    """Create fact audience request."""

    pass


class FactAudienceRead(FactAudienceBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Fact audience response."""

    model_config = ConfigDict(from_attributes=True)


class RelationshipFactAudienceBase(BaseModel):
    """Base relationship fact audience fields."""

    audience_type: Annotated[str, Field(default="general", pattern="^(general|player|dm)$")] = "general"
    player_id: UUID | None = None
    fact_id: UUID


class RelationshipFactAudienceCreate(RelationshipFactAudienceBase):
    """Create relationship fact audience request."""

    pass


class RelationshipFactAudienceRead(RelationshipFactAudienceBase, IDMixin, TimestampMixin, SoftDeleteMixin):
    """Relationship fact audience response."""

    model_config = ConfigDict(from_attributes=True)
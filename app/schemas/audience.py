"""Audience and visibility schemas.

An audience rule is only meaningful as a pair: ``player`` names a player, and
``general`` and ``dm`` do not. A ``player`` rule with no ``player_id`` can never
select anybody, and a ``general`` rule carrying a ``player_id`` looks like it
narrows the audience when it does not. Both are rejected rather than stored, so
the Phase 2 filter never has to decide what a nonsensical rule means.

These schemas record and return rules. They do not enforce them: no read path
applies an audience to a fact yet, which is deliberate and tracked in ADR-025.
"""

from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import IDMixin, TimestampMixin

AUDIENCE_TYPES = ("general", "player", "dm")

AudienceTypeField = Annotated[
    str, Field(pattern="^(general|player|dm)$")
]


class _AudienceBase(BaseModel):
    """Shared audience fields, with the type and player validated as a pair."""

    model_config = ConfigDict(extra="forbid")

    audience_type: AudienceTypeField = "general"
    player_id: UUID | None = None

    @model_validator(mode="after")
    def _type_and_player_agree(self) -> Self:
        """Require a player exactly when the rule is addressed to one."""
        if self.audience_type == "player" and self.player_id is None:
            raise ValueError("audience_type 'player' requires a player_id")
        if self.audience_type != "player" and self.player_id is not None:
            raise ValueError(
                f"audience_type {self.audience_type!r} must not carry a player_id; "
                "only 'player' rules name a player"
            )
        return self


class FactAudienceCreate(_AudienceBase):
    """Create an entity fact audience rule.

    The fact comes from the path, so ``fact_id`` is not settable here.
    """


class FactAudienceRead(_AudienceBase, IDMixin, TimestampMixin):
    """Entity fact audience response."""

    model_config = ConfigDict(from_attributes=True)

    fact_id: UUID


class RelationshipFactAudienceCreate(_AudienceBase):
    """Create a relationship fact audience rule."""


class RelationshipFactAudienceRead(_AudienceBase, IDMixin, TimestampMixin):
    """Relationship fact audience response."""

    model_config = ConfigDict(from_attributes=True)

    fact_id: UUID

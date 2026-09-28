"""Persistence for the six specialized entity tables.

These tables have no ``campaign_id`` and must not grow one. Every read and
write resolves the parent entity through the campaign-scoped
:class:`EntityRepository` first, so campaign isolation and the entity type
check are decided in one place. See ADR-021.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Entity
from app.models.entity.entity_types import (
    Actor,
    Faction,
    Item,
    Location,
    Player,
    PlayerCharacter,
)
from app.repositories.entity_repo import EntityRepository
from app.schemas.entity import EntityType

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase


class SpecializedRepository[T: DeclarativeBase](ABC):
    """Base repository for a one-to-one entity specialization.

    Subclasses declare the entity type, the name of the relationship on
    ``Entity`` that loads their row, and any type-specific validation.
    """

    entity_type: EntityType
    relationship_name: str

    def __init__(self, session: AsyncSession, campaign_id: UUID):
        self.session = session
        self.campaign_id = campaign_id
        self.entity_repo = EntityRepository(session, campaign_id)

    @property
    @abstractmethod
    def model(self) -> type[T]:
        """Return the SQLAlchemy model class."""
        ...

    @property
    def label(self) -> str:
        """Human-readable resource name used in error messages."""
        return self.entity_type.value

    def _not_found(self, entity_id: UUID) -> NotFoundError:
        """Build the 404 for a missing, cross-campaign, or wrong-type entity.

        All three cases collapse to the same error on purpose. Distinguishing
        "wrong campaign" from "does not exist" would let a caller probe which
        identifiers exist in campaigns they cannot see.
        """
        return NotFoundError(
            f"{self.label.capitalize()} not found",
            {f"{self.relationship_name}_id": str(entity_id)},
        )

    async def _resolve(self, entity_id: UUID) -> tuple[Entity, T]:
        """Load the parent entity and its specialization, or raise 404."""
        entity = await self.entity_repo.get_with(entity_id, self.relationship_name)
        if entity is None or entity.entity_type != self.entity_type.value:
            raise self._not_found(entity_id)
        specialized = cast(T | None, getattr(entity, self.relationship_name))
        if specialized is None:
            raise self._not_found(entity_id)
        return entity, specialized

    async def validate(self, **_payload: Any) -> None:  # noqa: B027
        """Type-specific payload validation.

        A no-op by default, overridden where a type has a link to check. Kept
        concrete rather than abstract on purpose: four of the six types have
        nothing to validate, and making them each declare an empty override
        would be noise that reads as if validation were meaningful for them.
        The payload is keyword-only and discarded, so a type without links
        cannot silently swallow a field it does not understand.
        """

    async def get(self, entity_id: UUID) -> tuple[Entity, T]:
        """Get a specialization together with its base entity."""
        return await self._resolve(entity_id)

    def _live_pairs_stmt(self, name_contains: str | None) -> Select[Any]:
        """Select live entities of this type that have a live specialization.

        The existence check is part of the query rather than a filter applied
        afterwards. Filtering after paging would let a page come back short
        while the total counted every row, so a client paging through the
        results would see gaps it cannot explain.
        """
        model = cast(Any, self.model)
        return self.entity_repo.filtered_stmt(
            entity_type=self.entity_type.value, name_contains=name_contains
        ).where(
            select(model.entity_id)
            .where(model.entity_id == Entity.id, model.deleted_at.is_(None))
            .exists()
        )

    async def list(
        self,
        *,
        name_contains: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[tuple[Entity, T]]:
        """List this campaign's specializations, newest entity first.

        Entities of the right type without a specialization row are excluded by
        the query: they are a normal transient state between the two create
        calls, not something to report as an incomplete actor.
        """
        entities = await self.entity_repo.list_filtered_with(
            relationship_names=(self.relationship_name,),
            base_stmt=self._live_pairs_stmt(name_contains),
            offset=offset,
            limit=limit,
        )
        pairs: list[tuple[Entity, T]] = []
        for entity in entities:
            specialized = cast(T | None, getattr(entity, self.relationship_name))
            if specialized is not None:
                pairs.append((entity, specialized))
        return pairs

    async def count(self, *, name_contains: str | None = None) -> int:
        """Count specializations matching the list filters.

        Uses the same predicate as :meth:`list`, so the total always equals the
        number of rows a client can page through.
        """
        stmt = self._live_pairs_stmt(name_contains)
        result = await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        return int(result.scalar_one())

    async def create(self, entity_id: UUID, **payload: Any) -> tuple[Entity, T]:
        """Create the specialization for an existing entity of the right type."""
        entity = await self.entity_repo.get_with(entity_id, self.relationship_name)
        if entity is None or entity.entity_type != self.entity_type.value:
            raise self._not_found(entity_id)
        if getattr(entity, self.relationship_name) is not None:
            raise ConflictError(
                f"{self.label.capitalize()} already exists for this entity",
                {"entity_id": str(entity_id)},
            )
        await self.validate(**payload)
        specialized = self.model(entity_id=entity_id, **payload)
        self.session.add(specialized)
        await self.session.flush()
        # Reload the relationship so the caller can build the response from it
        # without a second query. The row is live, so the primaryjoin matches.
        await self.session.refresh(entity, [self.relationship_name])
        return entity, cast(T, getattr(entity, self.relationship_name))

    async def update(self, entity_id: UUID, **payload: Any) -> tuple[Entity, T]:
        """Update specialization fields. The entity is never modified."""
        entity, specialized = await self._resolve(entity_id)
        await self.validate(**payload)
        for key, value in payload.items():
            setattr(specialized, key, value)
        await self.session.flush()
        # updated_at is a server-side default, so it is expired after the write.
        await self.session.refresh(specialized)
        return entity, specialized

    async def soft_delete(self, entity_id: UUID) -> bool:
        """Soft delete the specialization, keeping the entity intact."""
        _, specialized = await self._resolve(entity_id)
        specialized.deleted_at = datetime.now(UTC)  # type: ignore[attr-defined]
        await self.session.flush()
        return True


class ActorRepository(SpecializedRepository[Actor]):
    """Repository for Actor operations."""

    entity_type = EntityType.ACTOR
    relationship_name = "actor"

    @property
    def model(self) -> type[Actor]:
        return Actor


class PlayerRepository(SpecializedRepository[Player]):
    """Repository for Player operations."""

    entity_type = EntityType.PLAYER
    relationship_name = "player"

    @property
    def model(self) -> type[Player]:
        return Player

    async def validate(self, **payload: Any) -> None:
        """``user_id``, when supplied, must reference a real user.

        Supplied on create only. The update schema forbids the field, so an
        update never re-validates a link it is not allowed to change.
        """
        user_id = payload.get("user_id")
        if user_id is None:
            return
        from app.repositories.user_repo import UserRepository

        user = await UserRepository(self.session, None).get(user_id)
        if user is None:
            raise ValidationError("User not found", {"user_id": str(user_id)})

    async def get_by_user(self, user_id: UUID) -> list[Entity]:
        """List this campaign's players linked to a user."""
        players = await self.entity_repo.list_filtered_with(
            relationship_names=(self.relationship_name,),
            entity_type=self.entity_type.value,
        )
        return [
            entity
            for entity in players
            if cast(Player, entity.player).user_id == user_id
        ]


class PlayerCharacterRepository(SpecializedRepository[PlayerCharacter]):
    """Repository for PlayerCharacter operations."""

    entity_type = EntityType.PLAYER_CHARACTER
    relationship_name = "player_character"

    @property
    def model(self) -> type[PlayerCharacter]:
        return PlayerCharacter

    async def validate(self, **payload: Any) -> None:
        """``player_id``, when supplied, must be a player in this same campaign.

        The foreign key only proves the player row exists somewhere. Without
        this check a character in one campaign could be linked to another
        campaign's player. Supplied on create only; the update schema forbids
        the field.
        """
        player_id = payload.get("player_id")
        if player_id is None:
            return
        player_repo = PlayerRepository(self.session, self.campaign_id)
        try:
            await player_repo.get(player_id)
        except NotFoundError as exc:
            raise ValidationError(
                "Player not found in this campaign", {"player_id": str(player_id)}
            ) from exc

    async def list_by_player(
        self, player_id: UUID
    ) -> list[tuple[Entity, PlayerCharacter]]:
        """List this campaign's characters belonging to a player."""
        pairs = await self.list()
        return [
            (entity, character)
            for entity, character in pairs
            if character.player_id == player_id
        ]


class LocationRepository(SpecializedRepository[Location]):
    """Repository for Location operations."""

    entity_type = EntityType.LOCATION
    relationship_name = "location"

    @property
    def model(self) -> type[Location]:
        return Location


class ItemRepository(SpecializedRepository[Item]):
    """Repository for Item operations."""

    entity_type = EntityType.ITEM
    relationship_name = "item"

    @property
    def model(self) -> type[Item]:
        return Item


class FactionRepository(SpecializedRepository[Faction]):
    """Repository for Faction operations."""

    entity_type = EntityType.FACTION
    relationship_name = "faction"

    @property
    def model(self) -> type[Faction]:
        return Faction

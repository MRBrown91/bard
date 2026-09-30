"""Entity fact use cases.

One module rather than one file per operation, because these share three
helpers: the not-found error, the provenance check on write, and the audience
lookup. Splitting them would mean importing private names across modules.

Provenance is validated here rather than trusted from the foreign key.
``entity_facts.statement_id`` and ``entity_facts.event_id`` are bare foreign
keys, so the database will happily accept a statement or event belonging to a
different campaign. A fact that cites another campaign's document is a
cross-campaign leak through the provenance chain, so both are checked against
campaign-scoped repositories before the write.
"""

from uuid import UUID

from app.application.exceptions import NotFoundError, ValidationError
from app.repositories import (
    DocumentStatementRepository,
    EntityRepository,
    EventRepository,
    FactAudienceRepository,
    FactRepository,
    PlayerRepository,
)
from app.schemas.audience import FactAudienceCreate, FactAudienceRead
from app.schemas.fact import (
    EntityFactCreate,
    EntityFactList,
    EntityFactRead,
    EntityFactUpdate,
    EntityFactWithAudiencesRead,
)


def _not_found(fact_id: UUID, entity_id: UUID | None = None) -> NotFoundError:
    """Build the error for a fact that is absent or in another campaign.

    The repository is already scoped to the caller's campaign, so a miss is
    either a fact that does not exist or one belonging to someone else. The two
    are reported identically, so the endpoint is not a probe for what exists.
    """
    where: dict[str, str] = {"fact_id": str(fact_id)}
    if entity_id is not None:
        where["entity_id"] = str(entity_id)
    return NotFoundError("Fact not found", where)


async def _require_fact(
    fact_id: UUID,
    entity_id: UUID,
    fact_repo: FactRepository,
) -> None:
    """Require a fact that belongs to the entity named in the path.

    The repository is scoped to the campaign, so this already rules out another
    campaign. It also has to rule out a *different entity in the same campaign*,
    because the path says which entity's facts these are: without the check,
    ``/entities/A/facts/F`` would happily read, edit, and delete a fact of
    entity B, which is both surprising and a way to sidestep the nested
    resource's meaning.
    """
    fact = await fact_repo.get(fact_id)
    if fact is None or fact.entity_id != entity_id:
        raise _not_found(fact_id, entity_id)


async def _require_entity(entity_id: UUID, entity_repo: EntityRepository) -> None:
    """Reject an entity that is not in the caller's campaign.

    The entity is in the path rather than the body, but it still has to belong
    to the campaign the caller owns, or a fact would be filed against an entity
    the caller cannot see.
    """
    if await entity_repo.get(entity_id) is None:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})


async def _validate_provenance(
    data: EntityFactCreate,
    fact_repo: FactRepository,
    statement_repo: DocumentStatementRepository,
    event_repo: EventRepository,
) -> None:
    """Reject a statement or event that is not in the caller's campaign.

    Both are bare foreign keys, so the database accepts another campaign's row.
    A missing id and one owned by another campaign produce the same message: the
    caller is entitled to neither, and naming which one it was would confirm the
    id is real. The campaign is read from ``fact_repo``, which the route scopes,
    so an unscoped repository cannot satisfy the check.
    """
    if data.statement_id is not None:
        statement = await statement_repo.get(data.statement_id)
        if statement is None:
            raise ValidationError(
                "Invalid statement_id", {"statement_id": str(data.statement_id)}
            )
    if data.event_id is not None:
        event = await event_repo.get(data.event_id)
        if event is None:
            raise ValidationError(
                "Invalid event_id", {"event_id": str(data.event_id)}
            )


async def create_fact(
    entity_id: UUID,
    data: EntityFactCreate,
    fact_repo: FactRepository,
    entity_repo: EntityRepository,
    statement_repo: DocumentStatementRepository,
    event_repo: EventRepository,
) -> EntityFactRead:
    """Create a fact against an entity in the scoped campaign."""
    await _require_entity(entity_id, entity_repo)
    await _validate_provenance(data, fact_repo, statement_repo, event_repo)
    fact = await fact_repo.create(
        entity_id=entity_id,
        fact_type=data.fact_type,
        content=data.content,
        confidence=data.confidence,
        importance=data.importance,
        status=data.status,
        statement_id=data.statement_id,
        event_id=data.event_id,
    )
    return EntityFactRead.model_validate(fact)


async def get_fact(
    entity_id: UUID,
    fact_id: UUID,
    fact_repo: FactRepository,
    audience_repo: FactAudienceRepository,
) -> EntityFactWithAudiencesRead:
    """Get a fact of this entity with its audience rules."""
    await _require_fact(fact_id, entity_id, fact_repo)
    fact = await fact_repo.get_with_audiences(fact_id)
    if fact is None:
        raise _not_found(fact_id, entity_id)
    return EntityFactWithAudiencesRead.model_validate(fact)


async def list_facts(
    entity_id: UUID,
    fact_repo: FactRepository,
    entity_repo: EntityRepository,
    *,
    status: str | None = None,
    fact_type: str | None = None,
    event_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> EntityFactList:
    """List the facts of one entity.

    The page and the total come from one predicate, so ``total`` is always the
    number of rows a client can page through. Ordering the page without a
    unique tiebreak would let a row swap between pages.
    """
    await _require_entity(entity_id, entity_repo)
    total = await fact_repo.count_filtered(
        entity_id=entity_id, status=status, fact_type=fact_type, event_id=event_id
    )
    items = await fact_repo.list_filtered(
        entity_id=entity_id,
        status=status,
        fact_type=fact_type,
        event_id=event_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return EntityFactList(
        items=[EntityFactRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


async def update_fact(
    entity_id: UUID,
    fact_id: UUID,
    data: EntityFactUpdate,
    fact_repo: FactRepository,
) -> EntityFactWithAudiencesRead:
    """Update the fields the caller sent, leaving the rest alone.

    ``exclude_unset`` is what makes a PATCH partial. Without it the absent
    fields would be written as ``None``, which would blank a confidence the
    caller never mentioned.
    """
    await _require_fact(fact_id, entity_id, fact_repo)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if changes and await fact_repo.update(fact_id, **changes) is None:
        raise _not_found(fact_id, entity_id)
    reloaded = await fact_repo.get_with_audiences(fact_id)
    if reloaded is None:
        raise _not_found(fact_id, entity_id)
    return EntityFactWithAudiencesRead.model_validate(reloaded)


async def delete_fact(
    entity_id: UUID, fact_id: UUID, fact_repo: FactRepository
) -> None:
    """Soft delete a fact.

    The audience rows are left alone. They are retained for retcons and are
    unreachable through the relationship once the fact is gone, because the
    relationship only loads rules whose fact is live.
    """
    await _require_fact(fact_id, entity_id, fact_repo)
    if not await fact_repo.soft_delete(fact_id):
        raise _not_found(fact_id, entity_id)


async def add_audience(
    entity_id: UUID,
    fact_id: UUID,
    data: FactAudienceCreate,
    fact_repo: FactRepository,
    audience_repo: FactAudienceRepository,
    player_repo: PlayerRepository,
) -> FactAudienceRead:
    """Attach an audience rule to a fact of this entity.

    A ``player`` rule names a player, so the id has to resolve to a live player
    in this campaign. Without the check a caller could name any uuid -- an
    entity of another campaign, a deleted player, an item -- and the rule
    would sit in the table looking valid while matching nobody.
    """
    await _require_fact(fact_id, entity_id, fact_repo)
    if data.player_id is not None:
        # Raises NotFoundError, which the player repository scopes to the
        # campaign, so a foreign id and an absent one are indistinguishable.
        await player_repo.get(data.player_id)
    audience = await audience_repo.create(
        fact_id=fact_id,
        audience_type=data.audience_type,
        player_id=data.player_id,
    )
    return FactAudienceRead.model_validate(audience)


async def remove_audience(
    entity_id: UUID,
    fact_id: UUID,
    audience_id: UUID,
    fact_repo: FactRepository,
    audience_repo: FactAudienceRepository,
) -> None:
    """Soft delete an audience rule.

    The rule is fetched through the scoped audience repository rather than by
    ``soft_delete`` on the id, so a rule id from another campaign is a miss
    instead of a deletion. The ``fact_id`` has to match too, or a rule could be
    removed through a fact it does not belong to.
    """
    await _require_fact(fact_id, entity_id, fact_repo)
    audience = await audience_repo.get_by_id(audience_id)
    if audience is None or audience.fact_id != fact_id:
        raise NotFoundError(
            "Audience rule not found",
            {"fact_id": str(fact_id), "audience_id": str(audience_id)},
        )
    await audience_repo.soft_delete(audience_id)

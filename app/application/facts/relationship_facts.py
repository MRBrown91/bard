"""Relationship fact use cases.

Mirrors ``facts.py`` deliberately, so the two fact types cannot drift apart in
how they treat provenance, audiences, or campaign isolation. The differences
are structural rather than stylistic:

- A relationship fact is addressed at campaign level, not nested under an
  entity. Two entities are involved and neither owns the relationship, so
  ``/entities/{id}/facts/{fid}`` has no honest form for it.
- It has two entity references to validate, and they must both be in the
  caller's campaign. Neither column is campaign-scoped by a foreign key, so the
  database will happily store a relationship between two entities of another
  campaign.
- ``source_entity_id`` and ``target_entity_id`` are immutable, and so is
  ``relationship_type``. See ``RelationshipFactRepository.UPDATABLE_FIELDS``.

The same provenance rule as entity facts applies: ``statement_id`` and
``event_id`` are bare foreign keys, so a fact citing another campaign's document
is a leak through the provenance chain and both are checked before the write.
"""

from uuid import UUID

from app.application.exceptions import NotFoundError, ValidationError
from app.repositories import (
    DocumentStatementRepository,
    EntityRepository,
    EventRepository,
    PlayerRepository,
    RelationshipFactAudienceRepository,
    RelationshipFactRepository,
)
from app.schemas.audience import (
    RelationshipFactAudienceCreate,
    RelationshipFactAudienceRead,
)
from app.schemas.fact import (
    EntityRelationshipFactCreate,
    EntityRelationshipFactList,
    EntityRelationshipFactRead,
    EntityRelationshipFactUpdate,
    EntityRelationshipFactWithAudiencesRead,
)


def _not_found(fact_id: UUID) -> NotFoundError:
    """Build the error for a relationship fact that is absent or in another campaign.

    Identical treatment to entity facts (ADR-011): the repository is already
    scoped to the caller's campaign, so a miss does not distinguish an absent
    fact from a foreign one, and reporting which would make the endpoint a probe
    for what exists.
    """
    return NotFoundError("Relationship fact not found", {"fact_id": str(fact_id)})


async def _require_entity(entity_id: UUID, entity_repo: EntityRepository) -> None:
    """Reject an entity that is not in the caller's campaign.

    Used for both ends of a relationship. The id comes from the body rather than
    the path, which makes the check more important, not less: nothing else would
    stop a caller naming another campaign's entity.
    """
    if await entity_repo.get(entity_id) is None:
        raise NotFoundError("Entity not found", {"entity_id": str(entity_id)})


async def _validate_entities(
    data: EntityRelationshipFactCreate,
    entity_repo: EntityRepository,
) -> None:
    """Require two distinct, live entities from the caller's campaign.

    A relationship from an entity to itself is refused. The foreign keys accept
    it, and a self-relationship is meaningless as a claim about two things: it
    would also make the materialized relationship in P1D.3 a self-loop, which
    every traversal downstream would then have to special-case.
    """
    if data.source_entity_id == data.target_entity_id:
        raise ValidationError(
            "A relationship cannot have the same source and target entity",
            {"source_entity_id": str(data.source_entity_id)},
        )
    await _require_entity(data.source_entity_id, entity_repo)
    await _require_entity(data.target_entity_id, entity_repo)


async def _validate_provenance(
    data: EntityRelationshipFactCreate,
    statement_repo: DocumentStatementRepository,
    event_repo: EventRepository,
) -> None:
    """Reject a statement or event that is not in the caller's campaign.

    Both are bare foreign keys, so the database accepts another campaign's row.
    A missing id and one owned by another campaign produce the same message: the
    caller is entitled to neither, and naming which one it was would confirm the
    id is real.
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


async def create_relationship_fact(
    data: EntityRelationshipFactCreate,
    fact_repo: RelationshipFactRepository,
    entity_repo: EntityRepository,
    statement_repo: DocumentStatementRepository,
    event_repo: EventRepository,
) -> EntityRelationshipFactRead:
    """Create a relationship claim between two entities of this campaign.

    Both entity references are validated before the write, so a cross-campaign
    relationship cannot be stored. The ``campaign_id`` comes from the repository
    scope, which the transport layer has already authorized.
    """
    await _validate_entities(data, entity_repo)
    await _validate_provenance(data, statement_repo, event_repo)
    fact = await fact_repo.create(
        source_entity_id=data.source_entity_id,
        target_entity_id=data.target_entity_id,
        relationship_type=data.relationship_type,
        content=data.content,
        confidence=data.confidence,
        importance=data.importance,
        status=data.status,
        statement_id=data.statement_id,
        event_id=data.event_id,
    )
    return EntityRelationshipFactRead.model_validate(fact)


async def get_relationship_fact(
    fact_id: UUID,
    fact_repo: RelationshipFactRepository,
    audience_repo: RelationshipFactAudienceRepository,
) -> EntityRelationshipFactWithAudiencesRead:
    """Get one relationship fact with its audience rules."""
    fact = await fact_repo.get_with_audiences(fact_id)
    if fact is None:
        raise _not_found(fact_id)
    return EntityRelationshipFactWithAudiencesRead.model_validate(fact)


async def list_relationship_facts(
    fact_repo: RelationshipFactRepository,
    entity_repo: EntityRepository,
    *,
    source_entity_id: UUID | None = None,
    target_entity_id: UUID | None = None,
    relationship_type: str | None = None,
    status: str | None = None,
    event_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> EntityRelationshipFactList:
    """List relationship facts for the campaign, filtered.

    When a filter names an entity, that entity is checked against the campaign
    before the query runs. A foreign id would otherwise return an empty page,
    which is indistinguishable from a campaign with no such relationship, and
    the endpoint would quietly confirm nothing about the entity rather than
    refusing it — the weaker contract the document endpoints already rejected.
    """
    if source_entity_id is not None:
        await _require_entity(source_entity_id, entity_repo)
    if target_entity_id is not None:
        await _require_entity(target_entity_id, entity_repo)

    total = await fact_repo.count_filtered(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relationship_type=relationship_type,
        status=status,
        event_id=event_id,
    )
    items = await fact_repo.list_filtered(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relationship_type=relationship_type,
        status=status,
        event_id=event_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return EntityRelationshipFactList(
        items=[EntityRelationshipFactRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


async def update_relationship_fact(
    fact_id: UUID,
    data: EntityRelationshipFactUpdate,
    fact_repo: RelationshipFactRepository,
) -> EntityRelationshipFactWithAudiencesRead:
    """Update the fields the caller sent, leaving the rest alone.

    ``exclude_unset`` makes the PATCH partial; without it an absent field would
    be written as ``None`` and blank a confidence the caller never mentioned.
    ``exclude_none`` additionally means a field cannot be cleared, which is why
    the schema marks the nullable ones as optional rather than nullable-to-null.
    The entity ids and ``relationship_type`` are refused by the schema and then
    again by the repository allow-list.
    """
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if changes and await fact_repo.update(fact_id, **changes) is None:
        raise _not_found(fact_id)
    reloaded = await fact_repo.get_with_audiences(fact_id)
    if reloaded is None:
        raise _not_found(fact_id)
    return EntityRelationshipFactWithAudiencesRead.model_validate(reloaded)


async def delete_relationship_fact(
    fact_id: UUID, fact_repo: RelationshipFactRepository
) -> None:
    """Soft delete a relationship fact.

    The audience rows are left alone, exactly as for entity facts: they are
    retained for retcons and become unreachable once the fact is gone, because
    the audience repository joins to a live fact.
    """
    if not await fact_repo.soft_delete(fact_id):
        raise _not_found(fact_id)


async def add_audience(
    fact_id: UUID,
    data: RelationshipFactAudienceCreate,
    fact_repo: RelationshipFactRepository,
    audience_repo: RelationshipFactAudienceRepository,
    player_repo: PlayerRepository,
) -> RelationshipFactAudienceRead:
    """Attach an audience rule to a relationship fact.

    A ``player`` rule names a player, so the id must resolve to a live player in
    this campaign. Without the check a caller could name any uuid and the rule
    would sit in the table looking valid while matching nobody.
    """
    if await fact_repo.get(fact_id) is None:
        raise _not_found(fact_id)
    if data.player_id is not None:
        await player_repo.get(data.player_id)
    audience = await audience_repo.create(
        fact_id=fact_id,
        audience_type=data.audience_type,
        player_id=data.player_id,
    )
    return RelationshipFactAudienceRead.model_validate(audience)


async def remove_audience(
    fact_id: UUID,
    audience_id: UUID,
    fact_repo: RelationshipFactRepository,
    audience_repo: RelationshipFactAudienceRepository,
) -> None:
    """Soft delete an audience rule from a relationship fact.

    The rule is resolved through the scoped audience repository and its fact_id
    is compared, so a rule id from another campaign or from another fact is a
    miss rather than a deletion.
    """
    if await fact_repo.get(fact_id) is None:
        raise _not_found(fact_id)
    audience = await audience_repo.get_by_id(audience_id)
    if audience is None or audience.fact_id != fact_id:
        raise NotFoundError(
            "Audience rule not found",
            {"fact_id": str(fact_id), "audience_id": str(audience_id)},
        )
    await audience_repo.soft_delete(audience_id)


__all__ = [
    "add_audience",
    "create_relationship_fact",
    "delete_relationship_fact",
    "get_relationship_fact",
    "list_relationship_facts",
    "remove_audience",
    "update_relationship_fact",
]

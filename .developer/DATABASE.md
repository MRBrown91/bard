# Database Schema

PostgreSQL is the authoritative persistence layer. `pgvector` is enabled for
future embeddings, but embeddings are not part of the initial domain model.

All persistent domain tables use a nullable `deleted_at` for soft deletion.
Facts and events may additionally use semantic `status` to represent
invalidation/retcons. Deletion and invalidation are different operations.

## User

```text
User
----
id UUID PK
auth_provider string
auth_subject string
display_name string
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

Unique `(auth_provider, auth_subject)`. Email is not the identity key.

## Campaign

```text
Campaign
--------
id UUID PK
user_id UUID FK User
name string
description text nullable
is_active boolean
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

`user_id` is the primary owner. Phase 1 access is limited to the owner.

## CampaignMember

```text
CampaignMember
--------------
id UUID PK
campaign_id UUID FK Campaign
user_id UUID FK User
role string
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

This is reserved for future sharing. It does not expand Phase 1 authorization.

## Session

```text
Session
-------
id UUID PK
campaign_id UUID FK Campaign
name string
session_number integer nullable
started_at timestamp nullable
ended_at timestamp nullable
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

A Session represents an actual D&D play session.

## Entity

```text
Entity
------
id UUID PK
campaign_id UUID FK Campaign
entity_type string
name string
description text nullable
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

Entity represents durable identity. Specialized tables hold stable canonical
fields. Facts and relationships hold evolving or historical information.

`entity_type` is validated in the application against a six-value enum —
`actor`, `player`, `player_character`, `location`, `item`, `faction` — and is
immutable once set. The column remains `varchar(50)` with no CHECK constraint
until Phase 2 (ADR-011, ADR-020). An NPC is an `actor`; there is no separate
`npc` type.

## EntityAlias

```text
EntityAlias
-----------
id UUID PK
entity_id UUID FK Entity
alias string
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

Aliases support deterministic transcript matching without polluting identity.

## Specialized entities

```text
Actor
-----
entity_id UUID PK/FK Entity
voice_instructions text nullable
personality text nullable
motivation text nullable
appearance text nullable

Player
------
entity_id UUID PK/FK Entity
user_id UUID FK User
status string

PlayerCharacter
---------------
entity_id UUID PK/FK Entity
player_id UUID FK Player

Location
--------
entity_id UUID PK/FK Entity
environment text nullable
atmosphere text nullable

Item
----
entity_id UUID PK/FK Entity
physical_description text nullable
effect_description text nullable

Faction
-------
entity_id UUID PK/FK Entity
purpose text nullable
description text nullable
```

Each of these also carries `created_at`, `updated_at`, and nullable
`deleted_at` from `TimestampMixin`. `entity_id` is both primary key and
foreign key, so each table is a strict one-to-one extension of `entities`
rather than table-per-class inheritance, and a specialized row shares the
UUID of its entity.

None of these tables has a `campaign_id` column, and none will get one. A
specialized row reaches its campaign only through `entity_id` →
`entities.campaign_id`, so campaign filtering is defined once on the entity
rather than repeated six times. See ADR-021.

Two further consequences of `entity_id` being the primary key: an id can never
belong to two types at once, and a specialized row cannot be orphaned onto a
deleted entity by a foreign key alone. Reads resolve the parent entity first,
so a soft-deleted entity hides its specialization as well.

Specialized tables intentionally remain small. Evolving facts such as current
location, ownership, injury, relationships, or character state belong in facts.

## Child tables referencing Entity

```text
Table                       Column                  References
entity_aliases              entity_id               entities.id
actors                      entity_id               entities.id
players                     entity_id               entities.id
player_characters           entity_id               entities.id
player_characters           player_id               players.entity_id
locations                   entity_id               entities.id
items                       entity_id               entities.id
factions                    entity_id               entities.id
entity_facts                entity_id               entities.id
entity_facts                campaign_id             campaigns.id
entity_relationship_facts   source_entity_id        entities.id
entity_relationship_facts   target_entity_id        entities.id
entity_relationship_facts   campaign_id             campaigns.id
```

Every foreign key runs one way, child to parent, so no cycle exists and no
table needs to be inserted before another. Entity creation is therefore
unconstrained: the entity is inserted first and its specialization second,
with no mutual dependency. `entity_facts` and `entity_relationship_facts` do
carry their own `campaign_id` and are filtered by it directly.

`entity_aliases` has no `campaign_id` of its own: an alias is reachable only
through its parent entity, and campaign scope reaches it by joining `entities`.
That is why any query over aliases must also filter the entity.

## Entity aliases hold the entity's own name

`entity_aliases.kind` distinguishes the two kinds of matchable term:

| kind | meaning | exact | case-insensitive |
|---|---|---|---|
| `name` | the entity's own current name | 1.0 | 0.9 |
| `alias` | an alternative name | 0.95 | 0.85 |

An entity always has exactly one live `name` row, so `entity_aliases` is the
complete set of strings the entity matcher can recognise and the vocabulary is a
single join. See ADR-027 for why this is storage rather than behaviour, and for
the costs accepted in exchange.

Two constraints hold the shape:

| index | columns | purpose |
|---|---|---|
| `uq_entity_aliases_entity_alias` | `(entity_id, alias)` unique | no duplicate term for one entity |
| `uq_entity_aliases_one_name` | `(entity_id)` unique, partial on `kind = 'name' AND deleted_at IS NULL` | at most one live name row |

The second is partial so that a soft-deleted name row does not block the
creation or restoration of another. Nothing in the schema enforces that a name
row *exists* — that is a cross-table invariant, so it is asserted by
`test_every_live_entity_has_exactly_one_live_name_alias` rather than by a
constraint.

Consequences for writes, all of which are exercised in
`tests/application/entities/test_entity_use_cases.py`:

- `create_entity` writes the `name` row first, then the requested aliases.
- `update_entity` retargets the `name` row on a rename. A rename onto an
  existing alias is refused, since `(entity_id, alias)` is unique and the two
  would otherwise collide.
- `add_alias` refuses an alias equal to the entity's current name.
- `remove_alias` refuses a `name` row. Removing it would leave an entity that
  exists but can never be recognised by the name it is called; the caller is
  told to rename instead.
- Soft-deleting an entity stamps its `name` row in the same transaction as its
  specialization, so a deleted entity stops being recognized while the row
  remains for retcons. A restore must un-delete the `name` row in the same way;
  no restore path exists yet.

No foreign key uses `ON DELETE CASCADE`. Soft deletion is application-level
and stamps `deleted_at` on the parent and its specialization in one
transaction, preserving history for retcons (ADR-010).

### One row per flush

The unit of work orders a flush by `relationship()` declarations, not by
foreign key columns. This schema expresses ownership as foreign key columns
without ORM relationships, so an `entities` row and its `campaigns` parent
have no dependency edge and can be emitted in either order. Adding both to one
session and committing once produces `IntegrityError` on the child's foreign
key, because the parent has not been written.

This is documented SQLAlchemy behaviour, not a defect, and the models are
deliberately built this way (ADR-021, ADR-023). Every write path therefore
flushes one row at a time. There are three: `BaseRepository.create`,
`SpecializedRepository.create`, and `resolve_current_user`, each of which adds
and flushes immediately. A write that needs several rows must flush the parent
explicitly in between. `tests/repositories/test_one_row_per_flush.py` guards
this.

This matters for DELETE as well as INSERT. Bulk cleanup has to remove children
before parents regardless of ORM ordering, which is what makes
`soft_delete_with_statements` stamp the parent and its children in one flush
rather than issuing separate deletes.

## Document

```text
Document
--------
id UUID PK
campaign_id UUID FK Campaign
session_id UUID FK Session nullable
document_type string
title string
content text
source_type string nullable
source_reference string nullable
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

A null `session_id` means campaign-level source material.

`Document.content` is the verbatim text that the fact chain points back to.
`DocumentStatement.content` is one ordered anchor inside it. The two are
independent: they are never synchronised, and editing one does not rewrite the
other. Statements are the curated, reorderable, position-bearing view that
extraction and citation depend on, so regenerating them from the document text
would throw that curation away.

`document_type` and `source_type` are unconstrained strings, not enums. Neither
has a settled vocabulary, and fixing one now would mean a migration in front of
the first real corpus.

## DocumentStatement

```text
DocumentStatement
-----------------
id UUID PK
document_id UUID FK Document
position integer
content text
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

Facts point to statements rather than directly to documents. This preserves
precise extraction provenance.

`position` carries no uniqueness constraint, because curated ordering is
meaningful and duplicates are legitimate. Read order is therefore
`(position, created_at, id)`, fixed in both the `Document.statements`
relationship and `DocumentStatementRepository.get_by_document`, so a tie cannot
reorder between reads.

`document_statements` has no `campaign_id` column, deliberately. Campaign
isolation for a statement is resolved through its parent `Document`, so every
scoped read joins `documents` and filters `documents.campaign_id`; the join also
requires `documents.deleted_at IS NULL`, so a statement under a deleted document
is unreachable. The generic repository campaign scope cannot do this on its own,
because it is a no-op for a table without that column.

That no-op makes it the repository's job, not the caller's, and this includes
the methods inherited from `BaseRepository` (ADR-029). `soft_delete` and `update`
resolve the row through `get`, so an unscoped `get` on this table would stamp or
edit a statement in any campaign given only its id while reporting success.
`DocumentStatementRepository` therefore overrides `get` and `exists` to apply the
parent join, and every read of a statement carries two deletion predicates: the
statement's own and its document's. `create` is left unscoped and is documented as
such, because the insert has no row to scope against — the application layer
resolves the document first instead. The same applies to `entity_aliases`.

## EntityFact

```text
EntityFact
----------
id UUID PK
campaign_id UUID FK Campaign
statement_id UUID FK DocumentStatement nullable
entity_id UUID FK Entity
event_id UUID FK Event nullable
fact_type string
content text
confidence float nullable
importance integer
status string
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

Example: `King John has blue eyes.` A fact belongs to one entity. `confidence`
means extraction/system confidence, not fictional-world truth.

## EntityRelationshipFact

```text
EntityRelationshipFact
----------------------
id UUID PK
campaign_id UUID FK Campaign
statement_id UUID FK DocumentStatement nullable
source_entity_id UUID FK Entity
target_entity_id UUID FK Entity
event_id UUID FK Event nullable
relationship_type string
content text
confidence float nullable
importance integer
status string
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

Example: `King John owns Mirabel.` A relationship fact is itself a fact and
therefore carries provenance, confidence, importance, and status.

## EntityRelationship

```text
EntityRelationship
------------------
id UUID PK
campaign_id UUID FK Campaign
source_entity_id UUID FK Entity
target_entity_id UUID FK Entity
relationship_type string
relationship_fact_id UUID FK EntityRelationshipFact
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

This is the materialized/current relationship representation. Queries must not
return relationships whose supporting fact is deleted or semantically invalid.

Indexes are required on campaign/source, campaign/target, and the relationship
fact foreign key. Additional indexes should be added only for measured access
patterns.

## Event

```text
Event
-----
id UUID PK
campaign_id UUID FK Campaign
title string
description text nullable
occurred_at timestamp nullable
game_time string nullable
status string
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

Events group facts belonging to the same occurrence. There is no direct Event →
DocumentStatement relationship; constituent facts provide provenance.

Example: `Bob and Phil killed Sue` can be represented as one Event with two
relationship facts:

- Bob → killed → Sue
- Phil → killed → Sue

No three-entity fact table is required.

## Knowledge audiences

```text
EntityFactAudience
------------------
id UUID PK
fact_id UUID FK EntityFact
audience_type string
player_id UUID FK Player nullable
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable

EntityRelationshipFactAudience
------------------------------
id UUID PK
fact_id UUID FK EntityRelationshipFact
audience_type string
player_id UUID FK Player nullable
created_at timestamp
updated_at timestamp
deleted_at timestamp nullable
```

Visibility is fact-level. Retrieval must enforce visibility before player-facing
context is constructed. The LLM is never the security boundary.

**The audience tables carry no `campaign_id`.** A rule is in a campaign only
through its fact, so a campaign-scoped read has to join to the parent fact and
filter on `entity_facts.campaign_id`. The join also requires
`entity_facts.deleted_at IS NULL`: without it, deleting a fact would leave its
rules readable through the audience repository, because a soft-deleted parent
is still a row that joins. Both conditions live in the repository's shared
statement builder, so no audience read can accidentally omit them.

**`audience_type` and `player_id` are paired by the application,** not by the
schema, because ADR-011 defers database CHECK constraints. `player` requires a
`player_id`; no other type may carry one. A `player_id` is additionally
resolved through the campaign-scoped `PlayerRepository` on write. The pairing
alone would accept any uuid, including one from another campaign, so the two
checks are not redundant.

**Audience rules are stored in Phase 1 but not enforced.** See ADR-025. The
enforcement is a query filter to be added in Phase 2, before the first read that
is not owner-only.

## Invariants

- Every Entity belongs to exactly one Campaign.
- Every `entity_type` is one of the six enum values and never changes after creation.
- Every entity type has exactly one specialization table, so every entity eventually has exactly one specialized row.
- Specialized tables carry no `campaign_id`; a specialized row is in a campaign only through its entity. A cross-campaign read is impossible by construction, and the foreign key on `player_characters.player_id` alone does not guarantee same-campaign links — that is validated in the application.
- Entity aliases cannot cross campaigns through their entity.
- Every fact belongs to the same Campaign as its referenced entity/entities.
- Every relationship fact has two entities in the same Campaign.
- PlayerCharacter references a Player in the same Campaign through its entity.
- Document statements cannot outlive their document. Soft-deleting a document stamps its live statements in the same flush, and the rows are retained, because facts reference them.
- Document and statement content are independent. Neither is generated from the other.
- Soft-deleted records are excluded from normal active queries. A soft-deleted specialization is treated as absent by the relationship and by the API.
- Soft-deleting an entity also stamps its specialization in the same transaction.
- Semantic invalidation is not equivalent to deletion.

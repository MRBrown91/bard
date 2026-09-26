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

Specialized tables intentionally remain small. Evolving facts such as current
location, ownership, injury, relationships, or character state belong in facts.

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

## Invariants

- Every Entity belongs to exactly one Campaign.
- Entity aliases cannot cross campaigns through their entity.
- Every fact belongs to the same Campaign as its referenced entity/entities.
- Every relationship fact has two entities in the same Campaign.
- PlayerCharacter references a Player in the same Campaign through its entity.
- Document statements cannot outlive their document.
- Soft-deleted records are excluded from normal active queries.
- Semantic invalidation is not equivalent to deletion.

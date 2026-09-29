# Phase 1 — Domain and Backend Foundation

> **Purpose:** Deliver complete REST APIs for campaign management, entities, documents, facts, events, and relationships with authentication, campaign isolation, and visibility enforcement. WebSocket protocol skeleton for live transcript processing.

> **Prerequisite:** All PrePhase1 steps `Completed`.

---

## Step Status Legend
- `Planning` — Defined but not approved for implementation
- `Approved` — Ready to implement; awaiting developer action
- `Completed` — Implemented, tested, merged

---

## Phase 1A — Campaign & Session APIs

### P1A.1 — Campaign CRUD API

**Status:** `Completed` (commit: 929d585)

**Goal:** Full campaign lifecycle management.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns` | Create campaign (authenticated user becomes owner) |
| GET | `/api/campaigns` | List user's campaigns (paginated) |
| GET | `/api/campaigns/{campaign_id}` | Get campaign details |
| PATCH | `/api/campaigns/{campaign_id}` | Update campaign (name, description, is_active) |
| DELETE | `/api/campaigns/{campaign_id}` | Soft delete campaign |

**Application:** No use-case layer. Routes call `CampaignRepository` directly; campaign authorization uses `get_current_campaign` in `app/application/campaigns/get_current_campaign.py` via the `CurrentCampaign` dependency.
**Repository:** `CampaignRepository` (from PrePhase1)
**Schemas:** `CampaignCreate`, `CampaignRead`, `CampaignUpdate`, `CampaignList`

**Authorization:** Owner-only for PATCH/DELETE/GET-by-id. List returns only owned campaigns.

**Known deviation:** `app/api/http/routes/campaigns.py` places persistence calls in route handlers, which AGENTS.md prohibits. P1B.1 introduced a use-case layer for entities; campaigns and sessions have not been migrated yet.

**Tests:**
- Unit: service methods with fake repo
- Integration: full CRUD flow with auth, cross-user isolation

---

### P1A.2 — Campaign Member API (Stub for Future Sharing)

**Status:** `Completed` (commit: 929d585)

**Goal:** Scaffold membership endpoints (no permission enforcement yet).

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/members` | Add member (owner only) |
| GET | `/api/campaigns/{campaign_id}/members` | List members |
| DELETE | `/api/campaigns/{campaign_id}/members/{member_id}` | Remove member |

**Note:** Phase 1 does not expand authorization beyond owner. Members are recorded for future use.

**Tests:** Basic CRUD; owner enforcement.

---

### P1A.3 — Session CRUD API

**Status:** `Completed` (commit: 929d585)

**Goal:** Session management within a campaign.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------------------|
| POST | `/api/campaigns/{campaign_id}/sessions` | Create session |
| GET | `/api/campaigns/{campaign_id}/sessions` | List sessions (paginated, filter by active/ended) |
| GET | `/api/campaigns/{campaign_id}/sessions/{session_id}` | Get session details |
| PATCH | `/api/campaigns/{campaign_id}/sessions/{session_id}` | Update session (name, session_number, started_at, ended_at) |
| DELETE | `/api/campaigns/{campaign_id}/sessions/{session_id}` | Soft delete session |

**Application:** No use-case layer. Routes call `SessionRepository` directly (same deviation as P1A.1).
**Repository:** `SessionRepository`
**Schemas:** `SessionCreate`, `SessionRead`, `SessionUpdate`, `SessionList`

**Authorization:** Campaign owner only (via campaign scope dependency).

**Tests:** Full CRUD; campaign isolation; session_number uniqueness per campaign.

---

## Phase 1B — Entity APIs

### P1B.1 — Entity Core CRUD API

**Status:** `Completed`

**Goal:** Manage base entities and aliases.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entities` | Create entity (type, name, description) |
| GET | `/api/campaigns/{campaign_id}/entities` | List entities (filter by type, search by name/description) |
| GET | `/api/campaigns/{campaign_id}/entities/{entity_id}` | Get entity with aliases (specialized data lands in P1B.2) |
| PATCH | `/api/campaigns/{campaign_id}/entities/{entity_id}` | Update base entity name and description. `entity_type` is immutable and rejected with a 422; see P1B.2 |
| DELETE | `/api/campaigns/{campaign_id}/entities/{entity_id}` | Soft delete entity |

**Alias Sub-resource:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entities/{entity_id}/aliases` | Add alias |
| DELETE | `/api/campaigns/{campaign_id}/entities/{entity_id}/aliases/{alias_id}` | Soft delete alias |

**Application:** Use-case functions in `app/application/entities/` (`create_entity`, `add_alias`, `get_entity`, `get_entity_with_aliases`, `list_entities`, `update_entity`, `soft_delete_entity`, `remove_alias`).
**Repository:** `EntityRepository`, `EntityAliasRepository`
**Schemas:** `EntityCreate`, `EntityRead`, `EntityUpdate`, `EntityList`, `EntityWithAliasesRead`, `EntityAliasCreate`, `EntityAliasRead`

**Authorization:** Campaign owner, enforced by the `CurrentCampaign` dependency before any use case runs. The campaign is taken from the repository scope, never from the request body.

**Notes:**
- Reads exclude soft-deleted rows so retained history stays invisible to the application.
- Aliases are currently loaded with an explicit query. P1B.2 adds the `Entity.aliases` relationship for loading; the explicit alias join is retained regardless, because a relationship can load rows but cannot filter a query, and alias search needs both.
- All timestamps are timezone-aware UTC: columns are `timestamptz`, `deleted_at` is written with `datetime.now(UTC)`, and every connection pins `SET TIME ZONE 'UTC'`.

**Tests:** 57 tests across `tests/application/entities/`, `tests/repositories/test_entity_repo.py`, and `tests/api/test_entity_endpoints.py` covering CRUD, alias uniqueness, campaign scoping (asserted against compiled SQL), LIKE escaping, soft-delete visibility, UTC timestamps, and 401/404/409/422 mapping.

**Verified manually against the development database:** create, read, filter, wildcard escaping, patch, clearing description, alias add/remove, soft delete, cross-campaign 404, and unauthenticated 401. This surfaced two defects that mocked tests could not: `BaseRepository.create` injected `campaign_id` into `EntityAlias` (which has no such column), and `BaseRepository.update` left the server-managed `updated_at` expired, raising `MissingGreenlet` on serialisation. Both are fixed and covered by repository tests.

---

### P1B.2 — Specialized Entity APIs

**Status:** `Completed`

**Goal:** Manage the stable canonical fields that only apply to one entity type, reached through real ORM relationships on `Entity`.

#### Decisions

**Ownership lives on the entity, never on the specialization.** The six specialized tables have no `campaign_id` column and must not grow one. Every specialized read and write resolves the parent `Entity` through the campaign-scoped `EntityRepository` first, so campaign isolation is inherited from one place instead of reimplemented six times.

**`Entity` gains real ORM relationships.** The foreign keys all run one way, child to `entities.id`, so there is no cycle to design around:

| Relationship | Cardinality | Target |
|---|---|---|
| `Entity.actor`, `.player`, `.player_character`, `.location`, `.item`, `.faction` | one-to-one | specialization table via `entity_id` |
| `Entity.aliases` | one-to-many | `entity_aliases` |
| `Entity.facts` | one-to-many | `entity_facts` (P1D.1) |
| `Entity.relationships_as_source`, `.relationships_as_target` | one-to-many | `entity_relationship_facts` (P1D.2) |

Loads use `selectinload` so a list of entities fetches its specializations in one additional statement rather than one per row. `uselist=False` is required on the six one-to-one relationships; without it SQLAlchemy infers a collection from the absence of a uniqueness constraint it can see.

**Soft-deleted rows are invisible through the relationship.** Each specialization relationship filters `deleted_at IS NULL` in its `primaryjoin`. A plain relationship would return a soft-deleted actor as though it were live, because `TimestampMixin` puts `deleted_at` on the specialization models. This is the same "retain history, hide it from the application" rule already applied to entity and alias reads.

**Presence is not sufficient; type is asserted too.** Because `entity_id` is the primary key of every specialization table, a location entity can never share an id with an actor, so a presence check alone would technically be enough. The specialized repository asserts `entity_type` explicitly anyway, so the rejection is a deliberate 404 rather than an accident of the schema, and a stale row cannot survive a future type change.

**`entity_type` is an immutable six-value enum.** Per ADR-011 the enforcement is a Python enum plus Pydantic validation, not a database CHECK constraint. The values are `actor`, `player`, `player_character`, `location`, `item`, `faction`. An NPC is an `actor`; there is no separate `npc` type. `PATCH /entities/{id}` rejects any `entity_type` change with a 422 — converting an actor into a location means deleting and recreating.

**Exactly one specialization table per type, so the specialization is mandatory.** Every valid `entity_type` has a table. An entity is created first and its specialization second, which means an entity that exists without its specialization row is a normal transient state rather than corruption. While it is in that state, `GET /entities/{id}` returns it normally and the type endpoint returns 404. Enforcing a completeness invariant is deferred.

**Two calls, entity first.** `POST /entities` then `POST /actors`. The entity insert never depends on the specialization, which is the whole of the circularity rule. A combined payload is not provided.

**`EntityKeyMixin` stays narrow.** It carries `entity_id` and nothing else. The specialized models already inherit `TimestampMixin`, which supplies `created_at`, `updated_at`, and `deleted_at`, so no mixin needs to invent them. Widening the mixin to include `id` or timestamps would duplicate fields that already exist and would put a second `created_at` on the wire: a specialization's `created_at` is the same instant as its entity's, and two near-identical values that disagree by a few milliseconds produce a confusing client-side sort. Sorting reads the entity's `created_at`, which the response already carries.

**Specialized responses embed the base entity.** `/actors/{id}` returns the base entity fields and the actor fields together, so a list endpoint is usable in one request and there is a single `created_at` to sort on. This is a schema decision, not a query convenience, and it is why the entity is always loaded alongside.

**Soft-deleting an entity cascades to its specialization.** Both rows are stamped in the same transaction. Without it, deleting an entity leaves a live-looking actor row; it is unreachable through the API because every read is entity-scoped, but it is inconsistent state.

#### Endpoints

Flat sub-resources per type, not nested under the entity. The specialization shares the entity's id, so `{id}` is the same UUID in both places.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/actors` | Create actor for an existing `actor` entity |
| GET | `/api/campaigns/{campaign_id}/actors` | List actors (paginated, filter by name) |
| GET | `/api/campaigns/{campaign_id}/actors/{id}` | Get actor with embedded base entity |
| PATCH | `/api/campaigns/{campaign_id}/actors/{id}` | Update actor fields |
| DELETE | `/api/campaigns/{campaign_id}/actors/{id}` | Soft delete actor specialization |

The same five endpoints exist for `players`, `player-characters`, `locations`, `items`, and `factions`.

`POST /players` additionally requires `user_id`; `POST /player-characters` additionally requires `player_id`.

**Application:** Use-case functions in `app/application/entities/` alongside the core use cases, one module per type. No service layer.
**Repository:** `EntityRepository` plus `ActorRepository`, `PlayerRepository`, `PlayerCharacterRepository`, `LocationRepository`, `ItemRepository`, `FactionRepository`.
**Schemas:** `EntityType` (new `StrEnum` in `app/schemas/entity.py`, the only place entity types are declared) and `EntityKeyMixin` (in `app/schemas/common.py`), per-type create/update models, and per-type read models composed as `EntityKeyMixin` with the base entity embedded and no timestamps of their own, so the entity's `created_at` is the only one on the wire.

#### Schema and model corrections required first

The existing specialized code does not work and must be repaired before any endpoint is written:

- `app/schemas/specialized.py` read models inherit `IDMixin` and require `id`. These tables have no `id` column, only `entity_id`, so every read would fail validation. They are rebuilt on `EntityKeyMixin`.
- `app/schemas/specialized.py` has no `PlayerCharacterUpdate`.
- `BaseRepository.get`, `update`, and `exists` all filter on `self.model.id`, which does not exist on these models. The specialized repositories cannot inherit those methods as written.

Two committed P1B.1 behaviours become wrong once the enum exists. They are corrected as part of P1B.2's work, because the enum is introduced there:

- `EntityCreate.entity_type` accepts any string. It is constrained to the `EntityType` enum.
- `EntityUpdate.entity_type` is settable today. It is rejected, because the type is immutable. Sending it is a 422 rather than being silently ignored, so a client that expects the change to take effect is told plainly that it does not.

#### Validation

- Every write resolves the parent entity through the campaign-scoped `EntityRepository`, so a cross-campaign id is a 404 before any type check runs.
- The entity's `entity_type` must equal the endpoint's type, otherwise **404, not 422**. A wrong-type id, another campaign's id, an id that does not exist, and an entity whose specialization has not been created yet are deliberately indistinguishable, so a caller cannot use the response to learn which identifiers exist in campaigns they cannot see. The type predicate is part of the query for the same reason: a wrong-type row is never loaded and then rejected.
- Unknown fields are rejected rather than dropped. The specialized tables have few columns, so a client that guesses a field name would otherwise get a 201 and a response that looks like the value was saved. `extra="forbid"` on every specialized request turns that into a 422 naming the field.
- `POST` against an entity that already has a live specialization is a 409.
- `Player.user_id` must reference an existing user. Nothing currently prevents two player rows in the same campaign from claiming the same user, and the right fix is not obvious, so it is left alone rather than guessed at. A global unique constraint on `players.user_id` would also stop a gamemaster who owns players in two campaigns, and a per-campaign constraint is not expressible because these tables deliberately have no `campaign_id`. Enforcing "one player per user per campaign" therefore needs either a denormalized `campaign_id` or a partial unique index that resolves the campaign through the entity, and that is a schema decision for P1C, not a side effect of this phase.
- `PlayerCharacter.player_id` must reference a player **in the same campaign**. The foreign key alone will not catch a cross-campaign link, so this is validated explicitly.
- Reads exclude soft-deleted specializations and soft-deleted entities.

#### Tests

Type enforcement on every type; cross-campaign 404 on read, write, and delete; `PlayerCharacter` cross-campaign `player_id` rejection; duplicate specialization 409; soft-deleted specialization invisible through both the relationship and the endpoint; embedded base entity present and correct; `entity_type` immutability rejected with 422; campaign scoping asserted against compiled SQL; `list` and `count` sharing one predicate so a page is never short; a single `created_at` on the wire.

Two rules earned their tests through live-database failures that the mocked tests could not have caught, because both were invisible at the unit level:

- **`PATCH /players/{id}` could never succeed.** Repository link validation demanded `user_id` on every write, so a status-only update failed with "user_id is required". Link validation now applies only when the field is actually supplied. The update schema does not declare `user_id` at all, which is what makes the link immutable.
- **Paging could come back short.** `list` applied offset and limit to entities and then dropped the ones with no specialization row, while `count` counted every entity of the right type. Both now share one `EXISTS` predicate, so the total always equals the number of rows a client can page through.

---

## Phase 1C — Document APIs

### P1C.1 — Document CRUD API

**Status:** `Completed`

**Goal:** Manage source documents (campaign-level or session-level).

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/documents` | Create document (type, title, content, optional session_id) |
| GET | `/api/campaigns/{campaign_id}/documents` | List documents (filter by session_id, document_type; paged, returns a total) |
| GET | `/api/campaigns/{campaign_id}/documents/{document_id}` | Get document with statements |
| PATCH | `/api/campaigns/{campaign_id}/documents/{document_id}` | Update document metadata. `campaign_id` is immutable and rejected with a 422 |
| DELETE | `/api/campaigns/{campaign_id}/documents/{document_id}` | Soft delete document |

**Application:** Use-case functions in `app/application/documents/documents.py` (`create_document`, `get_document`, `list_documents`, `update_document`, `delete_document`). There is no `DocumentService`; the transport, use case, and repository layers are kept separate and the use cases stay thin.
**Repository:** `DocumentRepository`, `DocumentStatementRepository`
**Schemas:** `DocumentCreate`, `DocumentRead`, `DocumentUpdate`, `DocumentWithStatementsRead`, `DocumentFilter`, `DocumentStatementCreate`, `DocumentStatementRead`

**Authorization:** Campaign owner, enforced by the `CurrentCampaign` dependency before any use case runs. The campaign is taken from the repository scope, never from the request body. `DocumentCreate` and `DocumentUpdate` use `extra="forbid"`, so a body carrying `campaign_id` is rejected with a 422 rather than silently ignored.

#### Decisions

**A document and a statement hold different things, and neither is derived from the other.** `Document.content` is the verbatim text the fact chain points back to. `DocumentStatement.content` is one ordered anchor inside it. They are stored and updated independently and never synchronised, because the statements are the curated, reorderable, position-bearing view that extraction and citation depend on, and rewriting them from the document would discard the curation.

**Tied positions are allowed, so the tiebreak is fixed.** `position` has no uniqueness constraint. Ordering is `(position, created_at, id)` in both the `Document.statements` relationship and `DocumentStatementRepository.get_by_document`, so a tie can never reorder between two reads, and the constant is asserted against the relationship so the two cannot drift apart.

**Statements are scoped through their parent, because they have no `campaign_id`.** The base campaign scope is a no-op for a table without that column, so every scoped statement read joins `documents` and filters `documents.campaign_id`. The join condition also requires `documents.deleted_at IS NULL`, so a statement under a soft-deleted document is not reachable by id. Putting that predicate in the join rather than a `where` matters: a `where` on the right table of an inner join would let those rows back in.

**Deleting a document stamps its statements in the same flush.** `soft_delete_with_statements` writes one timestamp to the document and to its loaded live statements and flushes once, so a cascade cannot be half-applied. Rows are retained rather than removed, because facts point at them.

**`document_type` and `source_type` stay free text.** They are `min_length=1` strings with no enum, because neither has a settled vocabulary, and inventing one now would put a migration in front of the first real corpus.

**Notes:**
- `Document.statements` is `viewonly=True` with `lazy="raise_on_sql"`. P1C.2 owns statement writes; a view-only relationship cannot be used to smuggle them in through the document.
- Listing returns a total, and the page and the total are built from one shared predicate, so `total` always equals the number of rows a client can page through.
- PATCH only touches fields the caller sent. An absent field is left alone, never blanked.
- `session_id` is validated against a campaign-scoped `SessionRepository` on create and on update, so a session from another campaign or a deleted one is refused with a generic 422. The message does not distinguish the two.

**Tests:** 62 tests across `tests/api/test_documents.py` and `tests/repositories/test_document_repo.py`, covering CRUD, 422 mapping, extra-field rejection, campaign scoping asserted against compiled SQL, page/total predicate agreement, deterministic ordering, the cascade, and retained history.

**Verified manually against the development database:** create, read with statements, filter by type and session, cross-campaign session refusal, cross-campaign read 404, patch, soft delete, and statement cascade. This surfaced a defect the mocked tests could not: the scoped statement join documented above did not actually exclude statements belonging to a soft-deleted document, because the deletion predicate was missing from the join condition. It is fixed and covered.

---

### P1C.2 — Document Statement API

**Status:** `Planning`

**Goal:** Atomic statement management within documents.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/documents/{document_id}/statements` | Create statement (position, content) |
| GET | `/api/campaigns/{campaign_id}/documents/{document_id}/statements` | List statements (ordered by position) |
| PATCH | `/api/campaigns/{campaign_id}/documents/{document_id}/statements/{statement_id}` | Update statement |
| DELETE | `/api/campaigns/{campaign_id}/documents/{document_id}/statements/{statement_id}` | Soft delete statement |

**Note:** Statements are the provenance anchors for facts. Position enables ordered reconstruction.

**Tests:** Position ordering; cascade soft delete with document.

---

## Phase 1D — Fact & Event APIs

### P1D.1 — Entity Fact CRUD API

**Status:** `Complete`

**Goal:** Manage atomic claims about single entities.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entities/{entity_id}/facts` | Create fact (fact_type, content, confidence, importance, optional statement_id, event_id) |
| GET | `/api/campaigns/{campaign_id}/entities/{entity_id}/facts` | List facts (filter by status, fact_type, event_id) |
| GET | `/api/campaigns/{campaign_id}/entities/{entity_id}/facts/{fact_id}` | Get fact with audiences |
| PATCH | `/api/campaigns/{campaign_id}/entities/{entity_id}/facts/{fact_id}` | Update fact (content, confidence, importance, status) |
| DELETE | `/api/campaigns/{campaign_id}/entities/{entity_id}/facts/{fact_id}` | Soft delete fact |

**Audience Sub-resource:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entities/{entity_id}/facts/{fact_id}/audiences` | Add audience rule |
| DELETE | `/api/campaigns/{campaign_id}/entities/{entity_id}/facts/{fact_id}/audiences/{audience_id}` | Remove audience rule |

**Application:** `app/application/facts/facts.py` — function-level use cases
(`create_fact`, `get_fact`, `list_facts`, `update_fact`, `delete_fact`,
`add_audience`, `remove_audience`). No `FactService` class: the operations are
single-purpose and share no state, so a class would be a namespace with an
`__init__`. This matches the entity and document phases.

**Repository:** `FactRepository`; audience rules via `FactAudienceRepository`
and, for P1D.2, `RelationshipFactAudienceRepository`. There is **no** visibility
filter — see ADR-025. The phase plan previously credited this repository with a
"visibility filter from PrePhase1" that never existed and that the docstrings
falsely claimed. Corrected here rather than left as a standing inaccuracy.

**Schemas:** `EntityFactCreate`, `EntityFactRead`, `EntityFactUpdate`,
`EntityFactList`, `EntityFactWithAudiencesRead`, `FactAudienceCreate`,
`FactAudienceRead`.

**Validation:** `confidence` 0-1, `importance` >= 0, `status` enum, `fact_type`
free text (convention: "physical_trait", "personality", "history", etc.). All
fact and audience schemas forbid extra fields.

**Tests:** Provenance chain (fact → statement → document); the fact belongs to
the entity named in the path; provenance is immutable; audience pairing; status
movement; campaign scoping of the audience tables through the parent fact.

**Decisions taken here:**

- **`entity_id` in the path owns the fact.** The item routes resolve the fact
  within the campaign and then check it belongs to that entity. Without the
  check, `/entities/A/facts/F` would read, edit, and delete a fact belonging to
  entity B, which contradicts what the path claims. `remove_alias` in P1B
  already does this.
- **Provenance is immutable after creation.** `entity_id`, `fact_type`,
  `statement_id`, and `event_id` are rejected by `EntityFactUpdate` and are
  absent from `FactRepository.UPDATABLE_FIELDS`. The schema is the first lock
  and the repository allow-list the second: a fact's history should not be
  rewritable by whichever caller reaches the repository. Status, content,
  confidence, and importance are mutable.
- **Status moves freely** between `active`, `invalidated`, and `superseded`.
  P1D.5 owns the meaningful transitions, including setting `superseded_by`.
  The enum is a regex pattern rather than a `StrEnum` here because ADR-011
  already accepts Python-side validation, and the plan does not commit to one
  representation.
- **`audience_type` and `player_id` are paired** by a schema validator: `player`
  requires `player_id`, and no other type accepts it. A `player_id` is also
  resolved through the campaign-scoped `PlayerRepository` on write, so it names
  a live player rather than any uuid. Without that, a rule could name an entity
  of another campaign, a deleted player, or an item, and sit in the table
  looking valid while matching nobody.
- **The page and the total share one predicate** (`_filtered_stmt`), so the
  total always equals the rows a client can page through. Ordering is
  `(created_at, id)`; a tie on the timestamp would otherwise let a row repeat or
  vanish between pages.
- **Audiences load as `viewonly` relationships** with `lazy="raise_on_sql"`, so
  a caller cannot write a rule by appending to a collection. Audience writes go
  through the audience repository explicitly.

---

### P1D.2 — Entity Relationship Fact CRUD API

**Status:** `Planning`

**Goal:** Manage atomic relationship claims between two entities.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/relationship-facts` | Create relationship fact (source_entity_id, target_entity_id, relationship_type, content, confidence, importance, optional statement_id, event_id) |
| GET | `/api/campaigns/{campaign_id}/relationship-facts` | List relationship facts (filter by source, target, type, status) |
| GET | `/api/campaigns/{campaign_id}/relationship-facts/{fact_id}` | Get relationship fact with audiences |
| PATCH | `/api/campaigns/{campaign_id}/relationship-facts/{fact_id}` | Update relationship fact |
| DELETE | `/api/campaigns/{campaign_id}/relationship-facts/{fact_id}` | Soft delete relationship fact |

**Audience Sub-resource:** Same pattern as entity facts.

**Service:** `RelationshipFactService`
**Repository:** `RelationshipFactRepository`
**Schemas:** `EntityRelationshipFactCreate`, `EntityRelationshipFactRead`, `EntityRelationshipFactUpdate`, `RelationshipFactAudienceCreate/Read`

**Validation:** Source and target must be in same campaign; not same entity; `relationship_type` free text (convention: "owns", "knows", "serves", "parent_of", etc.)

**Tests:** Cross-campaign prevention; self-reference prevention; provenance; visibility.

---

### P1D.3 — Materialized Relationship API (Read-Only)

**Status:** `Planning`

**Goal:** Query current relationships materialized from active relationship facts.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/campaigns/{campaign_id}/relationships` | List current relationships (filter by source, target, type) |
| GET | `/api/campaigns/{campaign_id}/relationships/{relationship_id}` | Get relationship with supporting fact |

**Note:** No write endpoints. `EntityRelationship` is maintained by application logic when relationship facts change status (see P1D.5).

**Service:** `RelationshipService`
**Repository:** `RelationshipRepository`
**Schemas:** `EntityRelationshipRead`

**Tests:** Only active facts produce relationships; deleted/invalidated facts excluded.

---

### P1D.4 — Event CRUD API

**Status:** `Planning`

**Goal:** Manage event groupings.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/events` | Create event (title, description, occurred_at, game_time) |
| GET | `/api/campaigns/{campaign_id}/events` | List events (filter by status, date range) |
| GET | `/api/campaigns/{campaign_id}/events/{event_id}` | Get event with constituent facts |
| PATCH | `/api/campaigns/{campaign_id}/events/{event_id}` | Update event |
| DELETE | `/api/campaigns/{campaign_id}/events/{event_id}` | Soft delete event |

**Service:** `EventService`
**Repository:** `EventRepository`
**Schemas:** `EventCreate`, `EventRead`, `EventUpdate`, `EventList`

**Tests:** Event + fact association; game_time free text; campaign isolation.

---

### P1D.5 — Relationship Materialization Service

**Status:** `Planning`

**Goal:** Keep `EntityRelationship` table in sync with active `EntityRelationshipFact` records.

**Trigger Points:**
- Relationship fact created with status="active" → create materialized relationship
- Relationship fact status changed to "active" → create/update materialized
- Relationship fact status changed to "invalidated"/"superseded" OR deleted → remove materialized
- Relationship fact deleted → remove materialized

**Implementation:** Domain event handlers in `app/application/relationships/relationship_sync.py` called from `RelationshipFactService` methods.

**Tests:** Sync correctness for all status transitions; idempotency; race condition handling (DB constraints).

---

## Phase 1E — Entity Recognition (Deterministic)

### P1E.1 — Entity Matcher Implementation

**Status:** `Complete`

**Goal:** Implement `EntityMatcher.find_candidates(text)` with deterministic pipeline.

**Pipeline (per ADR-008):**
1. Exact entity name match (case-sensitive)
2. Exact alias match (case-sensitive)
3. Case-insensitive name match
4. Case-insensitive alias match
5. Fuzzy match (Levenshtein distance <= 2, configurable)
6. Return `EntityCandidate` list sorted by confidence

**Files:**
- `app/application/entities/entity_matching.py` — Replace stub with implementation
- `app/application/entities/matching_pipeline.py` — Pipeline steps as composable functions

**Confidence Scoring:**
- Exact name: 1.0
- Exact alias: 0.95
- Case-insensitive name: 0.9
- Case-insensitive alias: 0.85
- Fuzzy: 0.7 - 0.8 based on distance

**Repository Dependency:** `EntityRepository.list_match_terms()` returns one term per name and one per alias, as plain values rather than `Entity` rows. The matcher compares strings and ids, so loading descriptions, timestamps, and specializations on every transcript message would be cost for columns it never reads.

That method runs **two** scoped projections, not one outer join. A join returns one row per (entity, alias) pair, so an entity *with* an alias contributes only the alias and never its own name — the more aliases an entity had, the less findable it became. This was built, verified wrong against real data, and fixed; the regression test is `test_an_entity_always_contributes_its_own_name`.

**Decisions taken here:**

- **Candidates come from tokens, not from substring search.** The text is
  tokenized and every run of 1..N tokens is looked up in the vocabulary. That
  is what stops a name from matching inside a longer word: "Ann" is never a
  candidate inside "Anne". The cost is that both sides normalize the same way,
  which is why a name with punctuation ("O'Brien") still matches itself.
- **Fuzzy has a length floor, applied to the *stored term* and not just the
  word in the text.** Checking only the text would still let a three-letter
  name sit within distance 1 of any four-letter word, so "Anne" would match a
  character named "Ann". Two short names also sit within distance 2 of each
  other, which is what the floor exists to prevent.
- **One candidate per entity.** A name mentioned three times in a transcript is
  one thing the text is about. The strongest tier wins, and a tie on confidence
  keeps the earlier mention, so `matched_text` is the first place the name was
  used.
- **A name beats an alias at the same tier or distance.** The name is the
  entity's primary identifier. Within the winning tier every entity survives, so
  two entities sharing a name both come back — nothing in the schema forbids
  it, and reporting one of them would silently drop a real entity.
- **Longest match wins, and a match consumes its tokens.** "Old Man" is not
  also reported as "Old" followed by "Man".
- **No new dependency.** Levenshtein is a short two-row DP with an early exit,
  rather than a package, for one bounded comparison.
- **No `EntityRecognitionService`.** It would hold no state and forward one
  call. Same reasoning as dropping `FactService` for P1D.1.

**Tests:** 56 pipeline unit tests (each tier in isolation, plus no-substring,
overlap, phrase, Unicode, blank-term, and determinism cases), 17 matcher tests
(per-entity collapse, shared names, settings, empty input), 6 delete-index
equivalence tests against a brute-force reference scan, and 6 latency budgets.

**Performance (see ADR-026):** The first version compared every word against
every term in the campaign. At 1,000 entities with ten aliases each — 11,000
terms — that was 1,114 ms per transcript, and no functional test noticed,
because a slow matcher returns the right answers too.

Two fixes, which only pay off together:

- **A delete index** replaces the scan. Each term is indexed under every
  string reachable by deleting up to `MAX_FUZZY_DISTANCE` characters; a query
  generates the same set from the word in the text. It is a *superset* filter,
  so it cannot miss a real match, and every candidate is still confirmed with a
  real edit distance — it narrows the work, it does not decide the answer.
- **A bounded per-campaign vocabulary cache** removes the query and the index
  build from all but the first call.

Measured, same 54-word transcript:

| entities | terms | before | after (warm) | speedup |
|---|---|---|---|---|
| 100 | 1,100 | 119 ms | 5.9 ms | 20x |
| 1,000 | 11,000 | 1,114 ms | 9.5 ms | 118x |
| 10,000 | 110,000 | 11,404 ms | 45 ms | 251x |

The first call for a campaign still pays ~225 ms to build the vocabulary and
index at 11k terms. That is a cache miss, and it is why the two fixes ship as a
pair: measured alone, the index is *slower* than the scan for a single call at
every size tested, and breaks even after about two calls.

`tests/performance/test_matching_performance.py` asserts both a ratio against
a scan measured on the same machine (immune to hardware speed) and a generous
absolute ceiling, because a wall-clock number alone is a flaky test and a
correct-but-slow matcher passes every other assertion in the suite.

**Edge case the unit tests could not have caught:** the vocabulary query was
correct against mocked rows and wrong against the database. Mocking the
repository bypassed the row-to-term mapping entirely, so the join's real shape
was never exercised until a live probe with an entity that had an alias.

---

### P1E.2 — Entity Recognition API

**Status:** `Complete`

**Goal:** Expose entity matching as a service endpoint.

**Endpoint:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entity-recognition` | Input: `{text: string}` → Output: `{candidates: EntityCandidate[]}` |

**Files:**
- `app/schemas/recognition.py` — request, candidate, and response models
- `app/api/http/routes/entity_recognition.py` — the endpoint
- `app/main.py` — router registration

**No service layer.** The route builds a campaign-scoped `EntityRepository` and
calls `EntityMatcher` directly. An `EntityRecognitionService` would hold no
state and forward exactly one call.

**Request rules:** `text` is stripped and must be non-empty, `max_length=10000`,
`extra="forbid"`. A blank transcript is a client mistake worth a 422, not an
empty result set that hides it.

**Authorization:** Campaign owner, via the shared `require_campaign_access`
dependency. Any authenticated owner may recognize text; no ownership filter is
applied, because the vocabulary is built from every entity in the campaign.

**Tests:** 12 API tests covering response shape, confidence ordering,
validation (blank text, too long, unknown field), the repository being
constructed with the request's campaign id, and byte-identical output across
repeated calls.

**Verified against a live database,** not only against mocked repositories. The
probe covered each confidence tier, a fuzzy typo, multiple mentions of one name,
a transcript matching nothing, and cleanup of its own rows. That probe is what
found the vocabulary defect described in P1E.1 — mocked repository tests could
not have caught it.

---

## Phase 1F — Realtime WebSocket Protocol

### P1F.1 — Authenticated WebSocket Endpoint

**Status:** `Planning`

**Goal:** Upgrade WebSocket to require campaign scope.

**Changes to `app/api/websocket/routes/stream.py`:**
- [x] Extract token from query string: `/ws/stream?token=<jwt>`
- [x] Validate via `AuthProvider` (rejects with close code 4001)
- [ ] Add `campaign_id` to the query string and verify campaign access
- [ ] Inject `campaign_id` and `user` into connection state

**Message Protocol (v1):**
```json
// Client → Server
{"type": "transcript", "text": "You approach LarkFellow.", "speaker": "dm"}

// Server → Client
{"type": "transcript_ack", "transcript": "...", "matches": [{"entity_id": "...", "name": "LarkFellow", "matched_text": "LarkFellow", "confidence": 0.95}]}
{"type": "context_card", "entity_id": "...", "entity_type": "location", "summary": "LarkFellow is a coastal town...", "facts": [...], "relationships": [...]}
```

**Tests:** Auth rejection; campaign scope enforcement; message echo with matches.

---

### P1F.2 — Transcript → Entity Match → Context Card Pipeline

**Status:** `Planning`

**Goal:** Connect WebSocket transcript to entity matcher and return context cards.

**Flow:**
1. Receive transcript message
2. Call `EntityMatcher.find_candidates(transcript)`
3. For each candidate, fetch entity + active facts + active relationships (via repositories with visibility filter)
4. Construct context card per entity
5. Send `transcript_ack` with matches + context cards

**Files:**
- `app/api/websocket/routes/stream.py` — Implement pipeline
- `app/application/realtime/realtime_service.py` — Business logic for context assembly

**Context Card Content:**
- Entity base info (name, type, description)
- Specialized data (actor voice, location atmosphere, etc.)
- Active facts (filtered by visibility for connected user)
- Active relationships (filtered)
- Recent events involving entity

**Tests:** End-to-end WebSocket test with seeded campaign data; visibility filtering; multiple matches.

---

## Phase 1 Exit Criteria

All Phase 1 steps `Completed`:
- [ ] Campaign & Session CRUD APIs with auth/isolation
- [ ] Entity + Specialized Entity + Alias CRUD APIs
- [ ] Document + Statement CRUD APIs
- [ ] Entity Fact + Relationship Fact + Audience CRUD APIs
- [ ] Materialized Relationship read API + sync service
- [ ] Event CRUD API
- [ ] Deterministic entity matcher implementation
- [ ] Entity recognition API
- [ ] Authenticated WebSocket with transcript → context pipeline
- [ ] Developer test console functional for all APIs + WebSocket
- [ ] All tests pass (unit + integration)
- [ ] Ruff + mypy clean
- [ ] Alembic migration history clean

**Next:** Phase 2 — Knowledge Ingestion (document parsing, extraction interfaces, review workflow)
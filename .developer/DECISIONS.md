# Architecture Decisions

## ADR-001: Python/FastAPI backend

**Decision:** Use Python with FastAPI.

**Reason:** The application needs asynchronous HTTP/WebSocket handling while
also integrating with Python's AI, NLP, and audio ecosystem.

## ADR-002: PostgreSQL plus pgvector

**Decision:** Use PostgreSQL as the persistence system and pgvector for future
embeddings.

**Reason:** Relational integrity is more important than introducing a separate
vector or graph system during the initial product stage.

## ADR-003: Domain model over RAG

**Decision:** Structured entities, facts, relationships, events, and provenance
are authoritative. RAG augments retrieval.

**Reason:** The application must support editing, contradiction handling,
visibility, and future state changes that require deterministic persistence.

## ADR-004: Entity plus specialized tables

**Decision:** Use a durable Entity identity with small specialized tables for
Actor, Player, PlayerCharacter, Location, Item, and Faction.

**Structure:** Each specialized table keys on `entity_id` as both primary key
and foreign key to `entities.id`, making it a strict one-to-one extension
rather than table-per-class inheritance. Stable canonical identity fields stay
on `entities` so the engine can always resolve and name a thing; everything
else is separated because it changes as the story develops and belongs in
campaign history instead of the stable core.

**Consequences:**
- Exactly one specialization table exists per `entity_type`, so the
  specialization is mandatory rather than optional. An entity is created
  first and its specialization second, which makes an entity without its
  specialization row a normal transient state: the base read succeeds and the
  type endpoint returns 404.
- Specialized rows are addressed by the same UUID as their entity, so API
  endpoints are flat sub-resources per type (`/actors/{id}`) rather than
  nested under the entity.
- Specialized read schemas expose `entity_id` and embed the base entity, so a
  list endpoint is usable in one request. See ADR-021.
- Schema base classes stay narrow: a shared `EntityKeyMixin` carries only
  `entity_id`. The models already inherit `TimestampMixin` for
  `created_at`/`updated_at`/`deleted_at`, and duplicating `created_at` on the
  wire would put two near-identical timestamps that disagree by a few
  milliseconds in front of client-side sorting.

**Reason:** Stable canonical fields remain easy to edit while evolving knowledge
lives in facts.

## ADR-005: Facts are provenance-bearing claims

**Decision:** Store atomic EntityFacts and EntityRelationshipFacts with source
statements, confidence, importance, and status.

**Reason:** AI extraction is fallible and campaign lore can be retconned.

## ADR-006: Events group facts

**Decision:** Events contain facts rather than directly linking to documents or
entities.

**Reason:** A single occurrence can involve many entities and relationships
without requiring a fixed number of entity columns.

## ADR-007: OIDC instead of custom authentication

**Decision:** Delegate authentication to an OIDC provider and map the stable
provider subject to an internal User.

**Reason:** Passwords, credential recovery, and MFA are security-sensitive
infrastructure that the application does not need to own.

## ADR-008: Deterministic-first entity detection

**Decision:** Try exact and fuzzy matching before semantic/vector/LLM matching.

**Reason:** Names and aliases are usually easier and cheaper to match
reliably than asking an LLM to rediscover known identities.

## ADR-009: Model module organization

**Decision:** Split the consolidated `app/models/domain.py` into cohesive modules
by domain concept rather than keeping all models in one file or creating
one file per model.

**Modules:**
```
app/models/
├── __init__.py              # Re-export all models
├── user.py                  # User + administrative settings (OAuth, future username/password, app settings)
├── campaign.py              # Campaign, CampaignMember, Session
├── entity/
│   ├── __init__.py          # Re-export entity types
│   ├── entity.py            # Entity, EntityAlias
│   └── entity_types/
│       ├── __init__.py
│       ├── actor.py
│       ├── player.py
│       ├── player_character.py
│       ├── location.py
│       ├── item.py
│       └── faction.py
├── document.py              # Document, DocumentStatement
├── fact.py                  # EntityFact, EntityRelationshipFact
├── relationship.py          # EntityRelationship
├── event.py                 # Event
└── audience.py              # EntityFactAudience, EntityRelationshipFactAudience
```

**Reason:** The current 394-line single file violates "small, cohesive modules" standard,
creates circular import risk, and obscures domain boundaries. User administration
is separated from campaign data. Entity types are granular to allow independent
evolution of specialized entity logic while keeping the core Entity/EntityAlias
together as the identity foundation.

**Status:** Approved — implement as PrePhase1 first step.

## ADR-010: Foreign key delete behavior for provenance preservation

**Decision:** Use `ondelete="RESTRICT"` on all foreign keys from fact/relationship/event
tables to `campaigns` and `entities` tables.

**Affected FKs:**
- `entity_facts.campaign_id`, `entity_facts.entity_id`, `entity_facts.event_id`
- `entity_relationship_facts.campaign_id`, `entity_relationship_facts.source_entity_id`,
  `entity_relationship_facts.target_entity_id`, `entity_relationship_facts.event_id`
- `entity_relationships.campaign_id`, `entity_relationships.source_entity_id`,
  `entity_relationships.target_entity_id`
- `events.campaign_id`
- `documents.campaign_id`, `documents.session_id`
- `campaigns.user_id`, `sessions.campaign_id`, `entities.campaign_id`

**Reason:** Soft deletion via `deleted_at` is the intended removal mechanism.
Cascade deletes would destroy provenance history when a campaign or entity is
soft-deleted, violating "Preserve invalidated information for retcons" and
"Provenance First" principles.

**Status:** Approved — implement via migration in PrePhase1.

## ADR-011: CHECK constraints for enum-like columns

**Decision:** Defer database-level CHECK constraints for `confidence`, `importance`,
`status`, `entity_type`, `audience_type` to Phase 2. Use Python enums and
Pydantic validation at the application layer for Phase 1.

**Reason:** Enum values are still evolving during initial extraction pipeline
development. Database enum migrations are painful to change. Application-level
validation provides sufficient integrity for Phase 1 while keeping schema
flexible.

**Status:** Approved.

## ADR-012: Session numbering

**Decision:** Keep `session_number` as nullable with unique index (allowing multiple
NULLs per PostgreSQL behavior). Do not impose numbering or add partial index
in Phase 1.

**Reason:** KISS. New users may bulk-import historical sessions without
numbering. Numbering can be added later when a concrete requirement emerges.

**Status:** Approved.

## ADR-013: OIDC provider for local development

**Decision:** Use a mock/stub OIDC provider implementation (`app/integrations/auth.py`)
for local development and testing. Document real provider setup (Keycloak,
Auth0, etc.) in README for production deployment.

**Reason:** Avoids infrastructure overhead during development. The stub implements
the same interface for seamless transition to a real provider.

**Status:** Approved.

## ADR-014: WebSocket authentication (Phase 1)

**Decision:** Accept token in query string (`/ws/stream?token=<jwt>`) for Phase 1
WebSocket authentication. This is a temporary measure; Phase 2+ will use
a more secure mechanism (subprotocol, cookie, or signed URL).

**Reason:** Simplest implementation for Phase 1 demo. Query string tokens
are logged in access logs and browser history — not acceptable for production
but acceptable for local development with the stub provider.

**Status:** Approved — temporary.

## ADR-015: API route organization

**Decision:** Organize transport adapters under `app/api/` with protocol-specific
subdirectories, separating HTTP/REST from WebSocket.

**Structure:**
```
app/api/
├── __init__.py
├── dependencies.py          # Shared FastAPI dependencies (auth, campaign scope, repos)
├── security.py              # JWT validation, auth helpers
├── http/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── campaigns.py
│   │   ├── sessions.py
│   │   ├── entities.py
│   │   ├── documents.py
│   │   ├── facts.py
│   │   ├── relationships.py
│   │   └── events.py
│   └── schemas/             # Re-export from app.schemas for convenience (optional)
└── websocket/
    ├── __init__.py
    ├── routes/
    │   ├── __init__.py
    │   └── stream.py        # WebSocket endpoint + message handlers
    └── handlers/
        ├── __init__.py
        └── transcript.py    # Transcript → entity match → context card logic
```

**Principles:**
- `app/api/http/` and `app/api/websocket/` are **transport adapters only** — thin handlers
- Business logic lives in `app/services/`
- Data access lives in `app/repositories/`
- Shared dependencies (auth, campaign scope, repository injection) in `app/api/dependencies.py`
- Route modules are registered in `app/api/http/routes/__init__.py` and `app/api/websocket/routes/__init__.py`
- `app/main.py` includes routers from `app.api.http` and `app.api.websocket`

**Reason:** Establishes clear separation of concerns early. HTTP and WebSocket are different
protocols with different concerns (request/response vs streaming), but share auth,
campaign scope, and repository dependencies. This structure scales cleanly as
endpoints grow and prevents transport logic from leaking into services.

**Status:** Approved — implement as PrePhase1 step.

## ADR-016: Explicit application layer

**Decision:** Introduce an explicit `app/application/` layer for use-case orchestration,
separate from `app/api/` (transport), `app/repositories/` (persistence), and
`app/integrations/` (external providers).

**Structure:**
```
app/application/
├── exceptions/
├── users/           # resolve_current_user
├── campaigns/       # get_current_campaign
├── documents/       # ingest_document
├── entities/        # create_entity, entity_matching
├── facts/           # create_fact, invalidate_fact
└── realtime/        # process_transcript
```

**Principles:**
- Application services are use-case oriented, not model-oriented.
- No service class per database model.
- Application services coordinate repositories and integrations.
- Application services must not depend on FastAPI, WebSocket, or HTTP types.
- Repositories handle persistence; application services handle workflows.
- No formal Domain layer without demonstrated need.

**Reason:** Bard has operations involving multiple repositories and/or external
integrations (document ingestion, transcript processing, fact extraction).
These workflows should not live in HTTP/WebSocket handlers. An explicit
application layer provides transport independence, testability, and clear
orchestration ownership.

**Status:** Approved — implement as PrePhase1 step (PP1.7).

## ADR-017: Authentication as FastAPI dependency

**Decision:** Implement authentication as FastAPI dependencies (`Depends(get_current_user)`)
rather than global middleware.

**Flow:**
```
Request
    ↓
Depends(get_current_identity)  → AuthProvider.validate_token()
    ↓
AuthenticatedIdentity
    ↓
Depends(get_current_user)      → UserRepository + resolve_current_user()
    ↓
Local User
```

**Reasons:**
- Public endpoints (`/health`) should not require authentication.
- Authentication requirements are endpoint-specific.
- Dependencies compose naturally with campaign scope (`Depends(get_current_campaign)`).
- Explicit endpoint requirements improve readability and testing.
- Middleware would run on all routes including public endpoints.

**Status:** Approved — implement as PrePhase1 step (PP1.7).

## ADR-018: Campaign scope (Phase 1 = owner only)

**Decision:** Phase 1 campaign access is owner-only. `CampaignMember` table exists
but is not enforced for authorization.

**Phase 1 flow:**
```
get_current_user
    ↓
get_current_campaign(campaign_id, user_id) → CampaignRepository
    ↓
if campaign missing OR campaign.user_id != user_id: 404 Not Found
```

A campaign owned by someone else returns the same 404, with the same body, as a
campaign that does not exist. A 403 would confirm the identifier is real, which
lets any authenticated user enumerate campaign ids. There is nothing to protect
by distinguishing them, because the non-owner's request fails either way. This
matches the rule P1B.2 applies to entities and specializations, so ownership
is checked the same way at both levels of the API.

**Phase 2+ (deferred):**
- `CampaignMember` authorization with roles (`dm`, `player`, `viewer`).
- Membership-based access replaces owner-only check.

`ForbiddenError` is retained in the error hierarchy but is not raised for
ownership. It is reserved for refusing an action on a resource the caller can
already see — a viewer attempting to edit a session, for example. Ownership
itself stays a 404 so that existence cannot be probed; the moment ownership
becomes a 403, the oracle returns. This is the one distinction to preserve when
membership roles land.

**Reason:** Phase 1 focuses on single-owner campaigns. The `CampaignMember`
schema exists for future sharing but enforcement is deferred until a
concrete sharing requirement exists.

**Status:** Approved — implement as PrePhase1 step (PP1.7).

## ADR-019: Realtime transport vs application behavior

**Decision:** Separate WebSocket transport (`app/api/websocket/`) from realtime
application behavior (`app/application/realtime/`).

**Structure:**
```
app/
├── api/
│   └── websocket/
│       ├── routes/stream.py      # WebSocket transport, message framing
│       └── handlers/transcript.py
└── application/
    └── realtime/
        └── process_transcript.py # Transcript → entity match → context cards
```

**Reason:** WebSocket is a transport mechanism. The realtime application
logic (entity matching, knowledge retrieval, visibility filtering) should
be transport-independent and reusable from HTTP endpoints or background jobs.

**Status:** Approved — implement as PrePhase1 step (PP1.7).
## ADR-020: entity_type is an immutable six-value enum

**Decision:** `EntityType` is a `StrEnum` with exactly six values: `actor`,
`player`, `player_character`, `location`, `item`, `faction`. An NPC is an
`actor`; there is no separate `npc` type. Once created, `entity_type` cannot
be changed — a `PATCH` that sets it is rejected with 422 rather than silently
ignored.

**Enforcement:** Python enum plus Pydantic validation, per ADR-011. The
database column stays `varchar(50)` with no CHECK constraint until Phase 2.

**Consequences:**
- Every valid `entity_type` maps to exactly one specialization table, so a
  specialized repository asserts the type on every access instead of relying
  on presence of a row. A location entity can never share an id with an actor
  because `entity_id` is the specialization's primary key, so the check is
  belt-and-braces — but it makes the rejection deliberate and prevents a stale
  row surviving a future type change.
- Converting an actor into a location means deleting and recreating the
  entity. This is accepted because the alternative, a type change that leaves
  a specialization row attached to the wrong table, is a silent data
  corruption.

**Reason:** The type drives which specialization applies, which validation
runs, and which endpoint reads it. Letting it drift would let an entity hold a
specialization its type does not describe.

**Status:** Approved — implement as Phase 1B.2.

## ADR-021: Specialized data inherits campaign scope from Entity

**Decision:** The six specialized tables do not carry `campaign_id` and never
will. `Entity` gains real ORM relationships for every child table, and a
specialized read or write always resolves the parent `Entity` through the
campaign-scoped `EntityRepository` first. Loads use `selectinload`; each
one-to-one specialization relationship is declared `uselist=False` and filters
`deleted_at IS NULL` in its `primaryjoin`.

**Structure:**
```
ActorRepository.get(entity_id)
    ↓
EntityRepository(session, campaign_id)          # campaign scope applied here
    ↓
select(Entity).where(id, campaign_id, deleted_at IS NULL)
               .options(selectinload(Entity.actor))
    ↓
entity is None          → 404    (wrong campaign, or gone)
entity.entity_type wrong → 404   (deliberate, see ADR-020)
entity.actor is None    → 404    (entity exists, specialization does not yet)
```

**Consequences:**
- Campaign isolation is defined once, on the entity, instead of being
  reimplemented across six tables that have no such column.
- Soft-deleted specializations are invisible through the relationship, because
  `TimestampMixin` puts `deleted_at` on those models and a plain relationship
  would otherwise return a deleted row as though it were live. This matches the
  retention rule already applied to entity and alias reads.
- Soft-deleting an entity stamps its specialization in the same transaction.
  Without it a deleted entity leaves a live-looking specialization row. It is
  unreachable through the API because every read is entity-scoped, but it is
  inconsistent state.
- `EntityKeyMixin` carries only `entity_id`; it is not widened to include `id`
  or timestamps, because the models already inherit `TimestampMixin` and a
  second `created_at` would give client-side sorting two values that disagree.
- `Entity.aliases` is added alongside the specializations. The explicit alias
  join is retained regardless, because a relationship can load rows but cannot
  filter a query, and alias search needs both.

**Reason:** Duplicating campaign predicates across six child tables is how
cross-campaign leakage happens, and each copy is a place to forget one. The
foreign keys all run child to `entities.id`, so there is no cycle to design
around and no reason to carry a second scope.

**Status:** Approved — implement as Phase 1B.2.

---

## ADR-022: Soft-delete filtering is enforced by BaseRepository, not per repository

**Context:** ADR-010 keeps soft-deleted rows in the table so history survives a
retcon. DATABASE.md states the resulting rule: "Soft-deleted records are
excluded from normal active queries."

The rule was not implemented anywhere. `BaseRepository.get`, `list`, `count`,
and `exists` applied campaign scoping but never a `deleted_at` predicate, and
only `EntityRepository` compensated with a private `_active_scope`. Every other
table leaked deleted rows. Verified against the live database before the fix:

```text
SOFT-DELETED campaign resolves as current : 'Deleted' (deleted_at=True)
soft-deleted docs in list()               : 1 ['ghost']
soft-deleted docs in count()              : 1
soft-deleted doc from get()               : ghost
```

A soft-deleted campaign was still accepted as `CurrentCampaign` and remained
fully usable, and a soft-deleted document was still returned by the repository
whose contract promised to remove it. The compensating filter in
`EntityRepository` was also the more dangerous shape: it made the rule
opt-in, so a soft delete on any other table was a silent no-op rather than an
error.

**Decision:** `_active_scope` moves to `BaseRepository` and is applied in
`get`, `list`, `count`, and `exists`. Every table inherits `deleted_at` from
`TimestampMixin`, so the filter is unconditional and the per-repository copies
are deleted.

Campaign scoping and deletion filtering are kept as separate methods because
they answer different questions and only one of them is optional. `_campaign_scope`
is a silent no-op when a model has no `campaign_id` column, which is how
`document_statements` and `entity_aliases` inherit isolation through a parent.
Those tables are therefore protected by the deletion filter alone, and the
tests assert both properties for exactly those repositories.

Moving the filter to the base class is necessary but not sufficient. A
subclass that writes its own `select()` never passes through `get`/`list`, so
the filter has to be repeated at every hand-written query — and it was missing
from 36 of them. `UserRepository.get_by_auth` was one, which is the
authentication path: a soft-deleted account could still sign in. SQLAlchemy
offers no hook to apply a predicate automatically, so this cannot be made
structural at the framework level.

`tests/repositories/test_no_undeleted_reads.py` therefore asserts the property
by walking the repository package and checking that every public method which
builds its own `select()` filters `deleted_at`, directly or by delegating to a
helper that does. A new read method cannot be added without deciding whether it
filters, and the walk asserts it found a plausible number of methods so it
cannot pass by matching nothing.

Both scope helpers are generic in the select type so wrapping a query does not
erase the row-type inference `AsyncSession.execute()` would otherwise give the
caller. Without that, every wrapped query needed a `cast` at the return
statement, which is the noise that made these methods look unwritten.

`soft_delete` and `update` inherit the behaviour through `get`: deleting or
editing an already-deleted row reports failure instead of re-stamping
`deleted_at` or writing through it.

**Consequences:**
- The DATABASE.md invariant becomes true by construction rather than by
  remembering to add a filter. A new repository cannot get this wrong.
- Reading history for retcons now needs a deliberate opt-out rather than the
  default. Any future "show deleted" query has to bypass `_active_scope`
  explicitly, which makes retention an intentional act instead of an accident.
- This changes behaviour for users, campaigns, sessions, events, facts,
  relationships, and audiences, which all returned deleted rows before. The
  fix is the point, but it is a wider blast radius than documents alone, so it
  is committed separately from P1C.1.
- Fact provenance that points at a soft-deleted statement is no longer
  resolvable through ordinary reads. Retcon tooling that needs to walk deleted
  provenance has to bypass the filter, and P1C.2 should decide how that is
  exposed.

**Reason:** A retention feature that keeps rows for history but still serves
them as live is worse than either extreme: the row is neither reliably
archived nor reliably gone, and the caller cannot tell which. Enforcing the
filter in the base class is the only way to make the documented guarantee
hold for tables that do not exist yet.

**Status:** Approved — implement before Phase 1C.1.

## ADR-023: One row per flush, because the ORM orders by relationship not foreign key

**Context:** A probe that added a `Campaign` and an `Entity` to the same
session and committed once failed:

```text
insert or update on table "entities" violates foreign key constraint
"entities_campaign_id_fkey"
```

The echo log showed a single statement, `INSERT INTO entities`, then
`ROLLBACK`. The campaign was never written, so the child could not resolve it.
This looked like a unit-of-work ordering defect and was carried as an open bug
until it was isolated.

It is not one. Three findings:

- A bare three-table model (users -> campaigns -> entities) with matching
  foreign key values, no application code, no event listeners, and a plain
  sync engine fails identically. A sync engine rules out asyncio, psycopg, and
  the session configuration.
- `sort_tables()` returns the correct order (`users`, `campaigns`, `entities`),
  so the metadata is right. The unit of work does not consult it.
- The SQLAlchemy maintainer, on the equivalent upstream report, states that
  "the ORM orders objects in terms of their dependencies using relationship
  exclusively. ForeignKey is not considered," and closed it as not a bug.

That is the whole explanation. Insert order is derived from the mapper
dependency graph, which is built from `relationship()` declarations, not from
foreign key columns. `sort_tables()` sorts by foreign key, but nothing in the
flush path calls it that way.

This codebase expresses ownership as foreign key columns. `Entity.campaign_id`
references `campaigns.id` with no `relationship()`, which is the deliberate
consequence of ADR-016 and ADR-021: navigation and isolation go through
campaign-scoped repositories instead of ORM object graphs. So that hop has no
dependency edge, and an `Entity` is free to be inserted before its campaign.

**Decision:** The invariant is one row per flush. There are three write paths
in the codebase that persist a new row — `BaseRepository.create`,
`SpecializedRepository.create`, and `resolve_current_user` — and all three
already add and then flush immediately. No code changes are needed. What is
added is a guard, because the failure mode is invisible until it is a live
`IntegrityError`.

`tests/repositories/test_one_row_per_flush.py` walks the application package
and asserts that no function accumulates two pending `session.add()` calls
without an intervening `flush()`. It matches on the receiver containing
`session` so a `set.add()` is not mistaken for one, asserts it found a
plausible number of writes so it cannot pass by matching nothing, and carries
its own cases proving it rejects a batched parent and child. This is the same
structural approach as `test_no_undeleted_reads.py`, for the same reason:
SQLAlchemy offers no hook to enforce either rule, and both rules are silently
violable otherwise.

**Consequences:**
- A future endpoint that creates a graph in one request must flush the parent
  explicitly, and the structural test will say so at review time rather than
  letting it fail against production-shaped data.
- The stricter alternative, adding `relationship()` declarations for the
  ownership chain purely to give the flush an order, was rejected. It would
  reintroduce the ORM object graph that ADR-021 removed, and it would only fix
  ordering, not scoping, which is enforced in the repositories anyway.
- The constraint is invisible in the model definitions. A reader of
  `app/models/entity/entity.py` cannot tell that the missing relationship has a
  persistence consequence, so the note also lives in DATABASE.md.

**Reason:** This is documented upstream behaviour interacting with a deliberate
architectural choice, not a defect to repair. Repairing it in code would mean
adding machinery that solves a problem the codebase does not currently have,
while leaving the real invariant undocumented.

**Status:** Approved — documentation and guard only, no behaviour change.

## ADR-024: WebSocket identity binding is deferred to the end of Phase 1

**Context:** `app/api/websocket/routes/stream.py` validates the token, binds the
result to a local, and never reads it again:

```python
identity = await provider.validate_token(token)   # line 21
```

`identity` is never referenced. The socket accepts any token the provider
considers valid, knows nothing about which campaign or user the connection
represents, and cannot apply campaign scope or visibility to anything. ADR-014
already made the query-string token a temporary Phase 1 measure and ADR-019
separated the transport from realtime behaviour, but neither addresses the
discarded identity.

Nothing is persisted over this socket in Phase 1. The handler reads a
`transcript` field and echoes it back with an empty `matches` list, so there is
no data to scope and no context to filter. There is consequently no
authorization decision being made wrongly today.

**Decision:** Do not resolve this before P1D.1. Resolve it at the end of Phase
1, as an explicit step, and record the gap here so it is tracked rather than
inherited silently.

This is recorded now because the failure mode is misleading. A reader sees a
validated token and a successful accept, which reads as authenticated. The
connection is in fact unauthenticated in the only sense that matters: there is
no identity to enforce anything with. That is survivable while nothing is
written, and dangerous the moment something is, because the code will still
look correct.

The end of Phase 1 is the right time rather than merely a convenient one. The
fix needs a decision this phase has not made: what a stream connection is bound
to, and for how long. That depends on the Phase 2 token and streaming model, and
binding the identity earlier would mean guessing and then rewriting.

**Consequences:**
- The socket is not a security boundary in Phase 1 and must not become one
  without this step. Any transcript handling that persists, caches, or enriches
  needs the identity first.
- The lint finding that flags the unused binding stays. Fixing it by deleting
  the call would remove the token check and turn an authentication gap into an
  unauthenticated endpoint, which is strictly worse than the current state.

**Reason:** Deferring is correct because nothing is at stake yet, but the
deferral has to be visible. A gap that only exists in a local variable is a gap
nobody is tracking.

**Status:** Approved — defer to the end of Phase 1; do not expand WebSocket
scope before then.

## ADR-025: Audience rules are stored in Phase 1 but not enforced until Phase 2

**Context:** `entity_facts` and `entity_relationship_facts` have audience tables
that record who a fact is meant for (`general`, `dm`, `player` + `player_id`).
ADR-014 removed the separate visible/secret flag and made visibility a first
class concept, with the rule that visibility is enforced *before* model context
is constructed.

P1D.1 originally listed `FactRepository` as carrying "visibility filter from
PrePhase1". No such filter was ever implemented. An earlier version of
`app/repositories/fact_repo.py` and `audience_repo.py` nonetheless carried
docstrings claiming that audience rules were honoured on reads, which was false
documentation of a feature that did not exist. The docstrings have been
corrected and the claim removed.

Nothing is lost by deferring. Phase 1 has no DM view and no per-player
perspective: every read goes to the campaign owner, who is authorized for every
row by definition. A filter applied to owner-only reads would be dead code whose
only observable behaviour is to hide rows from the one person allowed to see
them.

**Decision:** Store audience rules and return them, unfiltered, from the fact
endpoints. Enforce visibility in Phase 2, before the first read that is not
owner-only, and before any LLM context is built from a fact.

The enforcement has to be a filter in the query, not a post-fetch check applied
to an already-loaded set. Paging makes that concrete: filtering after a page is
fetched returns a short page while the total counts every row, so a client
paging through results sees gaps it cannot explain. ADR-022's per-module
`test_no_undeleted_reads` guard is the pattern to extend when a visibility
predicate lands, so a repository that grows a read path without one is caught.

**Consequences:**
- `GET /facts/{fact_id}` returns every audience rule, including DM-only ones.
  Correct for an owner-only API, wrong the moment a player or DM view exists.
- `list_for_player` exists on the audience repository but is not reachable from
  any Phase 1 endpoint. It is the deterministic half of the Phase 2 filter and
  is here so the query is written and tested rather than improvised later.
- Phase 2 must not build a prompt from a fact and ask a model to decide
  visibility. The filter goes in the repository, ahead of context construction.

**Reason:** Storing the rules now keeps the schema settled and gives Phase 2 a
tested query, while the enforcement lands where it can be tested against real
vantage points instead of asserted against a fiction.

**Status:** Approved — store and return in Phase 1; enforce in Phase 2 before
any non-owner read or any model context that includes a fact.

## ADR-026: Entity recognition keeps its vocabulary in process, narrowed by a delete index

**Context:** P1E.1 shipped a deterministic matcher that loads every name and
alias in a campaign on every recognition call and then scans that vocabulary
per text token. Measured on this repository's dev machine with a 54-word
transcript:

| terms | match time | index build | no fuzzy |
|---|---|---|---|
| 1,100 | 119 ms | 0.3 ms | 0.1 ms |
| 11,000 | 1,114 ms | 2.7 ms | 0.2 ms |
| 110,000 | 11,404 ms | 33 ms | 0.6 ms |
| 550,000 | 56,976 ms | 178 ms | 2.3 ms |

Two separate costs, both linear in campaign size. The scan is the larger one:
`_fuzzy_best` compared every word against every term whose length was within
the edit limit, and at 11k terms essentially all of them qualified, so the
length bucketing filtered nothing. The profile showed 4.9M calls to
`levenshtein_within` for a 125-word transcript.

Nothing caught it. Functional tests pass on a slow implementation exactly as
they do on a fast one, because a slow matcher still returns the right
candidates. The only honest signal is a latency budget.

An 11,000-term campaign is 1,000 entities with ten aliases each. That is
plausible for a long-running campaign, and P1F calls recognition once per
transcript message, so the cost was about to be paid on every line of
narration.

Two candidate narrowings were measured before anything was written:

- **A cheap per-entry pre-filter** (character-multiset L1 distance bounded by
  twice the edit limit, which is a sound necessary condition). It was
  *slower*: 183 ms against 173 ms at 11k terms, 977 ms against 848 ms at
  55k. Natural-language terms share character multisets too often for the
  filter to reject anything, and the Python-level work per entry costs more
  than the comparison it avoids. Not used.
- **A delete index.** Every term is indexed under each string reachable from
  it by deleting up to `MAX_FUZZY_DISTANCE` characters; a query generates the
  same set from the word in the text and looks it up. 11k terms index to 59,840
  keys in 16 MB and answer a 39-token transcript in 2 ms against 147 ms for
  the scan, a 73x improvement. Used.

**Decision:** Narrow fuzzy candidates with a delete index, and keep each
campaign's built vocabulary in a bounded process-local cache.

The index is a *superset* filter, never the decision. If two strings are
within edit distance `d`, some string survives in both after at most `d`
deletions each, so index lookup cannot miss a real match; every returned
candidate is then confirmed by a real `levenshtein_within` call, and the
winning distance still comes from that measurement. `tests/application/
test_delete_index_equivalence.py` keeps a brute-force reference scan and
asserts the two agree across randomized vocabularies, deliberately corrupted
probes, unicode terms and reduced distance settings. The earlier length-bucketed
`Vocabulary.by_length` index was removed once nothing read it.

The index is built lazily on first fuzzy lookup and the vocabulary is cached
per campaign, because the two only pay off together. Measured in isolation the
index is *worse* than the scan for a single call at every size tested — the
build costs about twice one scan — and it breaks even after roughly two calls.
Caching without the index would leave a per-message scan; the index without
caching would add a build to every message. The full vocabulary is 57 bytes
per term, so an unbounded cache is a memory leak with extra steps, and the LRU
is bounded at 32 campaigns with eviction documented as costing only a rebuild.

**Consequences:**
- Recognition over 11k terms goes from 1,114 ms to 9.5 ms per message, and to
  45 ms at 110k terms. The first call for a campaign still pays ~225 ms to
  build the vocabulary and index; that is a cache miss, not a regression.
- **The cache is process-local, and this is a real limitation.** Invalidation
  is an explicit call from the five use cases that can change a vocabulary
  (`create_entity`, `add_alias`, `update_entity`, `soft_delete_entity`,
  `remove_alias`), so a write in one worker process does not reach another's
  cache. A multi-worker deployment therefore has a staleness window bounded by
  the next write to that campaign in that process, not by any cross-process
  signal. Entity and alias writes are rare compared to recognition reads, which
  is why this is accepted for Phase 1 and stated rather than hidden. Fixing it
  properly needs a shared version marker, which belongs with the indexing work
  described below rather than invented alongside it. A deployment that cannot
  tolerate staleness constructs `MATCHING_VOCABULARIES` with `max_campaigns=0`.
- A missed invalidation is not a stale read of old data. A soft-deleted entity
  whose vocabulary is still cached keeps answering to its name, so the write
  paths are enumerated in
  `tests/application/test_matching_vocabulary.py` rather than left to memory.
- The scan's asymptotics are now fine for realistic campaigns, but the
  vocabulary is still fully materialized per campaign in memory and still read
  in one query. Past roughly 100k terms — larger than any plausible campaign,
  and included in the stress case only to find the shape — the remaining fix is
  to push candidate generation into SQL with a trigram index, so the database
  returns plausible rows instead of the whole vocabulary. That is deliberately
  **not** done here: it adds a Postgres extension dependency, changes where
  matching happens, and needs its own decision.

## ADR-027: An entity's own name is stored in `entity_aliases` as a `name` row

**Context:** ADR-026 left one open question about where candidate terms should
come from, and the pending SQL-side indexing work makes it urgent: the trigram
index decision has to name a table, and `entity_aliases` cannot be indexed
alone because it carries no `campaign_id` — campaign scope reaches it only by
joining `entities`. So the vocabulary query is a join either way, and the real
question is what the vocabulary *is*.

The previous shape was two scoped projections, an entity's `name` from
`entities` and every `alias` from `entity_aliases`, unioned in Python. That
shape existed because of a bug: a single outer join returns one row per
(entity, alias) pair, so an entity *with* an alias contributed only its alias
and became unmatchable by its real name. P1E.1 fixed it with two queries rather
than with a constraint, which left the guarantee in the query's shape.

**Decision:** Store every matchable term in `entity_aliases`, including the
entity's own name, distinguished by a new `kind` column (`name` | `alias`).
The vocabulary becomes one join, and `is_alias` is read off each row's kind
rather than inferred from which query produced it.

**Why, given it is not faster.** Measured, the union was never the cost: the
query's time is dominated by the trigram scan and `levenshtein()` calls in the
SQL-side design, and the join to `entities` remains either way. This was chosen
for comprehension — one table means "the set of strings that can match this
entity", readable without knowing which query a term came from. That is a real
maintainability argument, and it also happens to make the SQL-side path
single-table, which is a prerequisite for the decision still open.

**The cost, accepted deliberately.** The entity's name now exists in two places
and can drift, and an entity contributes its name *because a `name` row exists*
rather than because of how the query is written. That is an invariant maintained
by five write paths instead of a structural guarantee. It is defensible only
while the other half is enforced, so:

- `uq_entity_aliases_one_name` is a partial unique index on
  `entity_aliases (entity_id) WHERE kind = 'name' AND deleted_at IS NULL`, which
  makes a *second* live name row impossible. Soft-deleted rows are excluded so
  a retcon can restore one without tripping it.
- Existence is asserted in a test rather than by convention:
  `test_every_live_entity_has_exactly_one_live_name_alias`. A cross-table
  invariant cannot be a `CHECK`, and a trigger would put domain logic in the
  database, so the test is the enforcement and the index is the backstop.

**Consequences:**
- The confidence tiers survive unchanged, which is why this is a storage change
  rather than a behaviour change: an exact name is still 1.0 and an exact alias
  still 0.95. Verified end to end against the real database, including that a
  renamed entity's old name drops to the distance-2 tier (0.7) rather than
  vanishing, since `"sela viper"` is genuinely two edits from `"selina viper"`.
- `create_entity` writes the name row first, then the requested aliases;
  `update_entity` retargets it on a rename and refuses a rename that collides
  with an existing alias; `add_alias` rejects an alias equal to the name;
  `remove_alias` refuses a `name` row, pointing the caller at renaming instead;
  `soft_delete_with_specializations` stamps it in the same transaction as the
  specialization, which is the same hazard that method already existed for.
- A rename without an alias repository is a `ValidationError` rather than a
  half-applied write that leaves an entity matchable only by a name it no longer
  has. The HTTP route supplies one.
- `EntityAliasRead` exposes `kind`, so `GET /entities/{id}` shows the name row
  among the aliases. Reporting actual table state was preferred over hiding it,
  since a filtered alias list would under-report what is stored and reintroduce
  the two-representation problem this decision removed.
- The vocabulary query is now one statement instead of two. Every existing
  matching test still passes unmodified, because the pipeline never learns where
  a term came from.

## ADR-028: Process-local matching state is a known and accepted interim state

**Context:** ADR-026 shipped the matcher with a bounded process-local LRU
(`MATCHING_VOCABULARIES`, 32 campaigns) and stated its limitation plainly: a
write in one worker process cannot reach another process's cache, so a
multi-worker deployment has a staleness window bounded by the next write to that
campaign *in that process*, not by any cross-process signal. ADR-027 made this
more pressing rather than less, because it fixed the table the eventual fix must
index and therefore removed the last reason to defer the decision.

The current deployment is not exposed. `Dockerfile:12` runs a single Uvicorn
worker, so there is only one cache to be stale. The exposure is entirely
prospective, which is precisely why it is easy to leave unrecorded: the design
looks stateless, because every request does construct its own repository and
authorization is enforced per request. It is the *matching* state that is
process-local, and nothing in the request path reveals that.

**Decision:** Record that process-local matching state is an accepted interim
state, not the intended end state, and that moving candidate generation into SQL
is an eventual necessity. It is **not** a Phase 1 gate and does not block the
MVP. Phase 1 keeps the LRU; the replacement is Phase 3 work (P3.1).

This is a decision about *sequencing and honesty*, not about which approach
wins. The direction is already settled — ADR-026 named the SQL trigram path as
the remaining fix, and ADR-027 made `entity_aliases` the single table to index —
so the open question was never whether, only when.

**Why it is not an MVP blocker.** Every condition that would make it one is
either absent or measured, and none of them is a correctness failure:

- **Scale.** The current cost is a ~225 ms cold start at 11k terms, 2.7 ms warm,
  and 45 ms at 110k. At one Uvicorn worker, a 225 ms first-call cost is paid once
  per campaign per process lifetime. The threshold where this hurts is
  campaigns large enough that the cold start is felt per restart — not reachable
  in Phase 1, whose realistic entity counts are far below 11k.
- **Correctness.** Staleness is only reachable at more than one worker, and
  entity and alias writes are rare compared to recognition reads. The write paths
  that must invalidate are enumerated in `tests/application/test_matching_vocabulary.py`
  rather than left to memory.
- **Escape hatch.** A deployment that cannot tolerate any staleness already has
  one: construct `MATCHING_VOCABULARIES` with `max_campaigns=0`, which
  disables caching entirely and accepts a query per call.

**What changes when it is done (P3.1):**
- `pg_trgm` becomes a dependency and needs its own migration and an ADR.
- Candidate generation moves from "load every term, then narrow in Python" to
  "ask the database for plausible rows." `entity_aliases` is the table to index
  (ADR-027), joined to `entities` for campaign scope, since it carries no
  `campaign_id`.
- Trigram similarity is a **heuristic superset filter, never the decision**, and
  the asymmetry matters: trigram similarity can *miss* true edit-distance
  neighbours on short strings, which the delete index provably cannot. So the
  Python `levenshtein_within` confirmation must stay authoritative even after the
  index exists, or short-term recall regresses silently.
- `tests/application/test_delete_index_equivalence.py` becomes the oracle for
  this change: the SQL path must agree with the brute-force reference across
  randomized vocabularies, corrupted probes, unicode terms and reduced distance
  settings, or the change is not equivalent.
- The process-local LRU is removed, not layered under.

**Consequences:**
- Phase 1 exits with a documented interim state, and `MATCHING_VOCABULARIES` is
  read as a placeholder with a known end date rather than as architecture.
- A second worker is not a safe scaling step for recognition until P3.1 lands.
  This is the concrete constraint to respect when deployment topology is
  revisited, and it is recorded here because nothing at runtime will report it.
- Phase 2 ingestion volume is the thing to watch. If ingestion makes campaigns
  large enough for the 225 ms cold start to be felt, that is the trigger to pull
  P3.1 forward — but it is a trigger, not a reason to build it speculatively
  during Phase 1.

## ADR-029: A child table that inherits its campaign scope must scope its own `get`

**Context:** `BaseRepository._campaign_scope` is a silent no-op for a model
without a `campaign_id` column, which is how `document_statements` and
`entity_aliases` inherit isolation through a parent. That no-op is correct for
the hand-written reads: `DocumentStatementRepository.get_scoped` and
`EntityAliasRepository.get_by_alias` both join to the parent and filter on its
campaign, and ADR-022 added those joins deliberately.

The gap was the *inherited* methods. `soft_delete`, `update`, `exists` and `get`
all live in `BaseRepository` and were written before these two tables existed.
`soft_delete` and `update` resolve the row through `self.get(id)`, so on a child
table they executed a bare `SELECT ... WHERE id = :id` with no join at all. Given
only an id, they would stamp or edit a row in another campaign and return
`True`/`True` while doing it. `EntityAliasRepository` overrode `get` but left it
unscoped, and `DocumentStatementRepository` did not override it, so it also
inherited the base version. The `_campaign_scope` no-op was documented as
deliberate; the consequence for inherited writes was not.

**Not reachable through the API, but reachable through the repository.** Every
current call site guards the write by resolving the parent first through a
campaign-scoped repository and comparing the parent id — `remove_alias` checks
`alias.entity_id == entity_id` after a scoped `entity_repo.get`, and
`delete_statement` does the same with `document_id`. So no route could cross the
boundary. The defect was that the safety depended on that convention holding at
every call site forever, in a method whose signature promises nothing about the
parent.

**Decision:** Override `get` and `exists` on both child repositories to apply the
parent join, so campaign scoping on these tables is a property of the
repository rather than of its callers.

**Why the inherited version is the right thing to fix.** Making the *callers*
more careful would have left the trap in place for the next person, and the
failure mode is the dangerous combination: a method that reports success while
writing outside its scope. The structural test in `test_no_undeleted_reads.py`
checks that reads filter `deleted_at`, but nothing checked that a write resolves
within the campaign — the deletion filter and the campaign scope are different
properties, and only the first was asserted.

`create` is deliberately left unscoped and is asserted as such. It inserts
whatever parent id it is handed, because there is no campaign column to
constrain it, and the fix for that is at the use case, not the repository: the
insert is not a read of the parent, so there is no row to scope against. The
`TestChildTableWriteScoping::test_create_is_still_unscoped` test exists so that a
future attempt to rely on it for isolation fails loudly rather than silently.

**Consequences:**
- `DocumentStatementRepository.get_scoped` is removed rather than kept alongside
  the new `get`. Two names for one behaviour is the kind of split that let the
  unscoped one be used by accident; the call sites in `facts.py` and the
  statement use cases now call `get`, and they are genuinely scoped.
- Every `DocumentStatement` and `EntityAlias` read now applies two deletion
  predicates — the child's own and the parent's. That is correct and intended: a
  statement under a deleted document is not reachable, and an alias of a deleted
  entity is not either.
- `tests/repositories/test_document_repo.py::TestChildTableWriteScoping` asserts
  the join on `get`, `exists` and `soft_delete` for both tables, and the
  two-deletion-predicate requirement. It asserts compiled SQL, because that is
  the layer at which the defect lived.
- Verified against the live database with two real campaigns, not only against
  compiled statements: a repository scoped to the wrong campaign now returns
  `None`/`False` from `get`, `exists`, `soft_delete` and `update`, and the target
  rows are confirmed unstamped and unedited afterwards. The owner can still write,
  so the join is not simply blocking everything. The probe was re-run with the
  override removed and it failed on exactly the two checks it should, so it does
  detect the defect rather than passing vacuously.
- `rename` on the alias repository is unaffected: it resolves through
  `get_name_alias`, which is now scoped, and is only reachable after the use case
  has resolved the entity.

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
if campaign.user_id != user_id: 403 Forbidden
```

**Phase 2+ (deferred):**
- `CampaignMember` authorization with roles (`dm`, `player`, `viewer`).
- Membership-based access replaces owner-only check.

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
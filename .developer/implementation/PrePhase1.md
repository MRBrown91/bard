# PrePhase1 — Foundation Refactoring & Schema Fixes

> **Purpose:** Prepare the codebase for Phase 1 API development by reorganizing models, fixing schema issues, and establishing the service/repository foundation. No user-visible features.

> **Prerequisite:** Architecture Takeover Report reviewed and decisions recorded.

---

## Step Status Legend
- `Planning` — Defined but not approved for implementation
- `Approved` — Ready to implement; awaiting developer action
- `Completed` — Implemented, tested, merged

---

## PP1.1 — Split Domain Models into Cohesive Modules

**Status:** `Completed` (commit: c6f70e3)

**Goal:** Replace `app/models/domain.py` (394 lines, 21 models) with domain-cohesive modules.

**Files to Create:**
```
app/models/
├── __init__.py                      # Re-export all models (update existing)
├── user.py                          # User + administrative settings (OAuth, future username/password, app settings)
├── campaign.py                      # Campaign, CampaignMember, Session
├── entity/
│   ├── __init__.py                  # Re-export entity types
│   ├── entity.py                    # Entity, EntityAlias
│   └── entity_types/
│       ├── __init__.py
│       ├── actor.py
│       ├── player.py
│       ├── player_character.py
│       ├── location.py
│       ├── item.py
│       └── faction.py
├── document.py                      # Document, DocumentStatement
├── fact.py                          # EntityFact, EntityRelationshipFact
├── relationship.py                  # EntityRelationship
├── event.py                         # Event
└── audience.py                      # EntityFactAudience, EntityRelationshipFactAudience
```

**Files to Modify:**
- `app/models/__init__.py` — Update imports to pull from new modules
- `app/models/domain.py` — **Delete** after verification

**Verification:**
1. `alembic revision --autogenerate -m "verify_model_split"` produces empty migration (no schema changes)
2. Existing tests pass: `pytest tests/`
3. Ruff + mypy clean: `ruff check . && mypy app/`

**Dependencies:** None (first step)

**Risks:** Circular imports if modules import each other. Avoid by keeping all FK references as strings (`ForeignKey("entities.id")`) and using `TYPE_CHECKING` for type-only imports. The `entity/` subpackage must be imported in `app/models/__init__.py` to maintain Alembic model discovery.

---

## PP1.2 — Add Missing Indexes & Unique Constraints

**Status:** `Completed` (commit: aa18b5a)

**Goal:** Add database indexes and constraints identified in Architecture Takeover Report.

**Migration:** New Alembic revision (`alembic revision -m "add_missing_indexes_and_constraints"`)

**Changes:**
| Table | Index/Constraint | Type | Reason |
|-------|------------------|------|--------|
| `entity_aliases` | `(entity_id, alias)` | **Unique** | Prevent duplicate aliases; cross-campaign safety via entity FK |
| `documents` | `session_id` | Index | Query session documents |
| `entity_relationship_facts` | `source_entity_id` | Index | Query outgoing relationships for entity (campaign-scoped via composite) |
| `entity_relationship_facts` | `target_entity_id` | Index | Query incoming relationships for entity (campaign-scoped via composite) |
| `entity_fact_audiences` | `player_id` | Index | Query audience rules for player |
| `entity_relationship_fact_audiences` | `player_id` | Index | Query audience rules for player |

**Note:** Standalone `entity_id` index on `entity_facts` intentionally omitted. All fact queries must include `campaign_id` (enforced by repository layer), making the existing composite index `(campaign_id, entity_id)` sufficient.

**Verification:**
1. Migration applies cleanly: `alembic upgrade head`
2. Indexes visible in `\d` output
3. Unique constraint rejects duplicate `(entity_id, alias)` inserts

**Dependencies:** PP1.1 (models must be split first so migration references correct modules)

---

## PP1.3 — Fix FK Delete Behavior to RESTRICT

**Status:** `Completed` (commit: df7dd41)

**Goal:** Change cascade deletes to `RESTRICT` on all FKs from fact/relationship/event tables to `campaigns` and `entities` to preserve provenance on soft delete.

**Migration:** New Alembic revision (`alembic revision -m "fix_fk_delete_behavior"`)

**Affected FKs (add `ondelete="RESTRICT"`):**
- `entity_facts.campaign_id` → `campaigns.id`
- `entity_facts.entity_id` → `entities.id`
- `entity_facts.event_id` → `events.id`
- `entity_relationship_facts.campaign_id` → `campaigns.id`
- `entity_relationship_facts.source_entity_id` → `entities.id`
- `entity_relationship_facts.target_entity_id` → `entities.id`
- `entity_relationship_facts.event_id` → `events.id`
- `entity_relationships.campaign_id` → `campaigns.id`
- `entity_relationships.source_entity_id` → `entities.id`
- `entity_relationships.target_entity_id` → `entities.id`
- `events.campaign_id` → `campaigns.id`
- `documents.campaign_id` → `campaigns.id`
- `documents.session_id` → `sessions.id`
- `campaigns.user_id` → `users.id`
- `sessions.campaign_id` → `campaigns.id`
- `entities.campaign_id` → `campaigns.id`

**Note:** Keep `CASCADE` for:
- `entity_aliases.entity_id` → `entities.id` (aliases die with entity)
- Specialized entity tables (`actors`, `players`, etc.) → `entities.id` (1:1 extensions)
- `document_statements.document_id` → `documents.id` (statements die with document)
- `entity_fact_audiences.fact_id` → `entity_facts.id`
- `entity_relationship_fact_audiences.fact_id` → `entity_relationship_facts.id`
- `entity_relationships.relationship_fact_id` → `entity_relationship_facts.id`

**Verification:**
1. Migration applies cleanly
2. Attempting to delete a campaign with existing entities/facts raises FK violation (not cascade)
3. Soft delete (`UPDATE ... SET deleted_at = now()`) still works

**Dependencies:** PP1.1, PP1.2

---

## PP1.4 — Create Repository Base & Campaign-Scoped Query Pattern

**Status:** `Planning`

**Goal:** Establish repository layer with automatic campaign isolation.

**Files to Create:**
```
app/repositories/
├── __init__.py
├── base.py              # BaseRepository with campaign-scoped query methods
├── user_repo.py
├── campaign_repo.py
├── session_repo.py
├── entity_repo.py
├── document_repo.py
├── fact_repo.py
├── relationship_repo.py
├── event_repo.py
└── audience_repo.py
```

**Key Pattern in `base.py`:**
```python
class BaseRepository:
    def __init__(self, session: AsyncSession, campaign_id: UUID):
        self.session = session
        self.campaign_id = campaign_id

    def _campaign_scope(self, stmt: Select) -> Select:
        """Automatically apply campaign_id filter to queries."""
        # Implementation depends on model having campaign_id column
        return stmt.where(self.model.campaign_id == self.campaign_id)
```

**Files to Modify:**
- `app/database/session.py` — Add dependency for campaign-scoped session (optional)

**Verification:**
1. Repository unit tests with in-memory fakes (no DB)
2. Integration test: query with campaign A returns only campaign A data

**Dependencies:** PP1.1

---

## PP1.5 — Create Pydantic Schemas (API Boundaries)

**Status:** `Planning`

**Goal:** Define request/response models for all Phase 1 APIs.

**Files to Create:**
```
app/schemas/
├── __init__.py
├── user.py              # UserCreate, UserRead, UserUpdate
├── campaign.py          # CampaignCreate, CampaignRead, CampaignUpdate, CampaignList
├── session.py           # SessionCreate, SessionRead, SessionUpdate, SessionList
├── entity.py            # EntityCreate, EntityRead, EntityUpdate, EntityList, AliasCreate, AliasRead
├── specialized.py       # ActorCreate/Read, PlayerCreate/Read, etc.
├── document.py          # DocumentCreate, DocumentRead, DocumentUpdate, StatementCreate, StatementRead
├── fact.py              # EntityFactCreate, EntityFactRead, EntityFactUpdate, RelationshipFactCreate/Read/Update
├── relationship.py      # EntityRelationshipRead
├── event.py             # EventCreate, EventRead, EventUpdate
├── audience.py          # FactAudienceCreate/Read, RelationshipFactAudienceCreate/Read
└── common.py            # Pagination, ErrorResponse, UUID/date types
```

**Validation Rules:**
- `confidence`: `Field(ge=0, le=1)`
- `importance`: `Field(ge=0)`
- `status`: `Field(pattern="^(active|invalidated|superseded)$")`
- `entity_type`: `Field(pattern="^(actor|player|player_character|location|item|faction)$")`
- `audience_type`: `Field(pattern="^(general|player|dm)$")`

**Verification:**
1. Schemas import cleanly
2. Validation rejects invalid values
3. Serialization/deserialization round-trip works

**Dependencies:** PP1.1

---

## PP1.6 — Implement Stub OIDC Auth Provider Interface

**Status:** `Planning`

**Goal:** Define authentication interface and stub implementation for local dev.

**Files to Create:**
```
app/integrations/
├── __init__.py
├── auth.py              # AuthProvider protocol + StubAuthProvider
└── auth_models.py       # TokenPayload, UserInfo Pydantic models
```

**Interface (`auth.py`):**
```python
class AuthProvider(Protocol):
    async def validate_token(self, token: str) -> TokenPayload: ...
    async def get_user_info(self, token: str) -> UserInfo: ...

class StubAuthProvider:
    """Accepts any token; returns test user. For local dev only."""
    async def validate_token(self, token: str) -> TokenPayload: ...
    async def get_user_info(self, token: str) -> UserInfo: ...
```

**Files to Modify:**
- `app/core/config.py` — Add `oidc_provider: Literal["stub", "keycloak", "auth0"] = "stub"`

**Verification:**
1. Stub provider works in tests
2. Interface allows swapping real provider without changing callers

**Dependencies:** PP1.1

---

## PP1.7 — Create Auth Middleware & Campaign Scope Dependencies

**Status:** `Planning`

**Goal:** FastAPI dependencies for authentication and campaign-scoped repository injection.

**Files to Create:**
```
app/api/
├── dependencies.py      # get_current_user, get_campaign_repo, get_entity_repo, etc.
└── security.py          # JWT validation (delegates to AuthProvider)
```

**Dependencies Provided:**
- `CurrentUser` — authenticated User model
- `CampaignScope` — campaign_id + verified ownership/membership
- `EntityRepo`, `FactRepo`, etc. — pre-scoped repositories

**Verification:**
1. Dependency injection works in test routes
2. Unauthenticated requests return 401
3. Cross-campaign access returns 403

**Dependencies:** PP1.4, PP1.6

---

## PP1.8 — Implement Fact Visibility Filter

**Status:** `Planning`

**Goal:** Centralized visibility enforcement for fact/relationship queries.

**Files to Create/Modify:**
- `app/services/visibility.py` — `VisibilityFilter` service
- `app/repositories/fact_repo.py` — Integrate filter in query methods

**Logic:**
```python
class VisibilityFilter:
    def apply(self, stmt: Select, user: User, campaign_id: UUID) -> Select:
        # Join audiences, filter by audience_type and player_id
        # "general" = visible to all campaign members
        # "player" = visible to specific player
        # "dm" = visible only to campaign owner (DM)
        return stmt.join(...).where(...)
```

**Verification:**
1. Unit tests: filter returns correct subset for each audience type
2. Integration test: DM sees all facts; player sees only general + their own

**Dependencies:** PP1.4, PP1.7

---

## PP1.9 — Reorganize API Routes into Protocol-Specific Structure

**Status:** `Planning`

**Goal:** Establish the approved API route organization before adding more endpoints.

**Files to Create:**
```
app/api/
├── dependencies.py          # Shared dependencies: get_current_user, get_campaign_scope, get_*_repo
├── security.py              # JWT validation, token extraction
├── http/
│   ├── __init__.py          # Exports http_router (includes all HTTP routes)
│   └── routes/
│       ├── __init__.py      # Registers all route modules
│       ├── health.py        # Move from app/api/health.py
│       ├── campaigns.py     # Placeholder for Phase 1A
│       ├── sessions.py      # Placeholder for Phase 1A
│       ├── entities.py      # Placeholder for Phase 1B
│       ├── documents.py     # Placeholder for Phase 1C
│       ├── facts.py         # Placeholder for Phase 1D
│       ├── relationships.py # Placeholder for Phase 1D
│       └── events.py        # Placeholder for Phase 1D
└── websocket/
    ├── __init__.py          # Exports ws_router (includes WebSocket routes)
    ├── routes/
    │   ├── __init__.py
    │   └── stream.py        # Move from app/realtime/stream.py
    └── handlers/
        ├── __init__.py
        └── transcript.py    # Transcript processing logic (Phase 1F)
```

**Files to Modify:**
- `app/main.py` — Import routers from `app.api.http` and `app.api.websocket`
- `app/api/health.py` — Move to `app/api/http/routes/health.py`
- `app/realtime/stream.py` — Move to `app/api/websocket/routes/stream.py`
- `app/realtime/__init__.py` — Can be removed or kept for future realtime services
- `app/api/__init__.py` — Update to new structure

**Verification:**
1. `uvicorn app.main:app --reload` starts successfully
2. `GET /api/health` returns `{"status": "ok"}`
3. `WS /ws/stream?token=test` connects and echoes transcript
3. Ruff + mypy clean
4. Existing tests pass

**Dependencies:** PP1.6 (auth provider interface for dependencies), PP1.7 (campaign scope dependencies)

---

## PP1.10 — Developer Test Console (HTML/JS)

**Status:** `Planning`

**Goal:** Implement the browser test console referenced in README.

**Files to Create:**
```
devtools/
└── test_console/
    ├── index.html
    ├── app.js
    └── style.css
```

**Features:**
- Health check button
- WebSocket connect with token input
- Transcript send + response display
- Campaign/entity CRUD forms (after APIs exist)

**Verification:**
1. `docker compose up -d db && uvicorn app.main:app --reload`
2. Open `devtools/test_console/index.html` in browser
3. Health check returns OK
4. WebSocket connects and echoes transcript

**Dependencies:** PP1.9 (for reorganized routes), PP1.7 (for auth), Phase 1B+ (for CRUD forms)

---

## PrePhase1 Exit Criteria

All steps `Completed`:
- [ ] Models split, Alembic verified (PP1.1)
- [ ] Missing indexes/constraints migrated (PP1.2)
- [ ] FK delete behavior fixed (PP1.3)
- [ ] Repository base with campaign scope (PP1.4)
- [ ] Pydantic schemas for all domains (PP1.5)
- [ ] Stub auth provider + middleware (PP1.6, PP1.7)
- [ ] Visibility filter implemented (PP1.8)
- [ ] API routes reorganized into http/websocket structure (PP1.9)
- [ ] Test console loads and connects (PP1.10)

**Next:** Phase 1A — Campaign & Session APIs
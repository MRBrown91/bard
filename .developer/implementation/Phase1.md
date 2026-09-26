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

**Status:** `Planning`

**Goal:** Full campaign lifecycle management.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns` | Create campaign (authenticated user becomes owner) |
| GET | `/api/campaigns` | List user's campaigns (paginated) |
| GET | `/api/campaigns/{campaign_id}` | Get campaign details |
| PATCH | `/api/campaigns/{campaign_id}` | Update campaign (name, description, is_active) |
| DELETE | `/api/campaigns/{campaign_id}` | Soft delete campaign |

**Service:** `CampaignService` in `app/services/campaign_service.py`
**Repository:** `CampaignRepository` (from PrePhase1)
**Schemas:** `CampaignCreate`, `CampaignRead`, `CampaignUpdate`, `CampaignList`

**Authorization:** Owner-only for PATCH/DELETE/GET-by-id. List returns only owned campaigns.

**Tests:**
- Unit: service methods with fake repo
- Integration: full CRUD flow with auth, cross-user isolation

---

### P1A.2 — Campaign Member API (Stub for Future Sharing)

**Status:** `Planning`

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

**Status:** `Planning`

**Goal:** Session management within a campaign.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/sessions` | Create session |
| GET | `/api/campaigns/{campaign_id}/sessions` | List sessions (paginated, filter by active/ended) |
| GET | `/api/campaigns/{campaign_id}/sessions/{session_id}` | Get session details |
| PATCH | `/api/campaigns/{campaign_id}/sessions/{session_id}` | Update session (name, session_number, started_at, ended_at) |
| DELETE | `/api/campaigns/{campaign_id}/sessions/{session_id}` | Soft delete session |

**Service:** `SessionService`
**Repository:** `SessionRepository`
**Schemas:** `SessionCreate`, `SessionRead`, `SessionUpdate`, `SessionList`

**Authorization:** Campaign owner only (via campaign scope dependency).

**Tests:** Full CRUD; campaign isolation; session_number uniqueness per campaign.

---

## Phase 1B — Entity APIs

### P1B.1 — Entity Core CRUD API

**Status:** `Planning`

**Goal:** Manage base entities and aliases.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entities` | Create entity (type, name, description) |
| GET | `/api/campaigns/{campaign_id}/entities` | List entities (filter by type, search by name) |
| GET | `/api/campaigns/{campaign_id}/entities/{entity_id}` | Get entity with specialized data + aliases |
| PATCH | `/api/campaigns/{campaign_id}/entities/{entity_id}` | Update base entity fields |
| DELETE | `/api/campaigns/{campaign_id}/entities/{entity_id}` | Soft delete entity |

**Alias Sub-resource:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entities/{entity_id}/aliases` | Add alias |
| DELETE | `/api/campaigns/{campaign_id}/entities/{entity_id}/aliases/{alias_id}` | Remove alias |

**Service:** `EntityService`
**Repository:** `EntityRepository`
**Schemas:** `EntityCreate`, `EntityRead`, `EntityUpdate`, `EntityList`, `AliasCreate`, `AliasRead`

**Authorization:** Campaign owner.

**Tests:** Entity + alias CRUD; alias uniqueness per entity; type validation.

---

### P1B.2 — Specialized Entity APIs

**Status:** `Planning`

**Goal:** Manage stable canonical fields for each entity type.

**Endpoints (per type: actors, players, player-characters, locations, items, factions):**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entities/{entity_id}/actor` | Create/update actor data |
| GET | `/api/campaigns/{campaign_id}/entities/{entity_id}/actor` | Get actor data |
| PATCH | `/api/campaigns/{campaign_id}/entities/{entity_id}/actor` | Update actor fields |
| DELETE | `/api/campaigns/{campaign_id}/entities/{entity_id}/actor` | Remove actor specialization |

**Player Endpoint Additional:**
- POST `/api/campaigns/{campaign_id}/players` — Create player (links User + Entity)
- GET `/api/campaigns/{campaign_id}/players` — List players

**PlayerCharacter Endpoint:**
- POST `/api/campaigns/{campaign_id}/player-characters` — Link character entity to player

**Service:** `SpecializedEntityService` (or per-type services)
**Schemas:** Per-type create/read/update models

**Validation:**
- Actor: entity_type must be "actor"
- Player: entity_type must be "player"; user_id must exist
- PlayerCharacter: entity_type must be "player_character"; player must exist in same campaign
- Location/Item/Faction: corresponding entity_type

**Tests:** Type enforcement; cross-campaign prevention; FK integrity.

---

## Phase 1C — Document APIs

### P1C.1 — Document CRUD API

**Status:** `Planning`

**Goal:** Manage source documents (campaign-level or session-level).

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/documents` | Create document (type, title, content, optional session_id) |
| GET | `/api/campaigns/{campaign_id}/documents` | List documents (filter by session_id, document_type) |
| GET | `/api/campaigns/{campaign_id}/documents/{document_id}` | Get document with statements |
| PATCH | `/api/campaigns/{campaign_id}/documents/{document_id}` | Update document metadata |
| DELETE | `/api/campaigns/{campaign_id}/documents/{document_id}` | Soft delete document |

**Service:** `DocumentService`
**Repository:** `DocumentRepository`
**Schemas:** `DocumentCreate`, `DocumentRead`, `DocumentUpdate`, `DocumentList`

**Authorization:** Campaign owner.

**Tests:** Document + statement CRUD; session_id FK validation; campaign isolation.

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

**Status:** `Planning`

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

**Service:** `FactService`
**Repository:** `FactRepository` (with visibility filter from PrePhase1)
**Schemas:** `EntityFactCreate`, `EntityFactRead`, `EntityFactUpdate`, `FactAudienceCreate`, `FactAudienceRead`

**Validation:** `confidence` 0-1, `importance` >= 0, `status` enum, `fact_type` free text (convention: "physical_trait", "personality", "history", etc.)

**Tests:** Provenance chain (fact → statement → document); visibility filter integration; status transitions.

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

**Implementation:** Domain event handlers in `app/services/relationship_sync.py` called from `RelationshipFactService` methods.

**Tests:** Sync correctness for all status transitions; idempotency; race condition handling (DB constraints).

---

## Phase 1E — Entity Recognition (Deterministic)

### P1E.1 — Entity Matcher Implementation

**Status:** `Planning`

**Goal:** Implement `EntityMatcher.find_candidates(text)` with deterministic pipeline.

**Pipeline (per ADR-008):**
1. Exact entity name match (case-sensitive)
2. Exact alias match (case-sensitive)
3. Case-insensitive name match
4. Case-insensitive alias match
5. Fuzzy match (Levenshtein distance <= 2, configurable)
6. Return `EntityCandidate` list sorted by confidence

**Files:**
- `app/services/entity_matching.py` — Replace stub with implementation
- `app/services/matching_pipeline.py` — Pipeline steps as composable functions

**Confidence Scoring:**
- Exact name: 1.0
- Exact alias: 0.95
- Case-insensitive name: 0.9
- Case-insensitive alias: 0.85
- Fuzzy: 0.7 - 0.8 based on distance

**Repository Dependency:** `EntityRepository` for fetching campaign entities/aliases.

**Tests:**
- Unit: each pipeline step in isolation
- Integration: full pipeline with test campaign data
- Edge cases: overlapping matches, substring issues, Unicode

---

### P1E.2 — Entity Recognition API

**Status:** `Planning`

**Goal:** Expose entity matching as a service endpoint.

**Endpoint:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/campaigns/{campaign_id}/entity-recognition` | Input: `{text: string}` → Output: `{candidates: EntityCandidate[]}` |

**Service:** `EntityRecognitionService` (wraps `EntityMatcher`)

**Schemas:** `EntityRecognitionRequest`, `EntityRecognitionResponse`, `EntityCandidateSchema`

**Authorization:** Campaign owner (or member in future).

**Tests:** API contract; pipeline integration; empty/no-match responses.

---

## Phase 1F — Realtime WebSocket Protocol

### P1F.1 — Authenticated WebSocket Endpoint

**Status:** `Planning`

**Goal:** Upgrade WebSocket to require authentication and campaign scope.

**Changes to `app/realtime/stream.py`:**
- Extract token from query string: `/ws/stream?token=<jwt>&campaign_id=<uuid>`
- Validate via `AuthProvider`
- Verify campaign access
- Inject `campaign_id` and `user` into connection state

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
- `app/realtime/stream.py` — Implement pipeline
- `app/services/realtime_service.py` — Business logic for context assembly

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
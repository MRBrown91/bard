# Development Phases

## Phase 1 — Domain and backend foundation

- FastAPI application.
- PostgreSQL database.
- SQLAlchemy models.
- Alembic migrations.
- OIDC authentication boundary.
- Campaign/session/entity/document/fact/event APIs.
- WebSocket protocol skeleton.
- Basic test console.
- Automated tests and code-quality tooling.

## Phase 2 — Knowledge ingestion

- Document upload and parsing interfaces.
- Document statements.
- Deterministic entity matching.
- Fact and relationship extraction interface.
- Manual review/editing workflow.

## Phase 3 — Context retrieval

- PostgreSQL full-text/fuzzy retrieval where useful.
- pgvector embeddings.
- Semantic retrieval behind an application interface.
- Visibility-aware context assembly.

## Phase 4 — Live session intelligence

- Streaming transcript processing.
- Entity mention detection.
- Context cards/events returned over WebSockets.
- Session event persistence.

## Phase 5 — Audio intelligence

- Server or client STT integration.
- Speaker diarization.
- Voice characteristics.
- Speaker-to-player mapping where reliable.

## Phase 6 — Advanced state and automation

- Richer live state changes.
- Event/timeline tooling.
- Optional automated summaries.
- Production hardening and scale only when measurements justify it.

Phases may be reordered when implementation evidence requires it. Such changes
must be recorded in `DECISIONS.md` and `HISTORY.md`.

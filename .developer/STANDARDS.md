# Engineering Standards

## Principles

1. Correctness.
2. Security and information isolation.
3. Domain integrity.
4. Simplicity (KISS).
5. Maintainability (SOLID/DRY).
6. Testability.
7. Performance.
8. Optimization.

Apply these principles together rather than mechanically. Avoid speculative
abstractions and premature optimization.

## Core principles

- SOLID.
- KISS.
- DRY.
- Separation of Concerns.
- Dependency Inversion.
- Composition over Inheritance.
- Explicit over Implicit.
- Deterministic First.
- Domain Model First.
- Provenance First.
- Fail Closed.
- No AI Authority Without Explicit Permission.
- No Speculative Generalization.
- Evidence over Assumption.

## Python

PEP 8 is the default Python style standard and PEP 257 governs docstrings.
Use four-space indentation, snake_case names, explicit imports, type
annotations, and public docstrings. The project uses automated tooling to
prevent style drift.

## Database

Use foreign keys, unique constraints, check constraints, and deliberate indexes
where they protect domain invariants. All schema changes use Alembic.

## Security

Treat all user-provided content as untrusted. Campaign scope and knowledge
visibility are authorization concerns, not prompt instructions.

Do not log raw audio, secrets, or complete transcripts by default.

## AI

Use deterministic techniques first when they are sufficient. AI extraction
must retain provenance and confidence. AI-generated suggestions require an
explicit path to become canonical state.

## Application Layer

Application services are use-case oriented, not model-oriented.

Do NOT create a service class for every database model (e.g., no `UserService`,
`CampaignService`, `EntityService` just because those models exist).

Instead, create application services for meaningful use cases:

* `resolve_current_user` — maps external identity to local User
* `get_current_campaign` — verifies campaign ownership
* `ingest_document` — coordinates document parsing and persistence
* `create_entity` — creates entity with aliases and specialized data
* `extract_facts` — coordinates fact extraction and persistence
* `process_transcript` — realtime transcript processing pipeline

Rules:

1. Application services own use-case orchestration, not models.
2. Application services must not depend on FastAPI, WebSocket, or HTTP types.
3. Application services coordinate repositories and integrations.
4. Repositories handle persistence; application services handle workflows.
5. No formal Domain layer without demonstrated need.
6. Avoid "god services" — prefer small, cohesive modules/functions.
7. Classes only when state/dependencies/lifecycle require them.
8. Enforce immutable and enum-like fields in the schema and application layer, not only in the database. Reject an attempt to change an immutable field rather than ignoring it silently, so the client learns the change did not happen.

## Enforcing type and ownership invariants

When a resource is reachable through a parent that carries the authorization
scope, resolve the parent first and assert the type before touching the child.
For a specialized entity this means the campaign-scoped `EntityRepository` is
consulted before the specialization, so a cross-campaign identifier is a 404
and never reaches the child table.

Never widen a shared schema mixin to avoid composing two. Keep each mixin to
the fields that are genuinely common and compose the rest, so that inherited
fields are deliberate rather than incidental.
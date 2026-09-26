# Agent Instructions

## Required reading

Before changing code, read:

1. `.developer/GOALS.md`
2. `.developer/PHASES.md`
3. `.developer/TECHNOLOGIES.md`
4. `.developer/STRUCTURE.md`
5. `.developer/STANDARDS.md`
6. `.developer/DATABASE.md` when changing persistence or domain models
7. `.developer/DECISIONS.md` when making or evaluating architectural choices
8. `.developer/DOCUMENTATION.md` when changing documentation

Read existing code before modifying it. Do not assume that an older proposal,
conversation, or generated artifact is more authoritative than the repository.

## Non-negotiable architecture rules

- The domain model is the source of truth.
- AI output is never authoritative without explicit application logic and
  authorization.
- Prefer deterministic matching and validation before LLM or vector search.
- Keep HTTP/WebSocket transport separate from business logic.
- Keep external providers behind application interfaces.
- Do not add a graph database, Redis, Celery, Kubernetes, or microservices
  without an explicit documented decision.
- Do not add generic abstractions without a demonstrated use case.
- Preserve provenance for extracted knowledge.
- Preserve invalidated information for retcons; use `deleted_at` for deletion.
- Enforce campaign isolation in application queries and database constraints.
- Never expose a secret fact merely because an LLM might be able to filter it.
  Visibility must be enforced before model context is constructed.

## Coding standards

- Use Python 3.12+.
- Follow PEP 8 and PEP 257.
- Use type annotations for application code.
- Prefer small, cohesive modules and functions.
- Use dependency inversion at integration boundaries.
- Use SQLAlchemy 2.x and Alembic for persistence.
- Use Pydantic models at API boundaries.
- Never put SQL queries, prompt construction, AI provider calls, or domain rules
  directly in route handlers.
- Do not silently introduce new dependencies. Update `pyproject.toml` and
  `TECHNOLOGIES.md` when a dependency becomes architectural.

## Testing

Every behavior change should have tests at the lowest practical layer.
Business logic tests must not require a live LLM, STT provider, or network.
Database schema changes require an Alembic migration and corresponding tests
where behavior is affected.

## Documentation

Documentation is part of the implementation. Update the relevant `.developer`
document whenever an architectural, schema, technology, phase, or governance
decision changes.

Do not rewrite documentation merely to make it look current; keep historical
context in `HISTORY.md` and decisions in `DECISIONS.md`.

## Before finishing a change

Run the formatter/linter and test suite. Report anything that could not be run.
Do not claim tests passed unless they actually ran successfully.

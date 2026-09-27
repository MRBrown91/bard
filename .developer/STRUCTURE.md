# Repository Structure

```text
bard/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .developer/
│   ├── GOALS.md
│   ├── PHASES.md
│   ├── TECHNOLOGIES.md
│   ├── STRUCTURE.md
│   ├── STANDARDS.md
│   ├── TESTING.md
│   ├── DATABASE.md
│   ├── DECISIONS.md
│   ├── DOCUMENTATION.md
│   └── HISTORY.md
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── http/
│   │   │   ├── __init__.py
│   │   │   └── routes/
│   │   └── websocket/
│   │       ├── __init__.py
│   │       ├── routes/
│   │       └── handlers/
│   ├── core/
│   ├── database/
│   ├── models/
│   ├── schemas/
│   ├── application/
│   │   ├── __init__.py
│   │   ├── exceptions/
│   │   ├── users/
│   │   ├── campaigns/
│   │   ├── documents/
│   │   ├── entities/
│   │   ├── facts/
│   │   └── realtime/
│   ├── integrations/
│   │   └── auth/
│   └── repositories/
├── alembic/
├── tests/
└── devtools/test_console/
```

## Dependency direction

`api` and `realtime` are transport adapters. They call application services.
Application services depend on repositories and integrations.
Repositories implement persistence concerns. Integrations implement external provider interfaces.
Database models implement persistence concerns.

Transport code must not contain domain rules.
Application services must not depend on transport types (FastAPI, WebSocket).

## Naming

Use singular domain model names (`Campaign`, `EntityFact`) and plural database
relationship collections. Python modules use lowercase snake_case.

## Application Layer Organization

Application services are use-case oriented, not model-oriented:

* `app/application/users/` — User identity resolution
* `app/application/campaigns/` — Campaign ownership and access
* `app/application/documents/` — Document ingestion
* `app/application/entities/` — Entity creation and matching
* `app/application/facts/` — Fact extraction and invalidation
* `app/application/realtime/` — Live transcript processing
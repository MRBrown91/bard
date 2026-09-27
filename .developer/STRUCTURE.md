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

SQL queries live in repositories. ORM relationships are declared on models and
used by repositories, so the query shape stays in the persistence layer rather
than leaking into application services.

## Naming

Use singular domain model names (`Campaign`, `EntityFact`) and plural database
relationship collections. Python modules use lowercase snake_case.

## Entity composition

`Entity` is the identity root. Everything else that belongs to an entity hangs
off it through a one-way foreign key to `entities.id`, and is reached through
an ORM relationship declared on `Entity` rather than a hand-rolled join:

```text
Entity
├── actor / player / player_character       one-to-one, filtered on deleted_at IS NULL
├── location / item / faction               one-to-one, filtered on deleted_at IS NULL
├── aliases                                 one-to-many
├── facts                                   one-to-many
└── relationships_as_source / _as_target    one-to-many
```

The six specializations share the entity's UUID, so they are addressed by the
same `{id}` as the entity and live at flat sub-resource paths
(`/api/campaigns/{id}/actors/{id}`). They carry no `campaign_id`: a
specialized repository resolves the parent `Entity` through the
campaign-scoped `EntityRepository` and asserts the entity's type, so campaign
isolation is defined once (ADR-021).

Schema composition mirrors this. `EntityKeyMixin` carries only `entity_id`,
and a specialized read model composes it with the base entity embedded and no
timestamps of its own. The entity carries the canonical `created_at`, and a
second value from the specialization row would differ by a few milliseconds,
leaving a client to sort on the wrong one.

## Application Layer Organization

Application services are use-case oriented, not model-oriented:

* `app/application/users/` — User identity resolution
* `app/application/campaigns/` — Campaign ownership and access
* `app/application/documents/` — Document ingestion
* `app/application/entities/` — Entity creation, alias management, specialized entity CRUD, and matching
* `app/application/facts/` — Fact extraction and invalidation
* `app/application/realtime/` — Live transcript processing

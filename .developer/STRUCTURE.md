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
│   ├── core/
│   ├── database/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── realtime/
│   └── integrations/
├── alembic/
├── tests/
└── devtools/test_console/
```

## Dependency direction

`api` and `realtime` are transport adapters. They call application services.
Services depend on domain abstractions and repositories. Integrations implement
external provider interfaces. Database models implement persistence concerns.

Transport code must not contain domain rules.

## Naming

Use singular domain model names (`Campaign`, `EntityFact`) and plural database
relationship collections. Python modules use lowercase snake_case.

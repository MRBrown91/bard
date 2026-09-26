# Technologies

## Core

| Area | Choice | Reason |
|---|---|---|
| Language | Python 3.12+ | Strong AI/audio ecosystem and productive backend development. |
| HTTP | FastAPI | Async API and WebSocket support with typed boundaries. |
| ORM | SQLAlchemy 2.x | Mature relational mapping and explicit control. |
| Database | PostgreSQL | Relational integrity plus future vector support. |
| Vectors | pgvector | Keep relational and vector persistence together. |
| Migrations | Alembic | Explicit, reviewable schema evolution. |
| Validation | Pydantic v2 | API/configuration validation. |
| Auth | OIDC provider | Avoid custom credential management. |
| Tests | pytest | Standard, composable Python testing. |
| Quality | Ruff + mypy | Automated formatting/linting and type checking. |
| Client | Android/Kotlin/Compose | Planned future client. |

## Deliberately deferred

LangChain/LlamaIndex may be used behind application interfaces when they provide
real value. They are not architectural foundations.

Redis, Celery, graph databases, Kubernetes, dedicated vector databases, and
microservices are deferred until a measured requirement justifies them.

## External integration rule

STT, LLM, embedding, authentication, and future storage providers must be
accessed through application-level interfaces. Provider-specific details must
not leak into domain models.

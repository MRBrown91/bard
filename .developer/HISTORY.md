# History

## 2026-09-24 — Initial foundation

Created the first repository structure and documented the agreed architecture,
domain model, engineering standards, testing approach, and development phases.
Implemented the FastAPI application skeleton, SQLAlchemy domain models, initial
Alembic migration, WebSocket protocol skeleton, and developer test console.

## 2026-09-26 — PrePhase1 complete

**PrePhase1 foundation refactoring & schema fixes:**

* PP1.1: Split consolidated `app/models/domain.py` (394 lines, 21 models) into
  domain-cohesive modules under `app/models/` with `entity/entity_types/` subpackage.
* PP1.2: Added missing indexes and unique constraint on `entity_aliases(entity_id, alias)`.
* PP1.3: Changed 16 FK constraints to `ondelete="RESTRICT"` for provenance preservation.
* PP1.4: Created `app/repositories/` with 9 campaign-scoped repositories.
* PP1.5: Created Pydantic schemas in `app/schemas/` for all domain boundaries (10 modules).
* PP1.6: Implemented stub OIDC auth provider interface (`app/integrations/auth/`).
* PP1.7: Established explicit `app/application/` layer with:
  - `app/application/users/resolve_current_user` — external identity → local User
  - `app/application/campaigns/get_current_campaign` — campaign ownership check
  - `app/application/exceptions/` — application-level error types
  - FastAPI dependencies for auth, campaign scope, and repository injection
* Moved `app/services/` → `app/application/` for use-case oriented services
* Added comprehensive tests for auth, user resolution, and campaign scope
* All mypy checks pass, all tests pass
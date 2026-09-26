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

# Documentation Standards

## General

Documentation is versioned with the code and is part of the product's
engineering contract.

Use Markdown for repository documentation. Prefer short, focused documents over
one large design document.

## Structure

Every document should have:

1. A clear title.
2. A short purpose statement.
3. Headings that reflect the information hierarchy.
4. Concrete examples where ambiguity is likely.
5. No information that contradicts the implementation.

## Style

- Use complete sentences for prose.
- Prefer active voice.
- Use one idea per paragraph.
- Use tables for stable comparisons.
- Use fenced code blocks for code, schemas, and commands.
- Use Mermaid only when a diagram materially improves understanding.
- Avoid decorative prose.
- Avoid undocumented acronyms.

## Python documentation

Python source follows PEP 8 and PEP 257. Public modules, classes, functions,
and methods should have useful docstrings. Comments explain why, not merely
what the code visibly does.

## Architecture documentation

Changes to architecture, technology, database schema, development phases, or
engineering governance must update the relevant `.developer` document in the
same change.

## Decision records

Material architectural choices belong in `DECISIONS.md`. Do not hide important
tradeoffs only in source comments or chat history.

## Historical records

`HISTORY.md` records completed milestones and meaningful changes. It is not a
second changelog for every commit.

## Application Layer documentation

When adding application services, document:

1. The use case the service addresses.
2. The repositories/integrations it coordinates.
3. The error conditions it raises.
5. How it fits into the dependency chain (transport → application → repositories/integrations).
6. Test strategy (unit with doubles, integration with real DB).
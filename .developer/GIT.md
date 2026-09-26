# Git Practices & Branching Strategy

## Philosophy

- **Atomic commits**: One logical change = one commit. Enables `git bisect`, clean reverts, readable history.
- **Conventional Commits**: Machine-parseable messages for changelogs and tooling.
- **Phase-based feature branches**: Each phase (PrePhase1, Phase1A, etc.) is a feature branch merged to `main`.
- **Milestone tags**: Phase completion tagged for reproducible checkpoints (not releases).
- **Linear history on `main`**: Rebase feature branches, merge with `--no-ff` to preserve atomic commits + feature grouping.

---

## Branch Strategy

```
main ──────────────────────────────────────────────────────
  │
  ├── prephase1-foundation          (1 branch, 10 atomic commits)
  │     └── PR #1 → merge --no-ff → tag: prephase1-complete
  │
  ├── phase1a-campaigns             (1 branch, N atomic commits)
  │     └── PR #2 → merge --no-ff → tag: phase1a-complete
  │
  ├── phase1b-entities              (1 branch, N atomic commits)
  │     └── PR #3 → merge --no-ff → tag: phase1b-complete
  │
  ├── phase1c-documents             (1 branch, N atomic commits)
  │     └── PR #4 → merge --no-ff → tag: phase1c-complete
  │
  ├── phase1d-facts-events          (1 branch, N atomic commits)
  │     └── PR #5 → merge --no-ff → tag: phase1d-complete
  │
  ├── phase1e-entity-recognition    (1 branch, N atomic commits)
  │     └── PR #6 → merge --no-ff → tag: phase1e-complete
  │
  ├── phase1f-realtime              (1 branch, N atomic commits)
  │     └── PR #7 → merge --no-ff → tag: phase1f-complete
  │
  └── ... future phases
```

### Branch Naming
| Phase | Branch Name |
|-------|-------------|
| PrePhase1 | `prephase1-foundation` |
| Phase 1A | `phase1a-campaigns` |
| Phase 1B | `phase1b-entities` |
| Phase 1C | `phase1c-documents` |
| Phase 1D | `phase1d-facts-events` |
| Phase 1E | `phase1e-entity-recognition` |
| Phase 1F | `phase1f-realtime` |
| Future | `phase{X}{Y}-short-description` |

### Branch Lifecycle
1. Create branch from `main`: `git checkout -b phase1a-campaigns main`
2. Make atomic commits (see Commit Standards)
3. Push branch, open PR to `main`
4. CI must pass (ruff, mypy, pytest)
5. Self-review (solo) or peer review (team)
6. Rebase onto latest `main`: `git rebase main`
7. Merge with `--no-ff`: `git merge --no-ff phase1a-campaigns`
8. Tag milestone: `git tag phase1a-complete`
9. Delete branch: `git branch -d phase1a-campaigns`

---

## Commit Standards

### Atomic Commit Rule
**One logical change = one commit.**

| Logical Change | Commits |
|----------------|---------|
| Split domain models (PP1.1) | 1 commit (all new files + `__init__.py` updates + delete old) |
| Add missing indexes (PP1.2) | 1 commit (migration file) |
| Fix FK delete behavior (PP1.3) | 1 commit (migration file) |
| Add repository layer (PP1.4) | 1 commit (all repository files) |
| Add Pydantic schemas (PP1.5) | 1 commit (all schema files) |
| Add auth provider stub (PP1.6) | 1 commit (auth files) |
| Add auth dependencies (PP1.7) | 1 commit (dependencies + security) |
| Add visibility filter (PP1.8) | 1 commit (service + repo integration) |
| Reorganize API routes (PP1.9) | 1 commit (all moved/created files) |
| Add test console (PP1.10) | 1 commit (devtools files) |

**Do not** split a logical change across multiple commits (e.g., "create file A", "create file B", "update import").
**Do not** combine unrelated changes in one commit.

### Commit Message Format (Conventional Commits)

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

#### Types
| Type | Use For |
|------|---------|
| `feat` | New feature / capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior change |
| `chore` | Maintenance (deps, config, tooling) |
| `docs` | Documentation only |
| `test` | Test additions/changes |
| `migration` | Alembic migration only |

#### Scope
Use the **step ID** from implementation plans: `pp1.1`, `pp1.2`, `p1a.1`, `p1b.2`, etc.

#### Examples
```
feat(pp1.1): split domain models into cohesive modules

fix(pp1.3): change FK ondelete to RESTRICT for provenance preservation

feat(p1a.1): add campaign CRUD API with auth and campaign isolation

refactor(api): reorganize routes into http/websocket structure

migration(pp1.2): add unique constraint on entity_aliases(entity_id, alias)

chore(deps): update pyproject.toml for ruff 0.12

test(p1e.1): add unit tests for entity matching pipeline
```

#### Body (Optional)
Include when the change needs context:
```
feat(pp1.4): add repository base with campaign-scoped query pattern

Introduces BaseRepository with automatic campaign_id filtering.
All repositories inherit and receive campaign_id at construction.
Eliminates manual campaign scoping in service layer.
```

#### Footer (Optional)
For breaking changes or references:
```
BREAKING CHANGE: CampaignRead no longer includes deleted_at field

Refs: #123
```

---

## Tagging Strategy

### Milestone Tags (Phase Completion)
Format: `<phase>-complete`

| Tag | Meaning |
|-----|---------|
| `prephase1-complete` | All foundation refactoring done; ready for API development |
| `phase1a-complete` | Campaign & Session CRUD APIs working |
| `phase1b-complete` | Entity + Specialized Entity APIs working |
| `phase1c-complete` | Document + Statement APIs working |
| `phase1d-complete` | Fact/Relationship/Event APIs + sync working |
| `phase1e-complete` | Deterministic entity matcher + API working |
| `phase1f-complete` | Authenticated WebSocket + context pipeline working |

**Not releases** — internal checkpoints for `git checkout` / `git diff` / CI baselines.

### Release Tags (Future)
When a deployable version exists:
```
v0.1.0          # First deployable (end of Phase 1?)
v0.2.0          # Phase 2 feature set
v1.0.0          # Production-ready
```

Use semantic versioning. Milestone tags remain for history.

---

## Main Branch Protection

### Current (Solo / AI-Assisted)
- Direct pushes to `main` **allowed** for trivial fixes (typo, config)
- All phase work via feature branch + PR
- Linear history via rebase + `--no-ff` merge
- No force-push to `main`

### Future (Team)
- Require PR for all changes to `main`
- Required status checks: `ruff`, `mypy`, `pytest`
- Require 1 approval
- Dismiss stale reviews on new commits

---

## CI Requirements (GitHub Actions)

Every PR must pass:
```yaml
# .github/workflows/ci.yml (to be created)
jobs:
  lint: ruff check .
  typecheck: mypy app/
  test: pytest --tb=short
```

Run locally before pushing:
```bash
ruff check . && mypy app/ && pytest
```

---

## AI-Assisted Commit Discipline

When the AI agent makes changes:
1. **Group related edits** into one logical commit
2. **Write meaningful message** — not "update files" or "fix bug"
3. **Stage and commit** each logical change separately
4. **Verify** `ruff check . && mypy app/ && pytest` before each commit

Example workflow for PP1.1:
```bash
# AI creates all new model files, updates __init__.py, deletes domain.py
git add app/models/
git commit -m "feat(pp1.1): split domain models into cohesive modules"

# AI creates migration for PP1.2
git add alembic/versions/xxxx_add_missing_indexes.py
git commit -m "migration(pp1.2): add missing indexes and unique constraint"
```

---

## Quick Reference

| Action | Command |
|--------|---------|
| Start new phase | `git checkout -b phase1a-campaigns main` |
| Atomic commit | `git add <files> && git commit -m "feat(pp1.1): ..."` |
| Rebase before PR | `git fetch origin && git rebase origin/main` |
| Merge to main | `git checkout main && git merge --no-ff phase1a-campaigns` |
| Tag milestone | `git tag phase1a-complete && git push origin phase1a-complete` |
| View phase history | `git log --oneline prephase1-complete..phase1a-complete` |
| Bisect regression | `git bisect start main prephase1-complete` |

---

## Related Documents

- `.developer/implementation/PrePhase1.md` — Atomic steps with commit mapping
- `.developer/implementation/Phase1.md` — Phase 1 steps with commit mapping
- `.developer/DECISIONS.md` — Architectural decisions (ADRs) referenced in commits
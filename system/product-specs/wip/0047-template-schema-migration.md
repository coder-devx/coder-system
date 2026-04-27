---
id: '0047'
title: Template schema migration
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ['0047']
related_specs:
  - knowledge-api
  - onboarding
  - admin-panel
  - audit-log
---

# 0047 — Template schema migration

## Problem

`coder-system/template/` is the source-of-truth blueprint that
every project's knowledge repo is forked from at onboarding time
(see `onboarding` spec). When the template gains a new required
field, renames a field, splits a field into two, or shifts a value
from one frontmatter key to another, every existing project's repo
needs to adopt the change. Today there is no path for that.

The realised pain points:
- Adding `last_verified_at` (spec 0043, shipped 2026-04-18)
  required a one-off backfill script
  (`scripts/backfill_last_verified.py`) and a coordinated PR per
  managed project. The `coder-system` and the two managed
  projects (`vibetrade`, `coder`) needed three separate PRs that
  all had to land within one CI window because the new field
  was added as required to the validator at the same time.
- The 0044 ship endpoint (knowledge-write-api) explicitly
  refuses any `/ship` call whose touched paths include
  `template/` ("rejected with a pointer to the template-
  migration path") — meaning template changes can't ride the
  normal pipeline today; they must be hand-curated.
- A future schema change (e.g. renaming `affects_services` to
  `relates_to_services`, or adding a required `criticality`
  field on services) has no automated path. The realistic
  outcome is "we don't make the change," which means the
  template ossifies and the knowledge model can't evolve.

What's missing is a regular, reviewed mechanism: a numbered
migration written once, registered in `coder-system/`, applied
exactly once per managed project as a PR a human reviews. The
same shape AGENTS.md uses for SQL migrations (one file per
change, ordered, applied tracked) but for knowledge-repo
frontmatter and folder structure.

## Users

- **Schema author** (typically the operator shepherding a
  template change) — writes one migration file in
  `coder-system/migrations/knowledge/00NN-<slug>.py` (or `.yaml`
  for declarative cases), commits it, and the per-project
  application is automated. Doesn't touch any project repo
  directly.
- **Per-project reviewer** — gets one PR per project per
  migration titled `template-migration: 00NN-<slug>` against
  the project's knowledge repo. Reviews exactly the diff the
  migration produced. Approves or asks for revision via the
  normal PR flow.
- **Onboarding operator** — when onboarding a new project, the
  fresh fork from `template/` carries the latest
  `template_version` so no prior migrations need to apply.
  Onboarding doesn't change.
- **Knowledge API** — gains a no-op behaviour: artifacts whose
  schema version doesn't match the current validator return
  `409 SCHEMA_DRIFT` for `min_schema_version=current` callers
  (mirroring how 0043's `min_freshness` works), so a worker can
  refuse to act on a pre-migration artifact if it knows the
  shape changed.

## Goals

- **One migration, N PRs.** A migration file lands once in
  `coder-system/`. The migrator job opens one PR per managed
  project per pending migration. Single source of truth for
  the schema change; per-project diffs are derived, never
  hand-authored.
- **Reversible by review.** Every migration produces a PR a
  human merges. There is no path that writes to a project's
  `main` without a human merge. A migration with a buggy
  transformation surfaces as a flagged PR, not silent damage.
- **Idempotent at the project level.** A project carries
  `template_version` (in `repos.yaml` at the repo root, see
  scope). Re-running the migrator is safe: it skips migrations
  whose number ≤ project's recorded version, and any migration
  that has an open PR is also skipped (we don't open duplicates).
- **Composable with the freshness + write-through machinery.**
  Migrations can update `last_verified_at` only when explicitly
  asked (default: leave the date alone — a migration is a schema
  change, not a fact verification). They never silently bump
  freshness on the operator's behalf.
- **Small enough to review.** A migration's PR diff is bounded
  by `template_migration_max_files_per_pr` (default 50). A
  larger migration auto-splits into batched PRs (`-1`, `-2`...)
  rather than producing an unreviewable mega-PR.

## Non-goals

- **Migrating data inside artifact bodies.** A migration touches
  frontmatter fields and folder/file shape. It does not rewrite
  the markdown body. Body content evolution is human or
  architect-worker work, not migrator work.
- **Migrating ADRs.** ADRs are append-only by contract
  (`knowledge-repo-model` design's invariants). A migration that
  tries to rewrite an ADR fails fast at registration time. If a
  schema field needs to change on ADRs going forward, the
  migration adds it to `template/adrs/_TEMPLATE.md` for new
  ADRs and the existing ADRs are exempt — same way
  `last_verified_at` is exempt for ADRs in 0043.
- **Cross-template migrations.** v1 migrates one template
  schema across all managed projects. There's no per-project
  template variant.
- **Auto-merging migration PRs.** Even with high static
  confidence (a pure-rename migration), the migration PR is not
  eligible for 0040 auto-approval. Schema changes are
  consequential — a human merges.
- **Backfilling content.** A migration can declare "compute the
  default value for new field `X` from existing field `Y`" via
  a transformation function, but it cannot say "go look up the
  truth in some external system." Migrations are pure functions
  over the project repo's current state.
- **Replacing the `coder-system` repo's CI validator.** The
  migrator updates project repos; the `coder-system` repo's own
  schema is updated by hand in the same PR that adds the
  migration file, since `coder-system` is its own knowledge
  repo (see `knowledge-repo-model`).

## Scope

### In scope — migration file format

`coder-system/migrations/knowledge/00NN-<slug>.py` is a Python
module exporting a uniform shape:

```python
NUMBER = 47
SLUG = "add-criticality-to-service"
DESCRIPTION = "Add required criticality field to all service artifacts."

# Optional — bumps the project's template_version after this
# migration applies. Default: NUMBER.
TARGET_VERSION = 47

# Optional — set true if the migration touches more files than
# the per-PR cap allows; the runner will batch into multiple PRs.
ALLOW_BATCHING = True

# Optional — explicit affects list. If omitted, the framework
# infers from any folder traversed by `migrate(...)`.
AFFECTS = ["services"]

def migrate(repo: KnowledgeRepoView) -> list[FileChange]:
    changes = []
    for service in repo.list("services"):
        fm = service.frontmatter
        if "criticality" in fm:
            continue  # idempotent — already migrated
        fm["criticality"] = _infer_criticality(fm)
        changes.append(FileChange(
            path=service.path,
            new_frontmatter=fm,
            new_body=service.body,  # unchanged
            reason=f"add criticality={fm['criticality']!r}",
        ))
    return changes

def _infer_criticality(fm: dict) -> str:
    return "high" if fm.get("tier") == "core" else "standard"
```

A declarative variant `.yaml` covers the most common case
(rename a key everywhere; add a key with a constant default;
move a folder) without requiring Python:

```yaml
number: 48
slug: rename-affects-services-to-relates-to-services
description: Rename affects_services → relates_to_services across designs and ADRs.
target_version: 48
affects: [designs, adrs]
operations:
  - kind: rename_frontmatter_key
    in_types: [design, adr]
    from: affects_services
    to: relates_to_services
```

The `migrations/knowledge/` folder gets its own `_TEMPLATE.py`
+ `_TEMPLATE.yaml` showing the shape.

### In scope — `template_version` storage

Each project's knowledge repo gains a `template_version: N`
field at the top of `repos.yaml` (which already exists in the
template — see `template/system/`). The `coder-system` repo's
own `system/repos.yaml` carries the **current** version (the
highest migration number in `migrations/knowledge/`). The
migrator job:

1. Scans `coder-system/migrations/knowledge/` for migration
   files; computes `current_version = max(NUMBER)` across them.
2. For each managed project (via the project registration list):
   - Reads `system/repos.yaml` from the project's knowledge
     repo, extracts `template_version`. If absent, treats as
     `0` (migration 1+ all need to apply).
   - For each migration with `NUMBER > project.template_version`:
     - Loads the project's repo into an in-memory
       `KnowledgeRepoView`.
     - Runs `migrate(view)` (or executes the YAML operations).
     - Collects the returned `FileChange[]`.
     - If empty (no-op for this project — e.g. project has no
       services and the migration touches services only),
       record a no-op acknowledgement that bumps
       `template_version` directly via a small one-line PR
       (or a tiny commit if the project's repo policy
       permits — see open questions).
     - Else, batch into PR-sized chunks and open one PR per
       batch titled
       `template-migration: 00NN-<slug>` (suffix `-2`, `-3`
       on subsequent batches).
3. The PR body lists the migration's `DESCRIPTION` + the
   per-file change reasons + the new `template_version` the
   `repos.yaml` will bump to on merge.

### In scope — KnowledgeRepoView SDK

The Python migration files import from
`coder_core.migrations.knowledge`:

```python
from coder_core.migrations.knowledge import (
    KnowledgeRepoView,  # read-only snapshot of one project's repo
    FileChange,         # one frontmatter+body change to land
    DeleteFile,         # path-only delete (e.g. folder rename)
    MoveFile,           # source → dest move
    RegistryRewrite,    # explicit registry rewrite hook
)
```

The view exposes `list(type) -> Iterable[Artifact]`, `get(type,
id) -> Artifact | None`, `iter_files(folder) -> Iterable[Path]`
for the rare migration that needs to walk arbitrary files (not
just registered artifacts).

`FileChange / MoveFile / DeleteFile` carry only the intent. The
runner is responsible for: rewriting the affected
`registry.yaml` if any `id`/`status`/`folder` field touched
its registry-relevant attributes; constructing the Git Trees
commit; opening the PR. The migration code never reaches for
GitHub directly.

### In scope — runner job

A new Cloud Run Job `coder-core-template-migrate` (oneshot,
also schedulable on a weekly cadence to catch newly-added
migrations after a `coder-system` merge):

- Args: `--migration-numbers 47,48` (default: all
  pending across the fleet) + `--projects coder,vibetrade`
  (default: all managed).
- Per project per migration: enforces idempotency via
  `template_migrations` table (migration 0055):
  `(project_id, migration_number, status, opened_pr_url,
  merged_at, error_kind, error_detail)`. A row exists once an
  attempt starts; a `status='pr_open'` row blocks further
  attempts on the same `(project, migration)` pair (idempotency
  for re-runs).
- One Git Trees commit per batch (atomic — same commit shape as
  `/ship` from 0044).
- Concurrent migrations on the same project serialise on
  `(project_id)` advisory lock; we don't open two pending PRs
  on the same repo at the same time even if migrations 47 and
  48 are both pending — they're sequential by number.
- Each migration application emits an `audit_events` row
  (`action='template_migration.opened_pr' | '.failed'`).

### In scope — Knowledge API integration

- `GET /v1/projects/{id}/knowledge/{type}/{artifact_id}` gains
  an optional `?min_schema_version=N` query param. Returns
  `409 SCHEMA_DRIFT` if the artifact's project's
  `template_version < N`. Body of the 409 carries the artifact
  + a `pending_migrations: [...]` list pointing at the
  numbers + slugs the project hasn't applied yet. Default:
  unset (legacy 200 behaviour).
- New endpoint `GET /v1/projects/{id}/template/version` returns
  `{template_version, current_version, pending: [...]}`. Used
  by admin panel + worker fall-back checks.
- New admin endpoint `GET /v1/_admin/template/migrations`
  returns the fleet-wide migration matrix:
  `[{project_id, template_version, pending_count,
  oldest_pending_pr_age, last_attempted_at, last_error}]`.

### In scope — admin surface

- `/admin/template-migrations` page renders the fleet matrix:
  one row per project, columns = each migration number with a
  status pill (✓ merged / ⚠️ PR open / ✗ failed / ○ pending).
  Click a cell → migration detail panel showing PR URL,
  per-file change reasons, runner output. Behind
  `VITE_TEMPLATE_MIGRATIONS_ENABLED`.
- Per-project tab `/projects/:id/template-migrations` shows
  the same row filtered to one project.

### In scope — runbook

`system/runbooks/template-migration.md` (new): how to author a
migration (Python vs YAML decision; idempotency requirements;
how to test against a synthetic repo with the new
`coder migrate test --against ./fixture-repo` CLI command); how
to roll one out (merge to `coder-system`, the runner picks it up
on next tick, monitor the admin page, expect PRs to open within
~10 min); how to handle a failed application (the
`template_migrations` row carries the `error_detail`, fix the
migration, bump its number, re-run); how to revert (mergeable
revert PR is the standard path; a migration with a destructive
operation should ship with a paired reversal migration).

### Out of scope

- **Live transformations on read.** We don't transform
  pre-migration artifacts on-the-fly at API read time (that
  would silently mask drift). 409 SCHEMA_DRIFT is the explicit
  signal.
- **Cross-managed-project migrations** (e.g. "move artifact X
  from project A to project B"). Not a thing.
- **Renaming a folder that the AGENTS.md contract names by
  string.** AGENTS.md and CLAUDE.md reference specific folder
  names (`active/`, `wip/`, `deprecated/`). A migration that
  renames one of those is outside scope; the framework refuses
  with a clear error. Such a change requires a coordinated
  AGENTS.md + framework code change first.
- **Migrating the `coder-system` repo itself via the runner.**
  `coder-system` is updated by the human author of the
  migration in the same PR — that PR includes the
  `migrations/knowledge/00NN-...py` file AND the corresponding
  `system/` updates AND a `system/repos.yaml`
  `template_version` bump. The runner only operates on
  managed projects. (This is the same self-hosting boundary as
  ADR 0008's CI validator.)

## Acceptance criteria

- **AC1.** `coder-system/migrations/knowledge/` folder exists
  with `_TEMPLATE.py`, `_TEMPLATE.yaml`, and `0001-baseline.py`
  (a no-op migration that records `template_version=1` for any
  project at version 0). Migration files are validated by CI:
  unique `NUMBER`, present `SLUG` and `DESCRIPTION`, importable
  Python or schema-valid YAML.

- **AC2.** Each managed project's knowledge repo carries
  `template_version: N` at the top of `system/repos.yaml`. The
  `coder-system` repo's own `system/repos.yaml` carries the
  current version. Onboarding (spec `onboarding`) seeds new
  projects with `template_version: <current>` so they have
  nothing pending on day one.

- **AC3.** Cloud Run Job `coder-core-template-migrate` exists,
  invoked oneshot via `POST /v1/_admin/template/migrate`
  (admin auth) or by Cloud Scheduler weekly. Args:
  `--migration-numbers` and `--projects` (both optional,
  defaults documented in scope).

- **AC4.** `template_migrations` table (migration 0055)
  records every attempt:
  `(project_id, migration_number, status: pending|pr_open|merged|failed,
   opened_pr_url, merged_at, error_kind, error_detail,
   batch_index, total_batches)`. Unique on
  `(project_id, migration_number, batch_index)`.

- **AC5.** Per-PR file cap: any migration whose
  `FileChange[]` count exceeds
  `template_migration_max_files_per_pr` (default 50) and that
  has `ALLOW_BATCHING=True` opens multiple PRs (`-1`, `-2`...);
  one without `ALLOW_BATCHING` and over the cap fails the run
  with a clear error and **doesn't open a partial PR**.

- **AC6.** `template_version` bump rides the merge: the PR
  includes a `system/repos.yaml` edit setting
  `template_version` to `migration.TARGET_VERSION` (defaults
  to `migration.NUMBER`). On batched migrations, only the
  final batch's PR carries the version bump; earlier batches
  carry comments noting "version bump in batch N/N." Merging
  out of order leaves the project at an intermediate state but
  with a clear path forward.

- **AC7.** `GET /knowledge/{type}/{id}?min_schema_version=N`
  returns `409 SCHEMA_DRIFT` with `pending_migrations[]` in
  the body when the project's `template_version < N`. Default
  legacy behaviour (no param) preserved.

- **AC8.** `GET /v1/projects/{id}/template/version` returns
  `{template_version, current_version, pending: [{number, slug,
  description}]}`. Per-project auth.

- **AC9.** Admin `/admin/template-migrations` page renders the
  fleet matrix behind `VITE_TEMPLATE_MIGRATIONS_ENABLED`. Each
  cell links to the PR (if open) or the merged commit (if
  merged) or shows the error detail (if failed).

- **AC10.** Audit: every state change writes an
  `audit_events` row
  (`action='template_migration.{started,opened_pr,merged,failed}'`)
  with `target_type='template_migration'`,
  `target_id='<project_id>:<migration_number>:<batch_index>'`.

- **AC11.** Runbook `system/runbooks/template-migration.md`
  documents authoring, applying, monitoring, reverting, and
  the `coder migrate test --against ./fixture-repo` CLI
  smoke-test command.

- **AC12.** Flag-gated fleet-wide on
  `CODER_TEMPLATE_MIGRATIONS_ENABLED` (default off on first
  deploy). Per-project escape hatch
  `projects.template_migrations_enabled` (NULL = inherit
  fleet, tri-state).

## Metrics

- **Mean time from migration merged-to-coder-system → all
  project PRs merged** — the headline KPI. Tracks how long a
  schema change takes to fully roll across the fleet. Target:
  ≤ 1 week median.
- **Migration failure rate per migration** — count of
  `template_migrations.status='failed'` rows per migration
  number. > 0 on a migration is a code-quality signal: the
  migration's `migrate()` raised on a real project's data.
- **PR-open age** — time since `opened_pr_url` set without a
  `merged_at`. > 14 days flags an abandoned migration PR for
  the operator queue.
- **Per-project pending count** — count of pending migrations
  per project, on the admin matrix. Watch for projects that
  are persistently behind (signals an unhealthy
  reviewer-availability situation, not a migrator bug).
- **Schema-drift 409 rate** — count of `409 SCHEMA_DRIFT`
  responses on `?min_schema_version=` callers per project per
  week. High rate = workers are increasingly demanding the
  current schema and the project is increasingly behind;
  prioritises merging the pending PRs.

## Decisions

Resolved 2026-04-27 ahead of architect dispatch.

- **No-op migrations bump `template_version` via a one-line
  `system/repos.yaml` PR.** Preserves the symmetry that every
  migration goes through review. The faster alternative
  (direct commit to a no-op branch the runner fast-forwards)
  violates "no path writes to `main` without a human merge"
  and is rejected.
- **`coder migrate test` synthetic fixtures live in
  `coder-system/migrations/_fixtures/`.** Hand-curated
  edge-case projects (large, small, missing-folder, repos with
  unusual layouts). Testing against `template/` snapshot alone
  misses real-project variance. Initial fixtures land
  alongside the `0001-baseline.py` migration in Stage 1.
- **Concurrent migration ordering — sequential per-project.**
  If 47 and 48 land back-to-back in `coder-system`, the runner
  opens 47's PR per project; only after it merges does 48's
  PR open. Slower for fast-following migrations but bounds the
  reviewer queue and keeps intermediate states one-at-a-time.
  Other projects independently sequence on their own
  `(project_id)` advisory lock.
- **Failed-migration recovery — strict per-project ordering.**
  If 47 fails on project A, A stays at `template_version=46`
  until A's 47-migration PR lands. Meanwhile 48 can still
  apply on project B (the failure is per-project, not fleet).
  Fleet-wide inconsistency is visible on the admin matrix;
  operator intervention (re-issuing the migration with a new
  number once the bug is fixed) closes it. **Failed rows are
  terminal** — re-running 47 against A is not the recovery
  path; writing 49 with the corrected logic is.
- **Renames + cross-link integrity — alias-tolerance window
  in the validator.** ADR 0008's CI validator gains an
  alias-tolerance mechanism: a `rename_frontmatter_key`
  migration declares the alias at the same time the migration
  lands; the validator accepts both `from` and `to` field
  names while any project is below the migration's
  `template_version`; the alias auto-removes once the admin
  matrix shows fleet-wide adoption. **This is pre-work for
  any rename migration** — a small validator change must land
  before Stage 5 if the first real migration is a rename.
  See 0047 design's rollout for the alias-tolerance ship
  ordering. (If the first real migration is purely additive,
  alias-tolerance can ship later.)
- **`glossary.md` — SDK exposes it via `iter_files('glossary')`.**
  Single file, not a registered artifact, but migrations may
  need to touch it (e.g. add a frontmatter key). The SDK's
  `iter_files` pattern handles it explicitly so a
  glossary-touching migration doesn't surprise.

## Open questions

_None — all resolved. See Decisions above._

## Links

- Related specs:
  [knowledge-api](../active/knowledge-api.md),
  [onboarding](../active/onboarding.md),
  [admin-panel](../active/admin-panel.md),
  [audit-log](../active/audit-log.md),
  [0044 (write-through enforcement)](../active/knowledge-api.md#evolution)
- Design: [0047](../../designs/wip/0047-template-schema-migration.md)
- Roadmap entry: [ROADMAP.md](../ROADMAP.md) → Phase 8 / 0047

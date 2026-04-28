---
id: '0047'
title: Template schema migration
type: design
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-28
last_verified_at: 2026-04-28
implements_specs: ['0047']
decided_by: ['0019', '0020', '0021']
related_designs:
  - knowledge-write-api
  - knowledge-repo-model
  - audit-log
  - system-overview
  - worker-communication
  - '0052'
affects_services:
  - coder-core
  - coder-admin
affects_repos:
  - coder-core
  - coder-system
---

# 0047 — Template schema migration

## Context

Spec 0047 ships a sanctioned path for evolving `coder-system/template/` and
rolling the change across every managed project's knowledge repo. A schema
author writes one migration file in
`coder-system/migrations/knowledge/00NN-...py` (or `.yaml` for declarative
cases); a Cloud Run Job `coder-core-template-migrate` applies any pending
migration to each managed project as a reviewed PR; a `template_migrations`
table tracks status; a per-project `template_version` field at the top of
`system/repos.yaml` records what has been applied.

This design was first drafted 2026-04-19 and is now sealed as of 2026-04-28
following spec seal on 2026-04-27. The sections below supersede the earlier
draft in full. Open questions from the draft are resolved here; ADRs 0019,
0020, and 0021 record the non-obvious decisions.

This design does not cover: the SPA admin page for migration runs (tracked
separately), auto-detection of needed migrations on schema bump (Stage 2), or
concrete first migrations beyond the worked example stub.

## Goals / non-goals

**Goals**

- Reuse 0044's Git Trees atomic-commit machinery — no new GitHub write path.
  The migrator builds a single tree per batch and pushes it as one commit on a
  branch; only the PR merge writes to `main`.
- Reuse the existing CI validator (ADR 0008) on the project repo's migration
  PR — a failed validation means the migration itself is buggy.
- Make the SDK pure: migration files receive a read-only view and return a
  list of intent objects. They never reach for GitHub, the database, or the
  cache. Testable in-process with a fixture repo.
- Strict per-project ordering: migrations apply to a project in number order;
  failure of N blocks N+1 on that project; other projects are independent.
- Alias-tolerance pre-work: any rename migration must register
  `VALIDATOR_ALIASES` so the CI validator accepts both old and new field names
  while the fleet is mid-migration. This ships before the first rename
  migration (Stage 5 pre-condition per spec roadmap).

**Non-goals**

- Live-transform pre-migration artifacts on API reads. Pre-migration artifacts
  are returned as-is; `?min_schema_version=N` callers get `409 SCHEMA_DRIFT`.
- Migrating ADRs (append-only invariant, per knowledge-repo-model design).
- Auto-merging migration PRs, even for pure-rename migrations (spec non-goal).
- Migrating `coder-system` itself via the runner (author updates it by hand in
  the same PR that adds the migration file).

## Design

```mermaid
flowchart TB
  author["Schema author"] -->|commit migration file\n+ optional VALIDATOR_ALIASES| sysrepo[(coder-system repo)]
  sysrepo -->|merge → Cloud Scheduler weekly\nor admin POST| trigger["POST /v1/_admin/template/migrate\n→ dispatch Cloud Run Job"]
  trigger --> runner["Cloud Run Job\ncoder-core-template-migrate"]
  runner -->|per project per migration| advisory["pg advisory lock\nhash(project_id)"]
  advisory --> pre["Preflight:\nread project repos.yaml,\ncompute pending,\ncheck template_migrations table"]
  pre --> sdk["SDK: KnowledgeRepoView\nin-memory tree snapshot"]
  sdk --> migrate["migration.migrate(view)\nor YAML interpreter"]
  migrate -->|FileChange[] / MoveFile / DeleteFile| batcher["Batcher\n≤ max_files_per_pr = 50"]
  batcher -->|per batch| trees["build_and_push_tree\n(shared with 0044 /ship)"]
  trees -->|branch template-migration/00NN-slug-bK| pr["Open PR\ntemplate-migration: 00NN-slug"]
  pr -->|insert row status=pr_open| db[("template_migrations\n(migration 0055)")]
  pr -.->|merge triggers| action["record-template-migration.yml\n(0052 managed workflow)"]
  action -->|POST merged callback| merged["PATCH row → status=merged\nbump repos.yaml template_version"]
  db -->|counters| obs["Prometheus metrics\naudit_events"]
```

### Schema change taxonomy

Each change kind has different backward-compatibility requirements during the
migration window (between when the migration lands in `coder-system` and when
every managed project has merged the migration PR).

| Change kind | Example | Alias-tolerant? | Migration kind | Backward-compat during window |
|---|---|---|---|---|
| **Field add with default** | Add `criticality: standard` to services | Yes — additive | Single `add_frontmatter_key_with_default` | Pre-migration artifacts lack the field; validator marks field optional until fleet-sealed; API returns 409 SCHEMA_DRIFT if caller passes `min_schema_version` ≥ this migration's TARGET_VERSION |
| **Field rename** | `affects_services` → `relates_to_services` | Yes — with VALIDATOR_ALIASES | Single `rename_frontmatter_key` + `VALIDATOR_ALIASES = {"affects_services": "relates_to_services"}` | Validator accepts both names while any project is below TARGET_VERSION (ADR 0019); cross-link checker resolves both names; API returns whatever name is in the file — no on-the-fly normalisation |
| **Field remove** | Drop deprecated `tier` field | Two migrations (ADR 0021) | Migration N: `DEPRECATED = ["tier"]` — validator emits warning on presence but doesn't fail; migration M > N: `remove_frontmatter_key` removes it | During deprecation window (migration N → M), old field tolerated with warning; API ignores the field for schema-version checks; after migration M, field in artifact is a CI validation error |
| **Enum value rename** | `status: draft` → `status: wip` | Yes — with VALIDATOR_ALIASES | Single `rename_frontmatter_value` + `VALIDATOR_ALIASES` on the enum key | Validator accepts both enum values during window; migration PR replaces old value with new |
| **Type change (str → list)** | `owner: "ro"` → `owners: ["ro"]` | No — rename + reshape | Two-step: (1) add new list field with derived default, (2) remove old str field | No alias for a type change; validator must accept old type until fleet adoption; migration coerces the value in the PR diff |

All change kinds share these invariants during the migration window:

- `GET /knowledge/{type}/{id}?min_schema_version=N` returns `409 SCHEMA_DRIFT`
  with `pending_migrations: [...]` if the project's `template_version < N`.
- Default reads (no `min_schema_version`) always succeed with the artifact's
  current on-disk representation — no silent coercion.

### Migration trigger — Cloud Run Job (ADR 0020)

`POST /v1/_admin/template/migrate` (admin auth) dispatches the Cloud Run Job
`coder-core-template-migrate` and returns `{run_id, scheduled_jobs: N}`
immediately. The endpoint does NOT run migrations inline. Cloud Scheduler
also fires this endpoint weekly with no filters (full fleet, all pending).

The sync-only alternative (run migrations inside the API handler) was rejected:
long-running migrations hitting 50 files × N GitHub API calls would timeout
and leave partial `template_migrations` rows in `status='pending'`. See ADR
0020 for the full decision record.

Optional args `{migration_numbers?: [N], projects?: [slug], dry_run?: bool}`:

- `migration_numbers`: restrict to specific migration numbers (default: all pending)
- `projects`: restrict to specific project slugs (default: all managed)
- `dry_run`: compute and return the `FileChange[]` per project per migration
  without opening PRs or writing DB rows (useful for schema author validation
  against live project data, complementing the local `coder migrate test` CLI)

### Migration metadata — `template_migrations` table

Migration 0055 creates:

```sql
CREATE TABLE template_migrations (
  project_id        TEXT        NOT NULL REFERENCES projects(id),
  migration_number  INTEGER     NOT NULL,
  batch_index       INTEGER     NOT NULL DEFAULT 1,
  total_batches     INTEGER     NOT NULL DEFAULT 1,
  status            TEXT        NOT NULL CHECK (status IN
                      ('pending','pr_open','merged','failed','abandoned')),
  opened_pr_url     TEXT,
  opened_pr_number  INTEGER,
  branch_name       TEXT,
  merged_at         TIMESTAMPTZ,
  merge_commit_sha  TEXT,
  error_kind        TEXT,  -- migrate_raised | github_upstream | forbidden_path | parse_error | suspicious_noop
  error_detail      TEXT,  -- full traceback or description
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, migration_number, batch_index)
);
CREATE INDEX ON template_migrations (status, project_id);
CREATE INDEX ON template_migrations (migration_number, status);
```

A row is inserted with `status='pending'` when the runner begins processing a
`(project, migration, batch_index)` tuple, before any GitHub API call. This
makes the row the authoritative idempotency key: a second runner invocation
sees the row and skips.

The registry of migrations is the filesystem: `coder-system/migrations/knowledge/`
contains the authoritative list. No separate database table maps migration
metadata — the migration files themselves are the registry (similar to SQL
migration files). The `template_migrations` table records *execution* state,
not migration *definitions*.

Migration 0056 adds the per-project flag:

```sql
ALTER TABLE projects ADD COLUMN template_migrations_enabled BOOLEAN NULL;
-- NULL = inherit fleet flag; TRUE = enabled; FALSE = disabled (tri-state)
```

### Alias-tolerance read path

A rename migration declares:

```python
VALIDATOR_ALIASES = {"affects_services": "relates_to_services"}
```

The registration CI validator on `coder-system` extracts `VALIDATOR_ALIASES`
from every migration file and writes them into a generated file
`coder-system/system/migrations/validator-aliases.yaml`:

```yaml
aliases:
  - migration_number: 48
    from: affects_services
    to: relates_to_services
    retired_at: null  # set when fleet_adoption_pct = 100
```

ADR 0008's `scripts/validate.py` reads `validator-aliases.yaml` at startup.
While `retired_at` is null for an alias, the validator:
- Accepts both `from` and `to` names as valid keys in frontmatter
- Resolves cross-link lookups against both names

**Deprecation window length** (ADR 0019): The alias window closes when the
fleet matrix shows 100% adoption — all managed projects have
`template_version >= migration.TARGET_VERSION`. The runner sets `retired_at`
in `validator-aliases.yaml` via a `coder-system` PR once fleet-sealed, not on
a fixed calendar deadline. A fixed deadline would break a slow-merging
project's CI on any unrelated PR; the fleet-completion gate ties alias removal
to the observable fact that every project adopted the rename.

The Knowledge API's read path does NOT normalise alias fields. A project whose
artifacts still carry `affects_services` will return `affects_services` in API
responses until the migration PR merges. Workers that need the new name should
either: (a) call `GET /v1/projects/{id}/template/version` and confirm
`template_version >= N` before assuming the new name, or (b) tolerate both
names in their own parsing.

### Migration runner

**`coder_core/migrations/knowledge/runner.py`** — Cloud Run Job entry point.

Per `(project, migration)` pair, the runner:

1. **Preflight.** Reads `system/repos.yaml` from the project's knowledge repo,
   extracts `template_version`. Computes `pending = [m for m in migrations if
   m.NUMBER > project.template_version]` ordered by NUMBER. Takes only the
   smallest pending NUMBER (strictly sequential — migration N+1 waits until N
   merges, per spec invariant).

2. **Idempotency check.** Queries `template_migrations` for any row at
   `(project, migration_number)` with `status IN ('pr_open','merged')`. If
   present, skips. If `status='failed'` or `status='abandoned'`, also skips —
   failed rows are terminal until the author ships a corrected migration with a
   new number.

3. **Advisory lock.** `SELECT pg_try_advisory_xact_lock(hash(project_id))` —
   concurrent runner invocations don't both process the same project.

4. **Snapshot.** Fetches the project repo's `main` ref SHA. Lazily fetches
   only the tree paths declared in `migration.AFFECTS` (or inferred from
   `in_types` for YAML migrations). Constructs an in-memory
   `KnowledgeRepoView`.

5. **Execute.** Calls `migration.migrate(view)` (Python) or
   `yaml_interp.execute(ops, view)` (YAML). Collects
   `list[FileChange | MoveFile | DeleteFile | RegistryRewrite]`.

6. **Suspicious-noop guard.** If the migration declares
   `EXPECTED_NONEMPTY_AT_LEAST_ONE_PROJECT = True` and the result is empty
   across all projects, the runner aborts with `error_kind='suspicious_noop'`.
   Default: off.

7. **Empty-result branch.** If result is `[]`, opens a one-line PR editing
   only `system/repos.yaml`'s `template_version` (title:
   `template-migration: 00NN-<slug> (no-op for this project)`). PR body
   explains why (e.g., "this project has no `services/` artifacts").

8. **Batch.** Sorts changes deterministically by path. If
   `len(changes) > template_migration_max_files_per_pr` (default 50):
   - If `migration.ALLOW_BATCHING` is falsy, inserts `status='failed'`,
     `error_kind='batch_required'` and stops (no partial PR opened).
   - If truthy, splits into batches of ≤ 50 files. The final batch carries the
     `system/repos.yaml` `template_version` bump; earlier batches carry a
     comment noting "version bump in batch N/N."

9. **Commit.** For each batch, calls `build_and_push_tree(repo, branch, sha,
   changes, message)` — the shared helper from 0044's `/ship` — on branch
   `template-migration/00NN-<slug>-bK`. Inserts a `template_migrations` row
   with `status='pending'`.

10. **PR.** Opens a PR titled `template-migration: 00NN-<slug>` (suffix `-K/N`
    for batched). PR body: migration DESCRIPTION + per-file change reasons +
    the new `template_version` the final batch will set on merge. Updates the
    row to `status='pr_open'` with `opened_pr_url`.

11. **Concurrency.** `--max-parallel-projects` flag (default 4). Projects
    parallelise across goroutine-equivalent async tasks; within a project,
    strictly sequential. Limits runner memory under heavy fleet.

**`coder_core/migrations/knowledge/git_trees.py`** — thin wrapper around the
Git Trees commit pattern from 0044's `/ship`. Exposes:

```python
def build_and_push_tree(
    github_client: GitHubClient,
    repo: str,         # owner/repo
    branch: str,       # target branch to create or push
    base_sha: str,     # current main SHA
    file_changes: list[FileChange | MoveFile | DeleteFile],
    commit_message: str,
) -> str:              # new commit SHA
```

The `/ship` handler in `knowledge-write-api` migrates to call this helper
(small internal refactor, no API behaviour change). Shared tests cover both
call sites.

**`coder_core/migrations/knowledge/sdk.py`** — pure dataclasses + read-only
view. Migration files import from this module only; no imports from other
`coder_core` modules are permitted (enforced by CI import-boundary check).

**`coder_core/migrations/knowledge/yaml_interp.py`** — YAML declarative
interpreter. Handles five operations in order:

| Operation | Effect |
|---|---|
| `rename_frontmatter_key` | In-scope artifact types: if `from` key present, rename to `to` preserving value |
| `add_frontmatter_key_with_default` | In-scope artifact types: if `key` absent, set to `default` |
| `remove_frontmatter_key` | In-scope artifact types: if `key` present, remove it |
| `move_folder` | Rename folder; update `registry.yaml` `file` + `folder`; re-run cross-link check |
| `rename_folder` | Shortcut: move every file from `from/` to `to/` |

### Failure handling

**`migrate()` raises.** Runner catches the exception; inserts
`status='failed'`, `error_kind='migrate_raised'`, `error_detail=<traceback>`.
No partial PR. Project stays at current version. Recovery: fix the migration
logic, ship a new migration with a higher number.

**Per-artifact parse error.** If `KnowledgeRepoView` cannot parse an
artifact's frontmatter (malformed YAML), the runner inserts
`status='failed'`, `error_kind='parse_error'`,
`error_detail='<path>: <parse exception>'`. **Abort the whole migration for
this project — no partial PR is opened.** This is "fail-strict": a project
with corrupted artifacts is not silently skipped. Operator must fix the
corrupt artifact and re-run (or issue a corrective migration).

Rationale for abort-over-partial: opening a partial PR (skipping the corrupt
artifact) would leave the project in an inconsistent intermediate schema state
— some artifacts migrated, one not — which is harder to reason about than a
clean failure with all artifacts at the prior version.

**Broken cross-links after rename.** Prevented by alias-tolerance (the
validator accepts both old and new names during the window). If a migration
opens a PR and the project's CI fails on cross-link validation anyway (e.g.,
alias not set up), the PR sits in CI-failing state. The fleet matrix surfaces
`pr_open` with the PR's CI status overlaid. Operator closes the PR, marks the
row `status='abandoned'`, and the migration is re-issued with the alias gap
fixed.

**Git Trees push 5xx.** Retried once via `run_with_transient_retry` (ADR
0013). On second failure, inserts `status='failed'`,
`error_kind='github_upstream'`. No PR opened.

**`NUMBER` collision.** Caught by the `coder-system` PR's CI validator before
merge.

**Forbidden path.** SDK refuses `MoveFile` / `RegistryRewrite` against paths
that AGENTS.md names by string (`active/`, `wip/`, `deprecated/`). Surfaces
as `error_kind='forbidden_path'`.

### Rollback

**Per-project.** Close the open migration PR in the project repo (manual
operator action). Update the `template_migrations` row to
`status='abandoned'` via `PATCH /v1/_admin/template/migrations/{project_id}/
{migration_number}/{batch_index}/abandon`. The project remains at its
pre-migration `template_version`. The runner will not re-open a PR for a
migration with an `abandoned` row — a new migration number is required to
retry.

**Fleet kill switch.** Set `CODER_TEMPLATE_MIGRATIONS_ENABLED=false`. Runner
invocations exit early with no work done.

**Bad migration in `coder-system`.** Two paths:

- *No PR opened yet*: revert the migration file's commit on `coder-system`.
  The runner will no longer see it as pending. Any partially-computed rows in
  `status='pending'` should be manually set to `abandoned`.
- *PR already opened (or merged)*: ship a paired-reversal migration with a
  higher number that undoes the bad migration's effects. This is the only safe
  path once any project has merged.

There is no separate `template_migrations_undo` table. The `abandoned` status
in `template_migrations` captures that a migration attempt was terminated
without completion; audit events capture the operator action. A reversal
migration creates new rows under its own migration number and is visible in
the fleet matrix as a standard migration.

**SDK / interpreter / runner bug.** Disable fleet, fix the code, re-enable.
Existing open PRs are unaffected.

**PR open > 30 days.** Operator closes, marks row `status='abandoned'`
(the admin endpoint above). A re-issue of the migration (new number) is
required to retry.

### Observability

**Prometheus counters:**

- `template_migration_run_total{outcome="success"|"failed"|"skipped",
  project_id, migration_number}` — incremented per `(project, migration)` pair
  at the end of each runner attempt.
- `template_migration_files_changed_total{migration_id, project_id}` —
  incremented by the number of files in the `FileChange[]` result; 0 for
  no-op migrations.
- `template_migration_pr_open_age_seconds{migration_id, project_id}` — gauge,
  current age of any row with `status='pr_open'`; updated at each runner tick.
- `template_migration_pending_count{project_id}` — gauge, count of
  migrations with no row or `status='pending'` for the project; derived at
  runtime from the migration registry vs `template_migrations` table.
- `template_migration_schema_drift_409_total{project_id}` — incremented by
  the Knowledge API read path each time it returns a `409 SCHEMA_DRIFT` on a
  `?min_schema_version=` call.

**Audit events** (`audit_events` table, per AC10):

| action | when |
|---|---|
| `template_migration.started` | Runner begins work on a `(project, migration, batch)` |
| `template_migration.opened_pr` | PR opened; row flipped to `pr_open` |
| `template_migration.merged` | Callback received from `record-template-migration.yml`; row flipped to `merged` |
| `template_migration.failed` | Row flipped to `failed` (any `error_kind`) |
| `template_migration.abandoned` | Row manually flipped to `abandoned` via admin endpoint |

`target_type='template_migration'`, `target_id='<project_id>:<migration_number>:<batch_index>'`.

### Feature flags

**Fleet flag:** `CODER_TEMPLATE_MIGRATIONS_ENABLED` (env var on coder-core,
default `false` on first deploy). When false, the runner exits early with no
work done and `POST /v1/_admin/template/migrate` returns `423 Locked` with
`reason='fleet_flag_disabled'`.

**Per-project tri-state** (`projects.template_migrations_enabled BOOLEAN NULL`,
migration 0056):

| Column value | Effective behaviour |
|---|---|
| `NULL` | Inherit fleet flag (default for all projects) |
| `TRUE` | Project participates in migrations regardless of fleet flag |
| `FALSE` | Project skipped by the runner regardless of fleet flag |

API: `PATCH /v1/projects/{id}` accepts `template_migrations_enabled: bool | null`.
The fleet matrix shows the effective state per project (inherited vs explicit).

### 0052 managed-workflow consumer registration

The `record-template-migration` workflow is 0047's consumer of the 0052
managed-workflow distribution primitive.

**Manifest entry** added to `coder-system/system/managed-workflows.yaml`
(in the same PR that ships Stage 3 of the 0047 rollout):

```yaml
- id: record-template-migration
  template_path: template/.github/workflows/record-template-migration.yml
  receiver_endpoint: /v1/_admin/template/migrations/{project_id}/{migration_number}/{batch_index}/merged
  consuming_spec: "0047"
  introduced: "2026-06-01"
```

**Workflow file** `template/.github/workflows/record-template-migration.yml`:

```yaml
name: Record template migration merge
on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  record:
    if: >
      github.event.pull_request.merged == true &&
      startsWith(github.event.pull_request.head.ref, 'template-migration/')
    runs-on: ubuntu-latest
    steps:
      - name: Parse migration ref
        id: parse
        run: |
          # branch: template-migration/00NN-slug-bK or template-migration/00NN-slug
          ref="${{ github.event.pull_request.head.ref }}"
          number=$(echo "$ref" | grep -oP '(?<=template-migration/)\d+')
          batch=$(echo "$ref" | grep -oP '(?<=-b)\d+$' || echo "1")
          echo "number=$number" >> "$GITHUB_OUTPUT"
          echo "batch=$batch"   >> "$GITHUB_OUTPUT"
      - name: POST merge callback
        run: |
          curl -fsSL -X POST \
            -H "Authorization: Bearer ${{ secrets.CODER_ADMIN_TOKEN }}" \
            -H "X-GitHub-Delivery: ${{ github.sha }}" \
            -H "Content-Type: application/json" \
            -d '{"merged_at":"${{ github.event.pull_request.merged_at }}",
                 "merge_commit_sha":"${{ github.event.pull_request.merge_commit_sha }}"}' \
            "${{ vars.CODER_CORE_URL }}/v1/_admin/template/migrations\
/${{ github.repository_owner }}-${{ github.event.repository.name }}\
/${{ steps.parse.outputs.number }}/${{ steps.parse.outputs.batch }}/merged"
```

**Handler registration** in `coder_core/migrations/knowledge/runner.py`:

```python
from coder_core.integrations.managed_repo_callbacks import register_handler
from coder_core.migrations.knowledge import callbacks

register_handler(
    workflow_id="record-template-migration",
    handler=callbacks.handle_migration_merged,
)
```

The handler `handle_migration_merged` validates the payload, flips the
`template_migrations` row to `status='merged'`, writes the audit event, and
bumps `template_version` in `repos.yaml` (the bump is already in the PR diff,
but this confirms the merge was recorded).

The workflow is distributed to managed repos via `coder managed-workflows sync
--workflow record-template-migration` (Stage 3 of the rollout, same command as
0052's seed CLI).

## Interfaces

**API:**

- `POST /v1/_admin/template/migrate` body
  `{migration_numbers?: [N], projects?: [slug], dry_run?: bool}` →
  `{run_id, scheduled_jobs: N}`. Admin auth. Dispatches Cloud Run Job.
- `GET /v1/_admin/template/migrations[?status=&project_id=&migration_number=]`
  → fleet matrix. Admin auth.
- `GET /v1/projects/{id}/template/version` →
  `{template_version, current_version, pending: [{number, slug, description}]}`.
  Per-project auth.
- `POST /v1/_admin/template/migrations/{project_id}/{migration_number}/{batch_index}/merged`
  body `{merged_at, merge_commit_sha}` — called by `record-template-migration.yml`
  on PR merge. Flips row; writes audit event.
- `PATCH /v1/_admin/template/migrations/{project_id}/{migration_number}/{batch_index}/abandon`
  — operator rollback. Flips row to `abandoned`; writes audit event.
- `GET /knowledge/{type}/{id}?min_schema_version=N` → `409 SCHEMA_DRIFT` with
  `{artifact, pending_migrations: [{number, slug}]}` if
  `project.template_version < N`. Default (no param) unaffected.

**CLI:**

- `coder migrate test --against ./fixture-repo
  --migration coder-system/migrations/knowledge/00NN-...py` — runs a migration
  against a local fixture repo, prints `FileChange[]`. No network. Used by
  schema authors in their development loop.
- `coder migrate status [--project <slug>]` — prints fleet matrix or a single
  project's rows.

**GitHub Action:** `template/.github/workflows/record-template-migration.yml`
(above). Distributed via `coder managed-workflows sync` (spec 0052 Stage 1).

**Audit:** every state change writes an `audit_events` row per AC10.

**Cloud Scheduler:** weekly job posts to `/v1/_admin/template/migrate` with no
filters (full fleet, all pending).

## Rollout

- **Stage 0 — infrastructure, no migrations.**
  Ship SDK, YAML interpreter, runner Cloud Run Job,
  `template_migrations` table (0055), `projects` flag column (0056), API
  endpoints. No migration files exist yet; the runner is a no-op.
  `CODER_TEMPLATE_MIGRATIONS_ENABLED=false`.

- **Stage 1 — baseline migration `0001-baseline.py`.**
  A no-op migration that bumps `template_version` from 0 to 1 for every
  project. Validates the end-to-end path: one PR per project, small diff,
  reviewed and merged, recording Action fires, matrix shows everyone at v1.
  Fixtures in `coder-system/migrations/_fixtures/` land here.

- **Stage 2 — `coder` opt-in.**
  Set `projects.template_migrations_enabled=true` for `coder` only. Run a
  synthetic additive migration (`0002-add-test-only-field.py`) against `coder`
  alone. Walk the PR → merge → callback → matrix update path. Inspect audit
  trail. Fleet flag remains off.

- **Stage 3 — Action distribution.**
  Distribute `record-template-migration.yml` to all managed repos via
  `coder managed-workflows sync --workflow record-template-migration` (0052
  CLI). Add the manifest entry to `managed-workflows.yaml`. Verify the Action
  fires on a synthetic merged migration PR.

- **Stage 4 — fleet flip.**
  `CODER_TEMPLATE_MIGRATIONS_ENABLED=true`. Every managed project now
  participates. Monitor the admin matrix.

- **Stage 5 — first real schema change.**
  A real schema evolution (additive — e.g., `criticality` on services) ships
  as migration `0003-add-criticality.py`. If this migration is a rename
  instead, alias-tolerance pre-work (VALIDATOR_ALIASES + `validator-aliases.yaml`
  generation) must land on `coder-system` before this stage.

- **Stage 6 — admin UI.**
  `VITE_TEMPLATE_MIGRATIONS_ENABLED=true` turns on the SPA fleet matrix page.

## Backout plan

- **Per-project disable:** `PATCH /v1/projects/{id}
  {template_migrations_enabled: false}`. Runner skips on subsequent ticks.
- **Fleet kill switch:** `CODER_TEMPLATE_MIGRATIONS_ENABLED=false`.
- **Bad migration pre-PR:** revert migration file commit on `coder-system`;
  open PRs must be closed manually and rows set to `abandoned`.
- **Bad migration post-merge:** ship a paired-reversal migration with a higher
  number. Runbook documents both paths.
- **SDK / runner bug:** disable fleet, fix, re-enable. Open PRs unaffected.
- **PR open > 30 days:** close PR, mark row `abandoned` via admin endpoint,
  re-issue with new migration number.

## Links

- Spec: [0047](../product-specs/wip/0047-template-schema-migration.md)
- ADRs:
  [0019](../adrs/0019-alias-tolerance-fleet-completion-gate.md),
  [0020](../adrs/0020-worker-dispatched-migration-runner.md),
  [0021](../adrs/0021-deprecate-then-remove-two-migrations.md)
- Related designs:
  [knowledge-write-api](../designs/active/knowledge-write-api.md),
  [knowledge-repo-model](../designs/active/knowledge-repo-model.md),
  [audit-log](../designs/active/audit-log.md),
  [0052](../designs/wip/0052-managed-repo-action-distribution.md)
- ADR 0008 (CI validation): [0008](../adrs/0008-ci-validation-of-knowledge-repo.md)

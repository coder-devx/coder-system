---
id: '0047'
title: Template schema migration
type: design
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
implements_specs: ['0047']
related_designs:
  - knowledge-write-api
  - knowledge-repo-model
  - audit-log
  - system-overview
  - worker-communication
affects_services:
  - coder-core
  - coder-admin
---

# 0047 — Template schema migration

## Context

Spec 0047 ships a sanctioned path for evolving
`coder-system/template/` and rolling the change across every
managed project's knowledge repo. A schema author writes one
migration file in `coder-system/migrations/knowledge/00NN-...py`
(or `.yaml` for declarative cases); a Cloud Run Job
`coder-core-template-migrate` per-project applies any pending
migration as a reviewed PR; a `template_migrations` table tracks
status; a per-project `template_version` field at the top of
`system/repos.yaml` records what's applied. This is the only path
to write to `template/` paths because 0044's `/ship` endpoint
explicitly refuses them.

This design is the wiring: the `KnowledgeRepoView` SDK that
migration files import, the Git Trees commit shape (atomic, same
shape as 0044's `/ship`), the runner's per-project advisory-lock
serialisation, the YAML-declarative-operations interpreter, and
the API surface (`min_schema_version=N` 409, fleet matrix
endpoint).

## Goals

- Reuse 0044's Git Trees atomic-commit machinery — no new GitHub
  write path. The migrator builds a single tree per batch and
  pushes it as one commit on a new branch.
- Reuse the existing CI validator (ADR 0008) on the project
  repo's PR — the migration PR validates the same way any
  knowledge edit does. A failed validation = the migration
  itself is buggy.
- Make the SDK pure: migration files receive a read-only view +
  return a list of intent objects. They never reach for GitHub,
  the database, or the cache. Testable in-process with a fixture
  repo.
- Strict per-project ordering: migrations apply to a project in
  number order; failure of N blocks N+1 on that project; other
  projects are independent.

## Architecture

```mermaid
flowchart TB
  author["Schema author"] -->|commit migration file| sysrepo[(coder-system repo)]
  sysrepo -->|merge → tick| runner["Cloud Run Job<br/>coder-core-template-migrate"]
  runner -->|per project per migration| advisory["pg advisory lock<br/>(project_id)"]
  advisory --> pre["Preflight:<br/>read project repos.yaml,<br/>compute pending"]
  pre --> sdk["SDK: KnowledgeRepoView<br/>(in-memory snapshot)"]
  sdk --> migrate["migration.migrate(view)<br/>or YAML interpreter"]
  migrate -->|FileChange[] / MoveFile / DeleteFile| batcher["Batcher<br/>(≤ max_files_per_pr)"]
  batcher -->|per batch| trees["Git Trees commit<br/>(reuses 0044 builder)"]
  trees -->|on branch template-migration/N-slug| pr["open PR via existing helper"]
  pr -->|status| db[("template_migrations table<br/>(migration 0055)")]
  pr -.merge.-> review["Reviewer / operator"]
  review -->|merge bumps repos.yaml.template_version| projrepo[(Project knowledge repo)]
```

### Parts

- **`coder-system/migrations/knowledge/`** — folder for
  migration files. CI validates each PR adding files here:
  unique `NUMBER`, importable Python, schema-valid YAML.
- **`coder_core/migrations/knowledge/sdk.py`** (new) —
  `KnowledgeRepoView`, `Artifact`, `FileChange`, `MoveFile`,
  `DeleteFile`, `RegistryRewrite`. Pure dataclasses + a
  read-only view backed by an in-memory snapshot of the
  project repo's tree.
- **`coder_core/migrations/knowledge/yaml_interp.py`** (new) —
  takes a YAML migration file's `operations[]` list, returns
  `list[FileChange|MoveFile|DeleteFile]` by interpreting the
  declarative ops (`rename_frontmatter_key`,
  `add_frontmatter_key_with_default`,
  `remove_frontmatter_key`, `move_folder`,
  `rename_folder`).
- **`coder_core/migrations/knowledge/runner.py`** (new) —
  Cloud Run Job entry point. Owns: load migration registry
  from `coder-system`, per-project preflight + advisory lock +
  in-memory-snapshot fetch + SDK invoke + batching + Git Trees
  commit + PR open + DB row update.
- **`coder_core/migrations/knowledge/git_trees.py`** (new but
  thin) — wraps the Git Trees commit pattern from 0044's
  `/ship` endpoint into a reusable
  `build_and_push_tree(repo, branch, base_sha,
  file_changes, message)` helper. The `/ship` handler in
  `knowledge-write-api` migrates to call this helper too
  (small refactor, no behaviour change).
- **`coder_core/api/template_migrations.py`** (new) — admin
  endpoints: `GET /v1/_admin/template/migrations` (fleet
  matrix), `POST /v1/_admin/template/migrate` (manual trigger
  for the runner with optional filters), and per-project
  `GET /v1/projects/{id}/template/version`.
- **Knowledge API change** —
  `coder_core/api/knowledge_read.py` adds the
  `?min_schema_version=N` parameter handling: if the project's
  `template_version < N`, return 409 with the artifact body and
  `pending_migrations[]`.
- **Tables:**
  - `template_migrations` (migration 0055) per AC4.
  - `projects` columns (migration 0056):
    `template_migrations_enabled BOOLEAN NULL` (tri-state).
- **Admin SPA:** `TemplateMigrationsPage.tsx` (new) renders
  the fleet matrix; per-project `TemplateMigrationsTab.tsx`
  reuses the same data filtered.

### Data flow — happy path

1. Schema author commits
   `coder-system/migrations/knowledge/0047-add-criticality.py`
   alongside any required `template/` updates and a
   `system/repos.yaml` `template_version: 47` bump on
   `coder-system`. The PR's CI runs the migration registration
   validator + the existing knowledge-repo CI. PR merges.
2. Cloud Scheduler fires
   `POST /v1/_admin/template/migrate` (no filters → fleet, all
   pending) once a week. (Or an operator triggers it manually
   via the admin endpoint.)
3. Runner reads `coder-system/migrations/knowledge/`, computes
   `pending = [m for m in migrations if m.NUMBER >
   project.template_version]` per project. Per `(project,
   migration)` pair, it acquires a Postgres advisory lock keyed
   on `hash(project_id)` so two runner invocations don't both
   work the same project; another invocation sees the lock and
   skips.
4. Runner checks `template_migrations` for an existing row at
   `(project, migration, batch_index=any)` with `status='pr_open'`
   — if present, the project already has a pending review;
   skip. If `status='failed'`, also skip pending operator fix +
   migration-number bump (failed rows are terminal until the
   author re-issues with a new number).
5. Runner fetches the project repo's `main` ref → SHA, loads
   the relevant tree paths into a `KnowledgeRepoView`. (Lazy
   per-folder-fetch, not full clone — only folders the
   migration's `AFFECTS` lists are loaded; declarative
   migrations infer this from `in_types`.)
6. Runner calls `migration.migrate(view)` (Python) or runs
   `yaml_interp.execute(yaml_ops, view)` (YAML); collects
   `list[FileChange | MoveFile | DeleteFile | RegistryRewrite]`.
7. **Empty result branch.** If empty, runner opens a one-line
   PR editing only `system/repos.yaml`'s `template_version`
   (per spec OQ #1). PR title:
   `template-migration: 00NN-<slug> (no-op for this project)`.
   Body explains why (e.g. "this project has no `services/`
   artifacts, the migration's `AFFECTS=['services']` was
   inapplicable").
8. **Non-empty branch.** Runner sorts the changes
   deterministically by path, batches at
   `template_migration_max_files_per_pr` (default 50),
   inserts a `template_migrations` row per batch (`status=
   'pending'`). The final batch additionally carries the
   `system/repos.yaml` `template_version` bump.
9. For each batch, runner builds a Git Trees commit via the
   shared helper (one tree, one parent = current `main`,
   commit message `template-migration: 00NN-<slug>: batch
   K/N`, author = the template-migration SA), pushes to
   `template-migration/00NN-<slug>-bK` branch, opens a PR
   titled `template-migration: 00NN-<slug>` (suffix `-K/N` if
   batched). Updates the row to `status='pr_open'` with
   `opened_pr_url`.
10. Reviewer merges the PR. A new GitHub Action distributed via
    `template/.github/workflows/record-template-migration.yml`
    POSTs to `/v1/_admin/template/migrations/{project_id}/
    {migration_number}/{batch_index}/merged` to flip the row
    to `status='merged'` with `merged_at`. (Webhook
    alternative below in OQ.)
11. The project's `system/repos.yaml.template_version` is now
    bumped (only on the final batch's merge), so subsequent
    runner ticks see this migration as no-longer-pending.

### Data flow — failure cases

- **`migrate()` raises.** Runner catches; inserts a
  `template_migrations` row with `status='failed'`,
  `error_kind='migrate_raised'`, `error_detail=<traceback>`.
  No partial PR is opened. The project stays at its current
  version. Operator inspects, fixes the migration, ships a
  new migration with a higher number.
- **Git Trees push 5xx.** Runner retries once via the existing
  `run_with_transient_retry` (0027) compose; on second
  failure, inserts `status='failed'`, `error_kind=
  'github_upstream'`. PR is not opened. Same recovery as above.
- **Validator (CI) fails on the open PR.** This is detectable
  but the runner is no longer in the loop — the PR sits in
  CI-failing state. The fleet matrix surfaces it as
  `pr_open` (because the runner did open it) with the PR's
  CI status overlaid. Operator either rebases/fixes or closes
  the PR; closing the PR triggers an operator-driven row
  update to `status='failed'` (or a new manual run after the
  fix).
- **Schema author error: `NUMBER` already exists.** The
  registration CI (running on the `coder-system` PR that adds
  the file) catches this; the PR can't merge.
- **Schema author error: migration touches paths AGENTS.md
  forbids renaming.** The SDK refuses the `MoveFile` /
  `RegistryRewrite` at runtime with a clear error pointing at
  the AGENTS.md contract. Surfaces as `error_kind=
  'forbidden_path'`.

### YAML declarative interpreter

The interpreter handles five operations:

| Operation | Effect |
|---|---|
| `rename_frontmatter_key` | for each artifact in `in_types`, if `from` key present, rename to `to` (preserving value) |
| `add_frontmatter_key_with_default` | for each artifact in `in_types`, if `key` absent, set to `default` |
| `remove_frontmatter_key` | for each artifact in `in_types`, if `key` present, remove |
| `move_folder` | rename a folder; for each artifact within, update `registry.yaml` `file` + `folder` fields and reissue cross-link integrity check |
| `rename_folder` | shortcut for moving every file from `from/` to `to/` (a single `move_folder`) |

A YAML migration with multiple operations applies them in
order to the snapshot — second operation sees the result of
the first. Output is the same `list[FileChange | MoveFile |
DeleteFile | RegistryRewrite]` shape the Python path produces.

### Invariants

- **Per-project, strictly ordered, single-pending.** A
  project never has two PRs open for two different migration
  numbers concurrently. Migration N's PR must merge before
  N+1's PR opens (per spec OQ #3 leaning). Enforced by
  preflight: runner only opens the smallest pending number
  per project; subsequent numbers wait.
- **PR never lands without human merge.** No part of the
  runner writes to `main`. The Git Trees commit lands on a
  branch; only the PR merge moves the ref.
- **Idempotency at the row level.** A `(project,
  migration_number, batch_index)` row is unique. Re-runs see
  the existing row and skip.
- **`coder-system` repo is self-hosted.** The runner does not
  touch `coder-system`; the schema author updates it by hand
  in the same PR that adds the migration file. This is the
  same boundary ADR 0008 draws for the CI validator.
- **Git Trees commit shape is shared with 0044.** The shared
  `build_and_push_tree(...)` helper is the one that 0044's
  `/ship` calls. A bug in the tree-build logic affects both
  endpoints; tests live alongside the helper.
- **Migration code never imports from `coder_core` outside
  the SDK module.** Migrations get exactly the SDK's
  exposed surface — preventing schema authors from reaching
  for the database or other internal helpers.

## Interfaces

- **API:**
  - `POST /v1/_admin/template/migrate` body
    `{migration_numbers?: [N], projects?: [slug]}` →
    `{run_id, scheduled_jobs: N}`. Auth: admin token.
  - `GET /v1/_admin/template/migrations[?status=pending|pr_open|merged|failed]`
    → fleet matrix.
  - `GET /v1/projects/{id}/template/version` →
    `{template_version, current_version, pending: [...]}`.
  - `POST /v1/_admin/template/migrations/{project_id}/
    {migration_number}/{batch_index}/merged` body
    `{merged_at, merge_commit_sha}` — called by the per-repo
    GitHub Action on PR merge to flip status.
  - `GET /knowledge/{type}/{id}?min_schema_version=N` →
    409 SCHEMA_DRIFT with `pending_migrations[]` if
    `template_version < N`.
- **CLI:**
  - `coder migrate test --against ./fixture-repo
    --migration coder-system/migrations/knowledge/00NN-...py`
    runs a migration against a local fixture repo and prints
    the resulting `FileChange[]`. No network. Used by the
    schema author for the development loop.
  - `coder migrate status [--project <slug>]` prints the
    fleet matrix or one project's row.
- **GitHub Action template:**
  `template/.github/workflows/record-template-migration.yml`
  triggered on `pull_request: closed` if `merged == true` and
  branch matches `template-migration/*`; POSTs to the
  `.../merged` endpoint to update the row.
- **Audit:** every state change writes an `audit_events` row
  per AC10. Runner failures also audit-log
  (`action='template_migration.failed'`).
- **Cloud Scheduler:** weekly job posts to
  `/v1/_admin/template/migrate` with no filters.

## Open questions

- **Webhook vs Action for merge tracking.** AC4 + the data
  flow uses a per-repo GitHub Action to POST on merge. An
  alternative is a single GitHub App webhook on the
  pull_request event installed on every managed repo. The
  webhook avoids the per-repo Action distribution but adds
  the complexity of installation tracking + signature
  verification on the receiving end. Leaning Action: the
  Action lands via 0045's existing template-distribution path
  + the one-time fleet sweep, no new GitHub App install.

- **Should the runner support `--dry-run`?** A dry-run that
  produces the `FileChange[]` and prints them without opening
  a PR would help the schema author validate against real
  project data. The CLI `coder migrate test` covers a fixture
  repo; a fleet-wide dry-run is the same logic against every
  managed project. Leaning yes — add `--dry-run` flag that
  emits a structured report keyed by project + change count;
  no DB write, no PR.

- **Validator alias-tolerance for renames.** Spec OQ #5 — a
  rename migration breaks cross-link integrity until applied.
  Two paths: (a) the validator (ADR 0008) gains an "alias
  list" the migration registers temporarily; (b) the
  migration's PR is the validator's first opportunity to see
  the new name + the project's pre-PR state has the old name.
  (b) means in the gap between `coder-system` merge and the
  per-project PR merge, any non-migration commit on the
  project breaks CI. Probably (a). Implementation: the
  migration file declares
  `VALIDATOR_ALIASES = {"old": "new"}` which the runner
  injects into the validator's accept list; on
  `template_migrations.status='merged'` for every project,
  the alias is removed from the next `coder-system` release.
  Adds a coordination dance — design needs to specify whether
  this is in-scope for v1 or deferred to a follow-up.

- **`template/_TEMPLATE.md` itself changing.** A migration
  that updates a `_TEMPLATE.md` file in the project's repo
  (not just the artifacts) — does the runner support that?
  Leaning yes; `_TEMPLATE.md` is just another file in the
  registered folder. SDK's `iter_files` covers it. The
  migration's PR diff includes the `_TEMPLATE.md` update.

- **Concurrent migration runs across projects.** Two managed
  projects A and B can have their `(N, K-batch)` PRs being
  prepared in parallel — the per-project advisory lock
  ensures intra-project serialisation but says nothing about
  cross-project. If migration 47 is heavy (touches 100s of
  files), do we bound concurrent project runs to avoid
  memory pressure? Leaning: yes, runner takes a
  `--max-parallel-projects` flag (default 4) — the runner is
  a single Cloud Run Job, so all parallelism is in-process.
  Trade-off: faster fleet rollout vs runner memory ceiling.

- **What if the migration accidentally produces empty
  changes?** A migration with a logic bug that always returns
  `[]` would silently bump `template_version` (per the no-op
  branch). To guard against this, the schema author can
  declare an `EXPECTED_NONEMPTY_AT_LEAST_ONE_PROJECT = True`
  flag; if all per-project applications return empty, the
  runner aborts the run with a "this migration is
  suspicious" error. Off by default. Worth adding so a
  silent-no-op-everywhere migration produces a clear failure.

## Rollout

- **Stage 0 — SDK + interpreter + runner land, no migrations
  written.** Ship the SDK module, the YAML interpreter, the
  runner Cloud Run Job, the `template_migrations` table
  (migration 0055), the `projects` flag column (migration
  0056), the API endpoints, the admin page. No migration
  files exist yet, so `/v1/_admin/template/migrate` is a
  no-op (everything is already at version 0 = current).
  Default `CODER_TEMPLATE_MIGRATIONS_ENABLED=false` fleet.

- **Stage 1 — baseline migration `0001-baseline.py`.**
  A no-op migration that just bumps `template_version` from
  0 to 1 for every project (per AC1). This validates the
  end-to-end path: runner opens one PR per project setting
  `template_version: 1`. Each PR is small and reviewed; merge
  fires the recording Action; the matrix shows everyone at
  v1. This is the mechanism's hello-world.

- **Stage 2 — `coder` opt-in.**
  `projects.template_migrations_enabled=true` for `coder`
  only. Run a synthetic test migration
  (`0002-add-test-only-field.py`) that adds an optional
  frontmatter field to one artifact type. Walk the PR review
  + merge + Action + matrix update path. Inspect the audit
  trail.

- **Stage 3 — Action + GitHub App install distribution.**
  Distribute `record-template-migration.yml` via
  `template/.github/workflows/` for new projects + a one-time
  `seed_template_migration_action.py` script for existing
  managed projects. Verify the Action fires on a synthetic
  merged PR.

- **Stage 4 — fleet flip.**
  `CODER_TEMPLATE_MIGRATIONS_ENABLED=true` fleet-wide. The
  next migration ships against every managed project.

- **Stage 5 — first real schema change.** A real schema
  evolution (e.g. add an optional `criticality` field to
  services) is shipped as the first non-baseline non-test
  migration. Use the runbook's authoring + monitoring +
  recovery paths end-to-end.

- **Stage 6 — admin UI on.**
  `VITE_TEMPLATE_MIGRATIONS_ENABLED=true` flips the admin
  page on. Operators can monitor without invoking the CLI.

## Backout plan

- **Per-project disable:** `PATCH /v1/projects/{id}` setting
  `template_migrations_enabled=false`. Runner skips the
  project on subsequent ticks.
- **Fleet kill switch:** flip
  `CODER_TEMPLATE_MIGRATIONS_ENABLED=false`. Runner
  invocations exit early with no work done.
- **Bad migration shipped to `coder-system`.** Two options:
  (a) revert the migration file's commit on `coder-system`;
  the runner will no longer see it as pending (effectively
  retroactive cancel) — but any PR already opened stays open
  and the operator must close it. (b) ship a paired-reversal
  migration with a higher number that undoes the bad one's
  effects. (b) is the only path if any project has already
  merged the bad migration. Runbook documents both.
- **Bug in the SDK / interpreter / runner.** Disable fleet,
  fix the code, re-enable. Existing pending PRs are
  unaffected (they're already on disk in the project repo).
- **Bug in the shared `build_and_push_tree` helper that also
  affects 0044's `/ship`.** This is a wide-blast-radius bug
  — the helper is the single commit-construction path for
  both the migrator and the ship endpoint. Mitigation:
  unit tests for the helper live alongside it with seeds
  that exercise both call sites; any change to the helper
  triggers both the migrator and `/ship` test suites.
- **PR sat open too long (e.g. > 30 days).** Operator
  judgment: close the PR (manual `template_migrations.status`
  update to `failed` with `error_kind='abandoned'`), then
  the migration is treated as failed for that project. A
  re-issue is required to retry.

---
id: knowledge-schema-migration
title: Knowledge schema migration
type: spec
status: active
owner: ro
created: 2026-05-06
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: []
related_specs: [knowledge-api, onboarding, admin-panel, audit-log, knowledge-freshness]
parent: knowledge-and-admin
---

# Knowledge schema migration

## What it is

A numbered-migration system for propagating `coder-system/template/`
schema changes across all managed project knowledge repos. A migration
file lands once in `coder-system/`; a Cloud Run Job opens one reviewed
PR per managed project per pending migration. No project repo is ever
written without a human merge.

The `last_verified_at` backfill (spec 0043, 2026-04-18) was the last
hand-curated schema change — that coordination cost motivates this
system.

## Users

- **Schema author** — writes one `00NN-<slug>.py` or `.yaml` file in
  `coder-system/migrations/knowledge/`, commits it; never touches any
  project repo directly.
- **Per-project reviewer** — receives one PR per project per migration
  titled `template-migration: 00NN-<slug>`; reviews the diff, approves
  or requests revision via the normal PR flow. Not eligible for
  auto-approval (spec 0040).
- **Onboarding operator** — new projects are seeded with
  `template_version: <current>` so no prior migrations are pending on
  day one.
- **Operator** — monitors the admin fleet matrix to triage stuck
  migrations and per-project drift.

## Capabilities

- **Migration files.** `coder-system/migrations/knowledge/00NN-<slug>.py`
  exports `NUMBER`, `SLUG`, `DESCRIPTION`, and
  `migrate(view) -> list[FileChange]`. A declarative `.yaml` variant
  covers rename-key, add-constant-key, and move-folder operations.
  `_TEMPLATE.py`, `_TEMPLATE.yaml`, and `0001-baseline.py` (no-op;
  records `template_version=1` for projects at version 0) seed the
  folder. CI validates unique `NUMBER`, present `SLUG`/`DESCRIPTION`,
  Python importability, and YAML schema compliance.
- **`template_version` tracking.** `system/repos.yaml` in every
  project knowledge repo carries `template_version: N`.
  `coder-system`'s own `system/repos.yaml` carries the current version
  (`max(NUMBER)` across the migrations folder). The
  `coder migrate test --against ./fixture-repo` CLI command smoke-tests
  a migration against synthetic fixtures in
  `coder-system/migrations/_fixtures/`.
- **KnowledgeRepoView SDK.** `from coder_core.migrations.knowledge
  import KnowledgeRepoView, FileChange, DeleteFile, MoveFile,
  RegistryRewrite`. Exposes `list(type)`, `get(type, id)`, and
  `iter_files(folder)` (for non-registered paths such as
  `glossary.md`). Migration code never calls GitHub directly — the
  runner constructs the Git Trees commit and opens the PR.
- **Runner job.** `coder-core-template-migrate` (Cloud Run Job,
  oneshot or Cloud Scheduler weekly). Args: `--migration-numbers` and
  `--projects` (both optional; defaults: all pending, all managed).
  Ad-hoc trigger: `POST /v1/_admin/template/migrate` (admin JWT).
- **Idempotency.** `template_migrations` table (DB migration 0055):
  `(project_id, migration_number, batch_index, status:
  pending|pr_open|merged|failed, opened_pr_url, merged_at,
  error_kind, error_detail, total_batches)`. Unique on
  `(project_id, migration_number, batch_index)`. Re-running skips
  `status='pr_open'` rows and any migration with
  `NUMBER <= project.template_version`. Advisory lock on
  `(project_id)` serialises concurrent runs per project.
- **Batching.** Migrations exceeding
  `template_migration_max_files_per_pr` (default 50) and flagged
  `ALLOW_BATCHING=True` split into numbered batches (`-1`, `-2`...).
  Without `ALLOW_BATCHING`, the run fails fast — no partial PR opened.
  The final batch PR carries the `template_version` bump in
  `system/repos.yaml`; earlier batches note "version bump in batch
  N/N."
- **Sequential ordering.** Migrations apply in ascending `NUMBER`
  order per project; N+1's PR opens only after N merges. A failure on
  project A does not block project B. Failed rows are terminal —
  recovery is a new higher-numbered migration with the corrected logic.
- **Schema-drift API signal.** Workers and callers may pass
  `?min_schema_version=N` on knowledge fetch endpoints to receive
  `409 SCHEMA_DRIFT` when the project's `template_version < N`, with
  `pending_migrations` in the body. See
  [knowledge-api](./knowledge-api.md).
- **Alias-tolerance.** Rename migrations declare an alias on the CI
  validator (ADR 0008); the validator accepts both old and new field
  names while any project is below the migration's `target_version`;
  the alias auto-removes once the admin matrix shows fleet-wide
  adoption. Pre-work must land before any rename migration ships.
- **Flag-gated.** `CODER_TEMPLATE_MIGRATIONS_ENABLED` (default off on
  first deploy). Per-project tri-state
  `projects.template_migrations_enabled` (NULL = inherit fleet).

## Non-goals

- Body rewrites — migration touches frontmatter fields and folder/file
  shape only; markdown bodies are unchanged.
- ADR rewrites — ADRs are append-only; existing ADRs are exempt; new
  ADRs inherit updated fields via `template/adrs/_TEMPLATE.md`.
- Auto-merging migration PRs — human merge required even for
  pure-rename migrations.
- `coder-system` self-migration — the schema author hand-curates
  `coder-system/` in the same PR that adds the migration file.
- Live on-read transformation — 409 SCHEMA_DRIFT is the explicit
  signal; no on-the-fly shape coercion at read time.
- Cross-project migrations (moving an artifact between projects).

## Metrics

- **Mean time to fleet adoption** — migration merged in `coder-system`
  to all project PRs merged. Target: ≤ 1 week median.
- **Migration failure rate** — `status='failed'` rows per migration
  number; > 0 is a code-quality signal.
- **PR-open age** — > 14 days flags an abandoned migration PR.
- **Per-project pending count** — visible on the admin matrix;
  persistently high signals reviewer-availability issues.
- **Schema-drift 409 rate** — `?min_schema_version=` caller 409s per
  project per week; high rate signals urgent PR backlog.

## Interfaces

- Cloud Run Job: `coder-core-template-migrate`.
- `POST /v1/_admin/template/migrate` — oneshot trigger (admin JWT).
- `GET /v1/projects/{id}/template/version` — `{template_version,
  current_version, pending: [{number, slug, description}]}`
  (per-project auth).
- `GET /v1/_admin/template/migrations` — fleet migration matrix
  `[{project_id, template_version, pending_count,
  oldest_pending_pr_age, last_attempted_at, last_error}]`
  (admin JWT).
- `GET /v1/projects/{id}/knowledge/{type}/{artifact_id}?min_schema_version=N`
  — 409 SCHEMA_DRIFT when `template_version < N`; see knowledge-api.
- Admin: `/admin/template-migrations` fleet matrix;
  `/projects/:id/template-migrations` per-project tab.
  Both behind `VITE_TEMPLATE_MIGRATIONS_ENABLED`.
- CLI: `coder migrate test --against ./fixture-repo`.
- Runbook: `system/runbooks/template-migration.md`.
- Env: `CODER_TEMPLATE_MIGRATIONS_ENABLED`,
  `projects.template_migrations_enabled`,
  `template_migration_max_files_per_pr`.

## Dependencies

- knowledge-api — `min_schema_version` param, version/matrix
  endpoints.
- onboarding — new projects seeded at current version.
- admin-panel — fleet matrix and per-project tab.
- audit-log — `template_migration.*` action namespace.
- Postgres — `template_migrations` table (DB migration 0055).

## Links

- Design: [0047-template-schema-migration](../../designs/wip/0047-template-schema-migration.md)
  (WIP; link to active once design ships).
- Related specs: [knowledge-api](./knowledge-api.md),
  [onboarding](./onboarding.md), [admin-panel](./admin-panel.md),
  [audit-log](./audit-log.md),
  [knowledge-freshness](./knowledge-freshness.md).

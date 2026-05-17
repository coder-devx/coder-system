---
id: template-schema-migration
title: Template schema migration
type: design
status: active
owner: ro
created: '2026-04-19'
updated: '2026-05-17'
last_verified_at: '2026-05-17'
summary: Migrate managed-project knowledge repos when the template schema changes.
implements_specs: []
decided_by:
- '0019'
- '0020'
- '0021'
related_designs:
- knowledge-write-api
- knowledge-repo-model
- audit-log
- system-overview
- worker-communication
- managed-repo-action-distribution
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-system
parent: knowledge-and-admin
---

# Template schema migration

## What it does today

Codifies the process for evolving the canonical `coder-system/template/`
schema and rolling each change across every managed project's knowledge
repo via PRs. Schema authors add a migration file to
`coder-system/migrations/knowledge/`; a Cloud Run Job applies migrations
per-project in sequential order, tracks state in `template_migrations`,
and opens one PR per project per migration. A GitHub Action callback
records merge completion and bumps each project's `template_version`.

## Architecture

```mermaid
flowchart TB
  author["Schema author"] --> file["coder-system/migrations/knowledge/<br/>00NN-*.py or .yaml"]
  file -->|weekly cron OR admin POST| trig["POST /v1/_admin/template/migrate"]
  trig --> runner["coder-core-template-migrate<br/>(Cloud Run Job)"]
  runner -->|pg_try_advisory_lock(hash(project_id))| lock["Per-project<br/>serialisation"]
  lock --> pre["Preflight:<br/>read repos.yaml,<br/>extract template_version,<br/>compute pending"]
  pre --> view["KnowledgeRepoView<br/>(in-memory snapshot)"]
  view --> exec["Execute migration<br/>(SDK migrate() or YAML)"]
  exec --> batch["Batcher<br/>≤50 files/PR"]
  batch --> trees["build_and_push_tree<br/>(shared with /ship)"]
  trees --> pr["Open PR<br/>row: status=pr_open"]
  pr -.->|merge| action["record-template-migration<br/>(GitHub Action)"]
  action -->|/merged callback| merged["row → merged<br/>bump repos.yaml<br/>template_version"]
```

### Parts

- **SDK (`coder_core/migrations/knowledge/sdk.py`)** — pure dataclasses; read-only `KnowledgeRepoView`; CI-enforced no cross-module imports.
- **Runner (`coder_core/migrations/knowledge/runner.py`)** — Cloud Run Job entry; preflight → snapshot → execute → batch; idempotency via advisory lock + `template_migrations` rows.
- **Git Trees helper (`coder_core/migrations/knowledge/git_trees.py`)** — reused from `/ship`; exposes `build_and_push_tree(...)`.
- **YAML interpreter (`coder_core/migrations/knowledge/yaml_interp.py`)** — declarative ops: rename / add / remove frontmatter keys, move / rename folders.
- **`template_migrations` table** — PK `(project_id, migration_number, batch_index)`; tracks state `pending | pr_open | merged | failed | abandoned`.
- **`record-template-migration.yml`** — GitHub Action (distributed via [managed-repo-action-distribution](./managed-repo-action-distribution.md)); fires on PR merge; POSTs callback.

### Data flow

A migration file lands in `coder-system` and passes CI validation
(schema author registers `VALIDATOR_ALIASES` for renames). Weekly
scheduler or admin request triggers `/v1/_admin/template/migrate`,
dispatching the Cloud Run Job. Per project: runner fetches snapshot,
executes the migration against the read-only view, batches results
(≤50 files), calls Git Trees to push branch-per-batch, opens a PR, and
inserts `template_migrations` rows. The GitHub Action fires on merge,
POSTs the callback, and the runner flips the row to `merged` while
bumping `template_version` in `repos.yaml`.

### Invariants

- **Strict per-project serialisation** — migration N+1 waits for N to merge; advisory lock prevents concurrent processing of the same project.
- **Idempotency** — a second runner invocation skips if a row exists with `status ∈ {pr_open, merged}` at the same `(project, migration_number)`.
- **Fail-strict on parse errors** — malformed frontmatter aborts the migration for that project; no partial PR opened.
- **No silent schema coercion** — read path returns artifacts as-is; `GET /knowledge/{type}/{id}?min_schema_version=N` returns `409 SCHEMA_DRIFT` if `template_version < N`.
- **Alias-tolerance window** — during rename migrations the validator accepts both old and new field names; window closes when fleet adoption reaches 100% (`template_version` check, per ADR 0019).
- **Registry is the filesystem** — `coder-system/migrations/knowledge/` is the migration definition; `template_migrations` tracks execution state only.

## Interfaces

| Surface | Effect |
|---|---|
| `POST /v1/_admin/template/migrate` `{migration_numbers?, projects?, dry_run?}` | Dispatches Cloud Run Job; returns `{run_id, scheduled_jobs}` |
| `GET /v1/_admin/template/migrations[?status=&project_id=&migration_number=]` | Fleet matrix of `template_migrations` rows (admin) |
| `GET /v1/projects/{id}/template/version` | Returns `{template_version, current_version, pending: []}` |
| `POST /v1/_admin/template/migrations/{project}/{n}/{batch}/merged` | Callback from GitHub Action; flips row → merged, bumps version |
| `PATCH /v1/_admin/template/migrations/{project}/{n}/{batch}/abandon` | Operator rollback; flips row → abandoned |
| `GET /knowledge/{type}/{id}?min_schema_version=N` | `409 SCHEMA_DRIFT` if `template_version < N` (with pending list) |
| `coder migrate test --migration 00NN-… --against ./fixture-repo` | CLI; runs against fixture; prints `FileChange[]`; no network |
| `coder migrate status [--project <slug>]` | CLI; prints matrix or single project |
| Prometheus: `template_migration_run_total`, `_files_changed_total`, `_pending_count` | Observability |

## Where in code

- `src/coder_core/migrations/knowledge/sdk.py` — `KnowledgeRepoView` (immutable snapshot)
- `src/coder_core/migrations/knowledge/runner.py` — Cloud Run Job entry; preflight + execute + batch
- `src/coder_core/migrations/knowledge/git_trees.py` — `build_and_push_tree` (shared with `/ship`)
- `src/coder_core/migrations/knowledge/yaml_interp.py` — YAML declarative interpreter
- `src/coder_core/migrations/knowledge/callbacks.py` — `handle_migration_merged`
- `coder-system/template/.github/workflows/record-template-migration.yml` — distributed via [managed-repo-action-distribution](./managed-repo-action-distribution.md)

## Evolution

Sealed 2026-04-28. ADRs in flight: 0019 (alias-tolerance fleet-completion gate), 0020 (worker-dispatched async runner vs sync API handler), 0021 (two-migration deprecation path for field removal).

## Links

- Spec: [0047-template-schema-migration](../../../product-specs/wip/0047-template-schema-migration.md)
- ADRs: [0019](../../../adrs/0019-alias-tolerance-fleet-completion-gate.md), [0020](../../../adrs/0020-worker-dispatched-migration-runner.md), [0021](../../../adrs/0021-deprecate-then-remove-two-migrations.md), [0008](../../../adrs/0008-ci-validation-of-knowledge-repo.md)
- Designs: [knowledge-write-api](./knowledge-write-api.md), [knowledge-repo-model](./knowledge-repo-model.md), [managed-repo-action-distribution](./managed-repo-action-distribution.md), [audit-log](../tenancy/audit-log.md)
- Repos: coder-core, coder-system

---
id: branch-cleanup
title: Branch cleanup
type: spec
status: active
owner: ro
created: 2026-04-15
updated: 2026-05-03
last_verified_at: 2026-05-03
served_by_designs: [branch-cleanup]
related_specs: [developer-worker, task-orchestration, observability]
parent: pipeline-operations
---

# Branch cleanup

## What it is

A scheduled job inside `coder-core` that deletes stale `task/<slug>`
branches from a managed project's GitHub repositories once the
underlying task has exited the pipeline and no open PR still
references the branch. Keeps each project's branch list free of
Coder-generated noise without an operator ever reaching for
`git push --delete`.

## Capabilities

- Enumerates branches prefixed `task/` per repo declared in a
  project's `system/repos.yaml`; other branches are never touched.
- Maps each branch to its originating task row via the
  `tasks.branch_name` column (populated by the developer worker on
  push).
- Deletes a branch only when ALL of: age > 24h, task terminal
  (`accepted` / `rejected` / `stuck` — or terminal worker status for
  legacy rows), no open PR. Orphan branches (no task row) are deleted
  only after a 7-day grace.
- Fails closed on uncertainty: any API hiccup records an error event
  and skips the branch rather than deleting it.
- Records every decision (delete, skip-with-reason, error) in the
  `gc_events` audit table, grouped by a per-pass `run_id`.
- Supports dry-run mode that logs the candidate deletions without
  calling GitHub.
- Per-project opt-out via `projects.gc_enabled` for incident freezes.

## Interfaces

- **Cron trigger (internal):** Cloud Scheduler hits
  `POST /v1/_admin/gc/branches` hourly. Body:
  `{"dry_run": false}` for the production pass; `{"project_id": "<id>",
  "dry_run": true}` for operator diagnostics.
- **Admin queries:**
  - `GET /v1/_admin/gc/runs?project_id=&limit=` — list recent runs with
    per-action counters.
  - `GET /v1/_admin/gc/runs/{run_id}` — full event trail for one run.
  - `GET /v1/_admin/gc/metrics?period=1d|7d|30d` — aggregate counters
    (`deleted_total`, `errors_total`, `skipped_total`,
    `dry_run_deleted_total`, `false_delete_total`).
- **Database:** writes `gc_events`; reads `tasks`, `projects`.

## Dependencies

- **GitHub API** (via `GitHubClient.list_branches / list_pulls /
  delete_branch`) — per-repo short-lived installation tokens.
- **Cloud Scheduler** — the hourly trigger.
- **Developer worker** — populates `tasks.branch_name` on push so the
  task-lookup path works.
- **Observability** — consumes the `metrics` endpoint for dashboards
  and `false_delete_total` alerting.

## Evolution

- 2026-04-15 — shipped (spec 0023, PR coder-devx/coder-core#10). Added
  `tasks.branch_name`, `projects.gc_enabled`, `gc_events` table,
  `ops/branch_gc.py`, admin endpoints, developer-worker branch
  capture, runbook.

## Links

- Design: [branch-cleanup](../../designs/active/branch-cleanup.md)
- Runbook: [branch-gc](../../runbooks/branch-gc.md)
- Related components: [developer-worker](./developer-worker.md),
  [task-orchestration](./task-orchestration.md),
  [observability](./observability.md)

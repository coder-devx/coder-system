---
id: developer-worker
title: Developer worker
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-14
last_verified_at: 2026-05-14
summary: Developer worker — code, tests, PRs.
served_by_designs: []
related_specs: [branch-cleanup, reviewer-worker, service-accounts, task-orchestration, tenant-isolation]
parent: worker-roles
---

# Developer worker

## What it is

The developer worker is the role inside `coder-core` that turns a task
prompt into a shippable pull request. It leases a `role=developer` task
from the Postgres queue, shells out to the `claude` CLI against a
per-task clone of the project's repo, and ends the run with a branch
pushed and a PR opened on GitHub. Everything downstream in the pipeline
(reviewer, acceptance, merge, deploy) keys off the PR URL this worker
produces.

## Capabilities

- Leases queued tasks race-free via
  `SELECT ... FOR UPDATE SKIP LOCKED`; concurrent workers never
  double-claim.
- Clones the target repo into a per-task tempdir, authed by a fresh
  GitHub-App installation token, and cleans up via `try/finally` on
  exit (including timeouts).
- Runs `claude` with a built-in developer system prompt instructing it
  to branch (`task/{task_id}`), commit, push, and `gh pr create` with
  a structured title and body referencing the task and spec.
- Captures the JSONL session transcript and buffers per-task structured
  logs (tagged with `project_id`, `task_id`, `role=developer`) into the
  `task_logs` table in one transaction with the outcome write.
- Extracts the PR URL from the claude output and persists it to
  `tasks.pr_url`; a failed push or missing PR URL fails the task
  rather than silently succeeding.
- Distinct lifecycle states: `succeeded`, `failed` (with captured
  stderr/traceback), `timed_out` (workspace cleaned).
- Accepts a `fix_context` prefix on retry prompts so prior reviewer
  feedback flows into the next attempt.
- Captures the `task/<slug>` branch name on push via
  `git rev-parse --abbrev-ref HEAD` and persists it to
  `tasks.branch_name` — the key the branch-cleanup GC uses to map a
  remote branch back to its task row.
- **Transient-failure retry.** The `claude` spawn is wrapped in the
  shared `run_with_transient_retry` helper; Anthropic 429/529,
  socket resets, and DNS blips re-spawn with full-jitter exponential
  backoff up to a bounded budget before surfacing. Budget
  exhaustion lands `failure_kind="transient"` on the task row;
  success-after-retry populates `transient_retry_history` so the
  admin panel renders a "recovered after N transient retries" chip.
  The per-task deadline is distinct: a deadline hit surfaces as
  `TaskStatus.TIMED_OUT`, not retried.
- **Lint pre-flight hard gate.** After `ruff format` + `ruff check
  --fix` complete, if surviving failures remain the worker runs one
  fix-loop iteration (re-prompt with the lint output injected as
  context, re-stage files, re-run pre-flight) before opening the PR.
  If the second pass is clean, the PR opens normally. If lint still
  fails, the task exits with `failure_kind="lint_preflight_failed"`
  and `failure_detail` populated with the surviving output (truncated
  to ~2 KB); no PR is opened. The fix-loop iteration draws from the
  existing `developer.fix_attempts` budget; if lint remediation
  somehow consumes >10 turns the gate surfaces `lint_preflight_failed`
  early. The clean-path (zero first-pass failures) is unaffected —
  the fix-loop iteration does not run. Operator recovery: retry via
  `POST /v1/projects/{id}/tasks/{task_id}/override` with
  `{"action": "retry"}`.
- **Migration head-conflict pre-commit gate.** After staging any file
  under `migrations/versions/`, the worker runs `uv run alembic heads`.
  If the output contains more than one revision id, the worker refuses
  to open the PR, logs a structured `developer.migration_head_conflict_refusal`
  event, and exits with `failure_kind="migration_head_conflict"` (`failure_detail`
  populated with the raw `alembic heads` output). Exactly one head after
  staging is the fast path — unaffected. Tasks with no changes under
  `migrations/versions/` skip the gate entirely. Operator recovery:
  `POST /v1/projects/{id}/tasks/{task_id}/override` with
  `{"action": "retry"}` after rebasing the migration to a clean head.
- **Prod-creds isolation.** Before spawning the `claude` subprocess,
  the worker's env-construction stage explicitly removes
  `CLOUD_SQL_INSTANCE`, `CLOUD_SQL_USER`, `CLOUD_SQL_DATABASE`,
  `DATABASE_URL`, `PGHOST`, `PGUSER`, `PGPASSWORD`, and `PGDATABASE`
  from the inherited env and replaces them with a DSN pointing at an
  ephemeral, per-turn test DB:
  - *SQLite in-memory* (default) — `sqlite+aiosqlite:///:memory:`
    exposed via `DATABASE_URL`. Sufficient for most dev tasks;
    PG-only migration guards (`if bind.dialect.name != "postgresql"`)
    no-op cleanly.
  - *Postgres-15 test container* (opt-in) — when
    `needs_postgres_test_db: true` appears in the task prompt, the
    harness boots a throwaway postgres-15 container, exposes its DSN
    via `DATABASE_URL`, and tears it down on subprocess exit (~30 s
    overhead; estimated <5 % of dev turns).
  The strip is logged as a `worker.prod_creds_stripped` audit event
  on every dispatch, carrying `task_id` and the comma-separated list
  of stripped env keys. Implemented in
  `coder_core/workers/_auth_env.py` and the new
  `coder_core/workers/_test_db.py` module.

## Interfaces

- **Consumes:** task rows with `role=developer`, `prompt`, `repo`,
  optional `spec_id` and `fix_context`.
- **Produces:** commit + feature branch + PR on GitHub, writes back
  `pr_url`, `result`, `status`, `finished_at`, and a `task_logs`
  stream.
- **Surfaced via:** `GET /v1/projects/{id}/tasks/{task_id}`,
  `/tasks/{task_id}/logs`, and the admin pipeline detail view.
- **Code:** `src/coder_core/workers/developer.py`,
  `src/coder_core/workers/workspace.py`; prompt at
  `system/roles/developer.md`.

## Dependencies

- Postgres task queue and `tasks` / `task_logs` tables.
- GitHub App installation for repo clone, push, and `gh pr create`
  (`GH_TOKEN` exported into the workspace).
- Developer-role service account + Anthropic key broker for the
  `claude` subprocess.
- Orchestrator for stage transitions and fix-loop dispatch.

## Evolution

- 2026-04 — v1 worker + leasing + workspace + transcripts + PR flow +
  branch-name capture + transient-failure retry (specs 0004, 0020,
  0023, 0027).
- 2026-04-28 — GH_TOKEN unified through `_github_env.apply_github_token_env`;
  orchestrator-side GitHub PR-URL reconciliation closes the
  "PR exists but task stuck" gap (specs 0054, 0055).
- 2026-05 — Hard pre-flight gates on lint, alembic head-conflict, and
  prod-credential isolation; the last responds to the 2026-05-12
  prod-DB incident (specs 0082, 0087, 0088).

## Links

- Designs: [worker-roles](../../../designs/active/worker-roles.md)
- Related components: [reviewer-worker](./reviewer-worker.md),
  [task-orchestration](../pipeline/task-orchestration.md),
  [branch-cleanup](../pipeline/branch-cleanup.md),
  [service-accounts](../tenancy/service-accounts.md),
  [tenant-isolation](../delivery/tenant-isolation.md)

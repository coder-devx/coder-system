---
id: developer-worker
title: Developer worker
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-12
last_verified_at: 2026-05-12
summary: Developer worker — code, tests, PRs.
served_by_designs: [worker-roles]
related_specs: []
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
- **`pr_url` guard on retry.** Before opening a new PR the worker
  checks `task.pr_url`. If set, it reads the existing PR's state via
  the GitHub REST API and branches on three outcomes: (1) PR is
  open-and-unmerged — the worker resumes against the existing branch
  (`git checkout <existing_branch>`) and pushes new commits there;
  no second PR is opened and `pr_url` stays the same. (2) PR is
  merged — the task's prior work already shipped; the worker exits
  with `failure_kind=duplicate_retry_on_merged_pr`, logs a
  structured event, and opens no new PR; the orchestrator's unblock
  check picks up downstream tasks. (3) PR is closed without merging
  (operator-killed) — the worker proceeds as normal, opening a fresh
  PR. A distinct log line (`developer.pr_state_check_operator_killed`)
  distinguishes this from the no-prior-pr_url case. The check is
  fail-open: a GitHub API error logs `developer.pr_state_check_failed`
  and falls through to the existing open-fresh-PR behaviour — no new
  hang path on a transient GitHub outage.

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

- 0004 — in-process worker, race-free leasing, per-task workspace,
  JSONL transcript capture, `task_logs` table, `timed_out` state.
- 0020 — branch/commit/push/PR flow, `pr_url` column (migration 0016),
  reviewer prompt receives the PR URL, hard failure on missing PR.
- 0023 — capture `tasks.branch_name` (migration 0019) on push so the
  [branch-cleanup](./branch-cleanup.md) GC can resolve remote
  `task/*` branches back to their task rows.
- 0027 — worker transient-failure retry: `_transient.classify` +
  `run_with_transient_retry` wrap the claude spawn. Migration 0021
  adds `tasks.transient_retry_history`. ADR 0013 documents why the
  retry loop lives inside the worker and not at the dispatcher; the
  pre-0027 dispatcher-level wrapper was removed on ship.
- `0054` — Orchestrator GitHub-state reconciliation (shipped
  2026-04-28, revision `coder-core-00161-ln6`): when a developer task
  succeeds but the worker stdout didn't include the PR URL, the
  orchestrator now queries GitHub for an open PR on the task's
  `branch_name` before marking the task STUCK — eliminating the
  "PR exists but task is stuck" false-positive class. Worker-authored
  PRs only (`pr.user.type == 'Bot'`, per ADR 0016); fail-soft to the
  existing STUCK path on any GitHub API error. Flag-gated via
  `coder_orchestrator_pr_url_reconcile_enabled`. See
  [task-orchestration](./task-orchestration.md) Evolution for the
  full implementation detail.
- 0055 — `GH_TOKEN` injection refactored through the shared
  `_github_env.apply_github_token_env` helper (no behaviour change).
  The inline `env["GH_TOKEN"] = task.workspace.github_token` access
  becomes a call site that prefers the workspace token and falls
  back to the dispatcher-resolved `WorkerInput.github_token`. Lifts
  the credential out of workspace-prep so the same helper serves
  every role worker.
- 0084 — `pr_url` guard against duplicate PRs on retry. Before the
  PR-open step, the worker inspects `task.pr_url`; if set it reads the
  existing PR state from the GitHub REST API and branches: open →
  resume on existing branch (no new PR); merged →
  `failure_kind=duplicate_retry_on_merged_pr`, clean exit; closed →
  proceed fresh. API errors fall through (fail-open). Eliminates
  operator-side duplicate-PR closures on retry (Phase A: seven
  closures tracked in gap #8 of the Phase A note).

## Links

- Designs: [worker-roles](../../designs/active/worker-roles.md)
- Related components: [reviewer-worker](./reviewer-worker.md),
  [task-orchestration](./task-orchestration.md),
  [branch-cleanup](./branch-cleanup.md),
  [service-accounts](./service-accounts.md)

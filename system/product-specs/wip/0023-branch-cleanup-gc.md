---
id: "0023"
title: Branch cleanup GC job
type: spec
status: wip
owner: ro
created: 2026-04-15
updated: 2026-04-15
served_by_designs:
- "0023"
related_specs:
- developer-worker
- task-orchestration
---

# Branch cleanup GC job

## Problem

The developer worker creates one `task/<task_id>` branch per dispatch
in the project's GitHub repo. When a task fails, times out, or has its
PR closed without a merge, the branch is left behind. Over days of
dog-fooding, stale branches accumulate: they clutter GitHub's branch
UI, pollute `git branch -a` for human contributors, and will eventually
bump against GitHub's soft limits on per-repo branch count for CI webhook
fan-out. There's no automated cleanup today — every stale branch is a
piece of manual ops work nobody owns.

## Users / personas

- **Operators** running the Coder system across multiple projects.
  Today they either ignore branch clutter or run ad-hoc `git push --delete`
  scripts.
- **Project contributors** (human developers on the managed projects),
  who see branch-list noise in their repos that isn't their work.

## Goals

- Stale `task/*` branches disappear automatically within 24h of a task
  reaching a terminal state with no open PR.
- Operators never need to hand-delete a developer-worker branch.
- Cleanup is safe: branches with open PRs, recently-created branches,
  and non-`task/*` branches are never touched.
- Deletions are auditable — which branch, when, by which GC run.

## Non-goals

- Cleaning up forks, tags, or non-`task/*` branches.
- Deleting merged `task/*` branches (GitHub's built-in "auto-delete
  branch on merge" already handles that — we enable it per repo, we
  don't reinvent it).
- Squash/rebase policy changes to the developer worker.
- Cleaning up branches in non-Coder-managed repos.

## Scope

1. **Identification.** `task_id → branch_name` must be recoverable.
   Either add a `branch_name` column to the `tasks` table (populated by
   the developer worker when it pushes) or derive deterministically
   from `task_id` (`task/<short-uuid>`). Pick one and document.
2. **GC pass.** A scheduled job ("gc worker" or a Cloud Scheduler cron
   calling a `coder-core` endpoint) runs hourly. For each project:
   - List `task/*` branches via the GitHub API.
   - For each candidate, confirm eligibility:
     - Branch name matches `task/*` (safety guard).
     - Branch age > 24h.
     - Associated task is in a terminal state (`accepted`, `failed`,
       `timed_out`, `rejected`).
     - No open PR references the branch.
   - Delete eligible branches and record the deletion.
3. **Audit.** Every deletion produces a structured log line and a row
   in an audit/history table (or re-uses `task_logs` with a `gc` role
   marker — spec defers to architect).
4. **Failure mode.** A GC failure on one branch must not block deletions
   of other eligible branches. Errors are logged and counted; threshold
   alerts re-use the observability component's Slack pipeline.
5. **Dry-run.** The job supports a dry-run mode (env flag or request
   param) that logs what it *would* delete without deleting. Operators
   use this during rollout.

## Acceptance criteria

- [ ] `task/*` branches older than 24h with a terminal task and no open
      PR are deleted within one hour of becoming eligible.
- [ ] `task/*` branches with an open PR are never deleted, regardless
      of age.
- [ ] Non-`task/*` branches are never enumerated, let alone deleted.
- [ ] A deletion records: project, branch name, task id, GC run id,
      timestamp, and actor (the GC worker's service account).
- [ ] Dry-run mode logs candidate deletions without issuing any
      GitHub delete calls.
- [ ] An error deleting one branch does not abort the GC pass —
      remaining candidates are still processed.
- [ ] The GC run exposes `gc_branches_deleted_total` and
      `gc_branches_errors_total` counters consumable by the
      observability component.
- [ ] A runbook entry covers: enabling/disabling GC per project,
      running a one-off dry-run, and forcing deletion of a specific
      branch.

## Metrics

- **Primary:** median age of oldest `task/*` branch across managed
  projects ≤ 48h (was: unbounded).
- **Secondary:** zero manual `git push --delete` operations needed in
  a given week across all Coder-managed repos.
- **Guardrail:** zero false deletions (branch deleted while PR was
  still open, or branch not matching `task/*`). Tracked via alert on
  `gc_branches_false_delete_total`.

## Open questions

- Separate `gc` worker role vs. endpoint-triggered cron in `coder-core`?
  Architect decision. A worker keeps it consistent with the role model;
  a cron endpoint is ~10 lines. Trade-off: separate role = separate
  IAM + logs + retries; endpoint = simpler but dispatcher-less.
- Eligibility when the task row has been hard-deleted (shouldn't happen
  today but future retention policies might). Default: orphaned
  `task/*` branches older than 7d are eligible even without a task row.
- Per-project opt-out knob? Default on everywhere, but someone might
  want manual control during an incident.

## Links

- Extends: [`developer-worker`](../active/developer-worker.md),
  [`task-orchestration`](../active/task-orchestration.md)
- Related observability surface: [`observability`](../active/observability.md)
- Roadmap entry: [ROADMAP.md § Phase 3 — 0023](../ROADMAP.md)

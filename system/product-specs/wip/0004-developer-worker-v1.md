---
id: "0004"
title: Developer worker v1
type: spec
status: wip
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0001", "0002", "0005", "0006"]
---

# Developer worker v1

**Phase:** Next (first real work gets done)
**Progress:** 4 / 7 acceptance criteria

## Problem

With projects, the knowledge API, and a read-only admin panel in place,
`coder-core` can describe work but cannot *do* work. The first role we
need on the new system is the **Developer** — a worker that picks up a
task from a queue and runs the existing `enrich → execute → fix →
test` loop against a project's repos. Until a developer worker exists
end-to-end, nothing downstream (reviewer, QA, release manager) has
anything to react to, and the rebuild can't prove parity with the old
`coder-agent`.

## Users / personas

- **Developer role** inside `coder-core` — this is the worker itself.
- **Ro (human owner)** — enqueues tasks and watches them run, validating
  that a real code change gets produced.
- **Software Architect** — needs to see the worker operate strictly
  under its role boundary (doesn't reach into PM or Reviewer territory).
- **Future Reviewer worker** — consumes the developer's output; the
  shape of what the developer produces is this spec's contract to them.

## Goals

- A `developer` worker module in `coder-core` that polls a Postgres task
  queue and processes `developer` tasks.
- The worker runs the `enrich → execute → fix → test` loop end-to-end
  against a real project's repo checked out in an isolated workspace.
- Every step emits structured logs tagged with `project_id`, `task_id`,
  and `role=developer`.
- The worker writes its output (branch, commit SHA, test results, notes)
  back into the task row and emits a completion event.
- Task failures don't crash the worker — they land the task in a
  `failed` state with captured stderr and tracebacks.

## Non-goals

- Multi-developer parallelism across projects (v1 = one worker, one
  task at a time; concurrency is a later spec).
- Reviewer, QA, or Release Manager workers — each of those is its own
  spec.
- Human-in-the-loop approval gates inside the loop — v1 runs
  unattended; escalation surfaces in the admin panel (spec `0006`).
- Long-running background agents — task runs are bounded by a timeout.

## Scope

- `developer_tasks` table: `id`, `project_id`, `repo`, `branch`, `prompt`,
  `status`, `assigned_at`, `finished_at`, `result_json`, `error_text`.
- Worker loop: lease a task with `SELECT ... FOR UPDATE SKIP LOCKED`,
  process it, commit status + result.
- Repo workspace manager: shallow clone the project's repo into a
  per-task temp dir, set up a working branch, tear it down on exit.
- `enrich → execute → fix → test` implementation porting the VibeTrade
  pipeline logic, but parameterised by project (no hard-coded paths).
- Per-task structured logs streamed into a `task_logs` table.
- Completion event published on the Core event bus for downstream
  consumers.

## Acceptance criteria

- [x] Enqueuing a task for a seeded project results in the worker
      claiming and running it within 5 seconds.
- [x] A successful task produces a commit on a feature branch in the
      project's repo with test output captured.
- [x] A failing task transitions to `failed` with a captured error and
      does not block subsequent tasks.
- [ ] Two workers running against the same queue never double-claim a
      task (tested under contention).
- [ ] Structured logs for a task can be fetched from the Core API and
      contain `project_id`, `task_id`, and `role=developer` on every
      line.
- [ ] A task that exceeds its timeout is terminated and marked
      `timed_out`, with the workspace cleaned up.
- [x] The worker's git operations use a credential scoped to the
      developer role's service account (stub in v1, real in spec `0005`).

## Metrics

- **Task throughput:** at least one successful developer task per minute
  on a seed project.
- **Failure recovery:** 0 "stuck running" tasks after a worker crash
  (validated with a kill -9 test).
- **Log fidelity:** 100% of task executions have full logs retrievable
  via the Core API.

## Open questions

- Workspace location and cleanup — `/tmp` per task, or a persistent
  per-project cache with cleanup sweeper?
- Task timeout default (30m? 2h?) and how it's overridden per task.
- Do we reuse the VibeTrade prompt scaffolding verbatim, or rewrite it
  project-parameterised from scratch?

## Links

- Designs: [`0004`](../../designs/wip/0001-generalize-coder-from-vibetrade.md) (build plan step 4), [`0002`](../../designs/active/0002-worker-roles-and-impersonation.md)
- Roles: [`developer`](../../roles/developer.md)
- Related specs: [`0001`](./0001-multi-tenant-project-crud.md), [`0002`](./0002-knowledge-repo-read-api.md), [`0005`](./0005-per-role-service-accounts.md), [`0006`](./0006-pipeline-ui-in-admin.md)

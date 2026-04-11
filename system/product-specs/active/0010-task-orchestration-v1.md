---
id: "0010"
title: Task orchestration v1
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-11
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0004", "0009"]
---

# Task orchestration v1

**Phase:** Shipped
**Progress:** 7 / 7 acceptance criteria ✅

## Problem

Tasks flow through multiple stages (enrich → execute → test → review →
accept) but there is no state machine managing transitions. Workers run
in isolation; there is no fix loop when a stage fails, no way to retry
from where it stopped, and no way for the human to pause or override a
running pipeline without killing the task entirely.

## Users / personas

- **Human operator** — needs visibility into where a task is in the
  pipeline and the ability to intervene (pause, retry, skip) without
  restarting from scratch.
- **Developer worker** — needs fix-loop context (what failed and why)
  prepended to its prompt when retrying.

## Goals

- A Postgres-backed state machine covering the full task lifecycle.
- Automatic fix loops (max 3 attempts) on failure with context carried
  forward.
- Human override at any stage: pause, resume, retry, skip, reject.

## Non-goals

- Cross-task dependencies or DAG scheduling (single-task pipeline only).
- Distributed worker coordination (single orchestrator process for now).
- SLA enforcement or deadline-based escalation.

## Scope

A `TaskStage` enum and `orchestrate_task` loop in
`workers/orchestrator.py`:

- Stages: `queued → enriched → executing → testing → reviewing →
  accepted | rejected | failed`.
- Fix loop: on `failed`, if `fix_attempts < 3`, prepend `fix_context`
  to the prompt and retry from `executing`.
- Override endpoint: `POST /v1/projects/{id}/tasks/{id}/override` with
  actions `pause | resume | retry | skip_to_stage | reject`.
- List filter: `?stage=` on task list.
- Structured logging at every stage transition.

## Acceptance criteria

- [x] AC1: `stage` column exists on tasks; new tasks start at `queued`.
- [x] AC2: The orchestrator advances a task through all stages to
  `accepted` on the happy path without manual intervention.
- [x] AC3: On failure, the orchestrator retries up to 3 times, prepending
  `fix_context` (error + failing output) to the prompt each time.
- [x] AC4: After 3 failed attempts the task moves to `failed` and the
  fix loop stops.
- [x] AC5: `POST /{task_id}/override` supports pause, resume, retry,
  skip_to_stage, and reject actions.
- [x] AC6: `GET /v1/projects/{id}/tasks?stage=` filters correctly.
- [x] AC7: Stage transitions are logged with structured fields (task_id,
  from_stage, to_stage, timestamp).

## What shipped

Migration 0010 adds `stage`, `fix_attempts`, and `fix_context` columns
plus `ix_tasks_stage` index. `TaskStage` enum covers the full lifecycle.
`workers/orchestrator.py` implements the `orchestrate_task` loop with
stage transitions, fix loops (max 3), and structured logging. Dispatcher
prepends `fix_context` to prompt for fix attempts. API: `stage=queued`
on create, `?stage=` filter on list, `POST /{task_id}/override`
(pause/resume/retry/skip_to_stage/reject). 19 new tests, 214 total
passing.

## Links

- Related specs: [`0004`](./0004-developer-worker-v1.md), [`0009`](./0009-reviewer-worker-v1.md)

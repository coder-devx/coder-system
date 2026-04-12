---
id: "0019"
title: "Task retry endpoint"
type: spec
status: active
owner: ro
created: "2026-04-12"
updated: "2026-04-12"
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0010", "0013"]
---

# Task retry endpoint

**Phase:** active
**Progress:** 7 / 7 acceptance criteria

## Problem

When a task enters a terminal failure state (`status=failed`, `status=timed_out`, or
`stage=stuck`) the only recovery path is to hand-craft a new task by copy-pasting the
original prompt and fields from the admin UI. This is error-prone, loses the link to the
failed attempt, and makes it impossible to audit retry chains. Operators need a one-click
retry that preserves the audit trail.

## Users / personas

- **Operators** monitoring the pipeline admin UI -- need a single action to re-queue a
  failed task without re-entering its prompt or looking up its spec.
- **Automated tooling** (CI scripts, future alert-response workers) -- need a stable API
  endpoint to retry stuck tasks programmatically.

## Goals

- Add `POST /v1/projects/{id}/tasks/{task_id}/retry` that creates a fresh task cloned
  from a failed or stuck original and returns it.
- Link the new task back to the original via an `original_task_id` column so retry chains
  are traceable in the audit log.
- Copy the fields an operator cares about (`role`, `prompt`, `repo`, `spec_id`) and reset
  execution state (`status`, `stage`, `fix_attempts`, etc.) to a clean start.
- Gate retries to tasks that are actually terminal so operators cannot accidentally
  double-dispatch a running task.

## Non-goals

- Retrying tasks in non-terminal states (`queued`, `running`, `succeeded`, `accepted`,
  `rejected`). Use the existing `/override` endpoint to re-queue non-terminal tasks.
- Cascading retry chains (retrying a retry is independent, not a linked chain).
- Copying `plan_id` / `plan_order` -- retries are standalone.

## Scope

**Retryable states** -- a task is retryable when ANY of the following is true:
- `status` is `failed` or `timed_out`, OR
- `stage` is `stuck`

**Copied fields** from original: `role`, `prompt`, `repo`, `spec_id`.

**Reset fields** on new task: `status=queued`, `stage=queued` (pipeline roles),
`fix_attempts=0`, `fix_context=null`, all execution/observability columns nulled.

**New column**: `original_task_id` (String 36, nullable FK -> tasks.id SET NULL),
migration 0015.

**Actor stamping**: new task's actor fields come from the caller making the retry, not
the original.

## Acceptance criteria

- [x] AC1: `POST /v1/projects/{id}/tasks/{task_id}/retry` returns `201 Created` with a
  `TaskCreated` body (including a fresh `worker_token`) when the original is retryable.
- [x] AC2: The new task's `original_task_id` equals the source task's `id`; `role`,
  `prompt`, `repo`, and `spec_id` match exactly.
- [x] AC3: New task starts with `status=queued`, `stage=queued`, `fix_attempts=0`;
  all execution-state fields are `null`.
- [x] AC4: Returns `422` with `code=task_not_retryable` when the original is in a
  non-retryable state (`queued`, `running`, `succeeded`, `accepted`, `rejected`).
- [x] AC5: Returns `404` when the task does not exist or belongs to a different project.
- [x] AC6: The original task row is not mutated; a `task_log` entry with
  `triggered_by=retry` and the `original_task_id` is written for audit.
- [x] AC7: Migration 0015 adds `original_task_id` (nullable FK -> tasks.id SET NULL) and
  the column appears in `TaskRead` responses.

## Open questions

- Legacy tasks (no `stage`): allow retry? Proposed: yes -- new task also has `stage=null`.
- Kick dispatcher immediately? Proposed: yes, same fire-and-forget as `create_task`.

## Links

- Existing override: `POST /v1/projects/{id}/tasks/{task_id}/override`
- Pipeline orchestration: spec 0010
- Plan traceability: spec 0013
- Domain model: `src/coder_core/domain/task.py`
- Task routes: `src/coder_core/api/tasks.py`

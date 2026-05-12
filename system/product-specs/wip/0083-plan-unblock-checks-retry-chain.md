---
id: '0083'
title: Plan-unblock check accounts for retry chain, not just original task's stage
type: spec
status: wip
owner: ro
created: '2026-05-12'
updated: '2026-05-12'
last_verified_at: '2026-05-12'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- task-orchestration
- developer-worker
parent: pipeline-operations
---

# Plan-unblock check accounts for retry chain, not just original task's stage

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

When a developer task fails or times out and the orchestrator (or operator) spawns a retry via `original_task_id`, the retry has `plan_order=NULL`. `_check_unblock_siblings` in `coder_core/workers/orchestrator.py` builds its dependency-resolution lookup keyed only on `plan_order`:

```
stage_by_order[t.plan_order] = t.stage   # ignores retries (plan_order=NULL)
```

So when a retry merges and lands stage `accepted`, the lookup is never updated. The downstream task at `plan_order = N+1` is `blocked` on `plan_order = N` being `accepted`. The retry's `plan_order` is `NULL`, so even though its work shipped, the unblock check doesn't see it. The downstream task stays blocked forever — or until an operator manually issues `POST /v1/projects/{id}/tasks/{original_task_id}/override` with `{"skip_to_stage": "accepted"}` on the *original* task (not the retry).

Every retry cycle hits this. The operator's recovery muscle memory now reflexively overrides the original, not the retry — but the muscle memory only forms after the operator has been bitten enough times to recognize the pattern. Memory's Phase A tracking note documents the pattern across at least three Phase A specs (0075 ord 4, 0079 ord 7, 0080 ord 2). Under Phase B's pressure, every Studio-approve dispatched task that retries will hit this gap.

The orchestrator's intent is clear from the code structure: a task's `plan_order` is its position in the plan, and a retry inherits its position via `original_task_id`. The bug is that `_check_unblock_siblings` doesn't follow the chain; it reads `plan_order` as a direct key without walking the retry-of-retry-of-original lineage.

## Users / personas

- **Operators driving spec runs through the orchestrator.** Today they must remember to override the *original* task (not the merged retry) every time a retry chain unblocks downstream work. Under Phase B's autopilot, they shouldn't have to.
- **Developer workers running retried tasks.** Currently produce shipped work that the orchestrator silently fails to recognize as plan-order progress.

## Goals

- When a task at `plan_order=N` is the original of a retry chain `T_orig → T_retry_1 → T_retry_2 → …`, the plan-unblock check sees the **maximum stage across the whole chain**. A merged-and-accepted retry unblocks `plan_order=N+1` even if the original is `stuck` or `timed_out`.
- The unblock lookup is order-independent: it produces the same result regardless of which task in a chain is queried first.
- Operator's `skip_to_stage=accepted` override remains available as a manual escape hatch for any task in the chain.
- No regression for the single-task case: a task with `plan_order=N` and no retries works exactly as today.

## Non-goals

- Refactoring `original_task_id` semantics. The chain is what it is.
- Auto-cancelling stuck originals when a retry merges. The original task row stays in its terminal state; only the unblock-check semantics change.
- Changing the dispatcher's queue-ordering logic (which already correctly dispatches the retry; the bug is only in the *downstream* unblock check after the retry merges).
- The reverse case: an original that ships while a retry is still in flight. (In practice the orchestrator stops dispatching retries once the original ships; this spec scopes to the retry-ships-original-stuck case.)

## Scope

One surface, narrow change:

**Orchestrator unblock check** (`coder-core` `coder_core/workers/orchestrator.py::_check_unblock_siblings`). Replace the direct `plan_order` lookup with a chain-aware aggregation: for each `plan_order = N` in the plan, compute `max_stage(T)` across `T_orig` and every task whose `original_task_id` chain points back to `T_orig`. Use the maximum-stage value (ordered by the orchestrator's stage progression: `queued < executing < testing < reviewing < accepted`, with `stuck`/`timed_out` collapsing to `executing` for ordering purposes — they're "in flight but failed", not terminal).

The chain walk has bounded depth in practice (operator memory shows retry chains rarely exceed 2-3 deep), but the implementation should not assume a depth limit. SQL approach: a single `WITH RECURSIVE` CTE walks the chain, keyed on `plan_id`. Avoids N+1 queries in the unblock check.

## Acceptance criteria

- **AC1.** A task at `plan_order=N` with `stage=stuck` and a retry whose `original_task_id` points back to it merges and lands `stage=accepted`. The next dispatcher tick observes `plan_order=N+1` as unblocked and dispatches it without any operator override.
- **AC2.** A two-deep retry chain (`T_orig → T_retry_1 → T_retry_2`) where `T_retry_2` is the one that lands `accepted` — `plan_order=N+1` is unblocked identically. The chain walks past intermediate failed retries.
- **AC3.** Operator's `POST /v1/projects/{id}/tasks/{task_id}/override` with `{"skip_to_stage": "accepted"}` continues to work on **any** task in the chain (original, retry, retry-of-retry). The override applies at the task it was issued on; the unblock check sees it via the chain walk.
- **AC4.** A task at `plan_order=N` with no retries and `stage=accepted` continues to unblock `plan_order=N+1` exactly as today. Regression guard for the single-task case.
- **AC5.** End-to-end test: dispatch a 3-task plan (ords 0/1/2). Ord 0 fails; a retry is spawned; the retry merges and accepts. Ord 1 dispatches automatically (no operator override). Ord 1 succeeds. Ord 2 dispatches automatically. No `skip_to_stage=accepted` override is required on any task.

## Open questions

- The stage ordering for `stuck` / `timed_out` — collapsing both to "executing for ordering purposes" matches the operator's mental model (work-not-done) but should be cross-checked against the existing stage state machine. If `stuck` is currently treated as terminal-but-failed elsewhere in the orchestrator, the unblock check might need a different ordering function than the rest of the system. Probably fine, but worth surfacing in design.
- Should the unblock check log a structured `orchestrator.unblock_via_retry_chain` event when the unblocking task is in a retry chain (not the original)? Helps the operator audit which retry actually shipped the work. Cheap to add; recommend yes.
- The `WITH RECURSIVE` SQL approach assumes `original_task_id` is indexed. Check the index list; add if missing as part of this spec's migration (zero-downtime — additive index).

## Links

- Related operator memory: orchestrator-side gap #3 in the Phase A tracking note. Documents the recovery muscle memory and the per-spec recurrence across 0075/0079/0080.
- Related spec: `task-orchestration` (active) — `_check_unblock_siblings` lives in that component's surface. This spec extends its semantics, doesn't replace them.
- Related spec: `self-healing` (active) — the self-heal patterns currently don't catch this case because the affected task is `stuck` on a single state machine, not zombie-executing. This spec closes a distinct gap.

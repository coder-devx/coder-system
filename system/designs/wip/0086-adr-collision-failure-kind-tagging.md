---
id: 0086
title: ADR Collision failure_kind Tagging
type: design
status: wip
owner: ro
created: '2026-05-12'
updated: '2026-05-12'
last_verified_at: '2026-05-12'
implements_specs:
- 0086
decided_by: []
related_designs:
- architect-worker
- worker-communication
- audit-log
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-admin
parent: pipeline-operations
---

# ADR Collision failure_kind Tagging

## Context

The orchestrator's per-ADR commit loop in `dispatcher.py::_handle_architect_result` already sets `failure_kind="adr_collision"` when an ADR collides with the registry, but uses a **last-wins** strategy: each iteration overwrites the task row independently and `failure_detail` carries only the final colliding ADR's ID. On a multi-ADR batch collision (live incident 2026-05-10: specs 0077/0079/0080 raced on the same ADR IDs, three of four ADRs silently dropped), the operator sees one chip but must manually diff `task.result` against the registry to discover how many ADRs actually dropped.

Two companion gaps: `failure_detail` doesn't list which ADRs committed successfully, and `FailureKindChip.tsx` has no label entry for `adr_collision`, so the chip renders a raw string rather than the human-readable "ADR collision" label.

## Goals / non-goals

**Goals:** Accumulate all colliding and committed ADR IDs across the batch loop; write `failure_kind` and `failure_detail` once post-loop with `collided_adr_ids` + `committed_adr_ids`. Add `"adr_collision"` label to `FailureKindChip`.

**Non-goals:** Auto-renumbering colliding ADRs; retrying commits; closing the underlying allocation race (spec 0085).

## Design

```mermaid
sequenceDiagram
    participant loop as ADR commit loop<br/>(dispatcher.py)
    participant acc as local accumulators
    participant db as tasks table
    participant chip as FailureKindChip.tsx

    loop for each ADR in batch
        loop->>loop: _commit_artifact_with_registry(adr_id)
        alt collision
            loop->>acc: collided_adr_ids.append(adr_id)
        else success
            loop->>acc: committed_adr_ids.append(adr_id)
        end
        loop->>db: TaskLogRow (per-ADR, unchanged)
    end
    alt collided_adr_ids non-empty
        loop->>db: failure_kind="adr_collision"<br/>failure_detail={collided_adr_ids, committed_adr_ids}
    end
    db-->>chip: "ADR collision" chip
```

### Orchestrator change — `coder-core/src/coder_core/workers/dispatcher.py`

In `_handle_architect_result`, replace the per-iteration `failure_kind` write for collisions with an accumulator pattern:

1. Before the ADR `for` loop, initialise `collided_adr_ids: list[str] = []` and `committed_adr_ids: list[str] = []`.
2. Per iteration: on `adr_result == "collision"` append to `collided_adr_ids`; on `None` (success) append to `committed_adr_ids`. Per-ADR `TaskLogRow` write is unchanged.
3. After the loop, if `collided_adr_ids` is non-empty, open one `async with sm()` session and write `task_row.failure_kind = "adr_collision"` and `task_row.failure_detail = json.dumps({"kind": "adr_collision", "collided_adr_ids": collided_adr_ids, "committed_adr_ids": committed_adr_ids, "design_id": design_id})`.
4. `broken_cross_link` iterations keep their existing per-iteration write unchanged — distinct failure kind, unchanged recovery path.

No schema migration needed — `failure_kind` and `failure_detail` exist since migration 0020.

### Admin UI change — `coder-admin/src/components/FailureKindChip.tsx`

Add to the chip's label/color map alongside `spec_collision` and `design_collision`:

```ts
adr_collision: { label: "ADR collision", color: "orange" },
```

`TaskDetail.tsx` already renders `failure_detail` as arbitrary JSON; no further changes needed there.

### Edge cases

- **All ADRs collide.** `committed_adr_ids: []`. Design committed normally; operator recovers missing ADR bodies from `task.result`.
- **Mix of collision and `broken_cross_link`.** Per-iteration `broken_cross_link` writes run; the post-loop write then overwrites `failure_kind` with `adr_collision` if any collision occurred. Both kinds remain visible in the task log.
- **Post-loop `sm()` write fails.** Swallowed by the existing `except Exception: pass` guard. Per-ADR log entries already persisted; chip won't render but log is readable.
- **No collisions.** Accumulators empty; no post-loop write; `failure_kind` stays `null`. Regression guard for AC4.

## Rollout

1. Land `coder-core` accumulator change; integration tests (AC1/AC3/AC4) gate the deploy. No flag needed — only the failure-path payload shape changes; clean path is untouched.
2. Smoke-test in staging: dispatch an architect task against a pre-collided ADR registry entry; confirm chip renders "ADR collision" with full `collided_adr_ids` list.
3. Land `coder-admin` chip label update; soak one architect-heavy pipeline cycle to confirm clean-path tasks show no chip.

## Links

- Spec [0086](../../product-specs/wip/0086-architect-adr-collision-failure-kind.md)
- Design [architect-worker](./architect-worker.md) — Phase 4 commit path this modifies
- Design [worker-communication](./worker-communication.md) — `failure_kind` / `failure_detail` column schema (migration 0020)
- PR coder-core#202 — `spec_collision` pattern reference
- PR coder-core#166 — `design_collision` pattern reference
- Spec [0085](../../product-specs/wip/0085-adr-id-allocation-race-under-concurrent-dispatch.md) — upstream allocation race

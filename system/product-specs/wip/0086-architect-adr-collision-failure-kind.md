---
id: '0086'
title: failure_kind tagging for architect ADR collisions inside the same batch
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
- architect-worker
- task-orchestration
parent: pipeline-operations
---

# failure_kind tagging for architect ADR collisions inside the same batch

**Phase:** wip
**Progress:** 0 / 4 acceptance criteria

## Problem

When the architect emits multiple ADRs in a single response and one of them collides with an existing registry entry (because another concurrent architect already shipped at that ID — see spec 0085 for the underlying allocation race), the per-ADR `commit_artifact` returns `collision`. The orchestrator's per-ADR loop logs the collision and continues to the next ADR — **no `failure_kind` tag is written to the task row**. Operator gets no visible signal that artifacts silently dropped from the batch.

PR [coder-core#202](https://github.com/coder-devx/coder-core/pull/202) added `failure_kind=spec_collision` for the PM-draft path so the operator sees a clear chip on the Pipeline list when a draft drops on collision. PR [coder-core#166](https://github.com/coder-devx/coder-core/pull/166) did the same for designs. The architect ADR path was missed — memory's gap #2 documents this. Saw the live consequence on 2026-05-10: architect for spec 0075 emitted four ADRs in the same response (0032/0033/0034/0035); only 0032 committed via the orchestrator due to per-ADR collisions, and 0033/0034/0035 had to be hand-recovered from the preserved task output. **No failure_kind chip surfaced** — the operator only noticed because they happened to inspect the registry.

Spec 0085 closes the underlying race. This spec closes the **visibility** gap: even after 0085, edge cases (operator-side ID overrides, racing operator-initiated dispatches, registry-edit-during-architect-run) can still produce collisions. The operator needs to see them, not have them silently dropped.

## Users / personas

- **Operators watching the pipeline.** Today they don't get a signal when an architect batch partially fails on ADR collisions. They have to manually compare the task's preserved output against the registry to notice the drop.
- **The reviewer worker.** Doesn't see the collision in its review surface; can't flag it for the operator.
- **The audit timeline.** Currently shows the architect's task as succeeded even when its work was partially dropped at commit time.

## Goals

- An architect task whose per-ADR commit loop encounters one or more `collision` returns is tagged with `failure_kind=adr_collision` on the task row.
- The `failure_kind` chip surfaces on the Pipeline list and on the task-detail page, with a breakdown of which ADRs collided (IDs + titles).
- The architect's other emitted artifacts (the design, non-colliding ADRs) still commit normally — partial success is preserved, not undone.
- The audit event recorded for the task includes the collision-id list for downstream tooling and operator audit.

## Non-goals

- Auto-renumbering colliding ADRs. The architect's choice of IDs is the contract; renumbering would change the cross-link semantics. Operator decides whether to re-dispatch with a new ID range or accept the partial commit.
- Retrying the colliding ADR commits. The task is terminal; retry surface is operator-initiated via the existing `action: retry` override.
- Closing the underlying allocation race. That's [spec 0085](https://github.com/coder-devx/coder-system/pull/120)'s job.

## Scope

Two surfaces:

1. **Orchestrator architect-commit path** (`coder-core` `coder_core/workers/orchestrator.py::_commit_artifact_with_registry` or its caller). When iterating ADRs in a batch and any one returns `collision`, accumulate the collisions in a list. After the batch loop completes, if the list is non-empty, set `task.failure_kind = "adr_collision"` and `task.failure_detail = {"collided_adr_ids": [...], "committed_adr_ids": [...]}`. Mirrors the pattern PR #202 used for `spec_collision`.

2. **Admin UI surfacing** (`coder-admin`). The existing `failure_kind` chip on the Pipeline list already handles new codes through the same enum — add `adr_collision` to the chip's label map (`"ADR collision"`) and color (matches existing `spec_collision` styling). The task-detail page surfaces `failure_detail` already; verify the structured payload renders cleanly.

No changes to the architect worker prompt. No changes to the registry format. No changes to operator-side dispatch surfaces.

## Acceptance criteria

- **AC1.** An architect task whose batch includes one ADR that collides with an existing registry entry (other ADRs commit normally) — the task row has `failure_kind=adr_collision`, `failure_detail` populated with `collided_adr_ids` and `committed_adr_ids`. The audit event for the task records the same payload.
- **AC2.** The Pipeline list shows an "ADR collision" chip on that task's row, styled consistently with the existing `spec_collision` chip. Clicking the row opens task-detail; the `failure_detail` block renders the collision list.
- **AC3.** Multiple ADRs in the same batch collide — all are recorded in `collided_adr_ids`. The non-colliding ADRs and the design commit normally (partial success preserved). Operator can choose to manually patch the registry to add the dropped ADRs (today's recovery path) or re-dispatch via the operator override.
- **AC4.** An architect task with no collisions — `failure_kind` stays `null`, no chip. Regression guard for the clean path.

## Open questions

- The label "ADR collision" on the chip — does that read well alongside `spec_collision` and the others? Operator-side preference; could be "ADR drop" or "ADR clash". Defer to the operator on copy.
- Should `failure_detail` also include the **content** that was dropped (the preserved ADR bodies from the architect's response)? Useful for hand-recovery, but might bloat the row. Alternative: link to the task's preserved-output GCS URI which already contains it. Lean toward link, not body.
- Same gap exists for design-collision in architect batches (PR #166 covered the PM-draft design path but not the architect's batch-design collision specifically). Should this spec also cover that, or scope tightly to ADR? Lean tight — design collision pattern is rarer in practice and a separate spec can land it.

## Links

- PR [coder-core#202](https://github.com/coder-devx/coder-core/pull/202): the prior failure_kind tagging pattern for `spec_collision`. This spec mirrors it for `adr_collision`.
- PR [coder-core#166](https://github.com/coder-devx/coder-core/pull/166): the same pattern for design collisions in the PM-draft path.
- Related operator memory: orchestrator-side gap #2 in the Phase A tracking note. Documents the 0075-architect-batch live incident (4 ADRs emitted, 3 silently dropped).
- Related spec: [0085](https://github.com/coder-devx/coder-system/pull/120) — closes the underlying allocation race. This spec covers the visibility gap regardless of whether 0085 lands first.
- Related spec: `architect-worker` (active) — extends its commit-path semantics.

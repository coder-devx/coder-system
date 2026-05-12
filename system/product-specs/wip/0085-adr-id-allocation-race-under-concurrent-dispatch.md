---
id: '0085'
title: ADR ID allocation race under concurrent architect dispatch
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

# ADR ID allocation race under concurrent architect dispatch

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

When two architect tasks are dispatched concurrently, each independently allocates `Next free ADR ID` at task admission time by reading the current max from the ADR registry on `main`. Both see the same max → both assign the same next-free ID. When the architects later commit ADRs, the second-merging batch collides on the ID that the first one already shipped.

Memory's Phase A tracking note documents this as orchestrator-side gap #1, in the same family as the dispatcher-allocation race documented in `feedback_dispatcher_id_race.md` (which covered PM specs). PR [coder-core#204](https://github.com/coder-devx/coder-core/pull/204) fixed the YAML-parse symptom that was masking the collision but did not address the underlying allocation race. Designs and ADRs share the issue. Under Phase B's autopilot, every fan-out moment where two specs reach architect concurrently risks a silent ADR drop.

The current behaviour:

1. Architect task `T_A` is admitted. Dispatcher reads ADR registry on `main` — max ID is `0036`. `T_A`'s run-context block contains `Next free ADR IDs: [0037, 0038, ...]`.
2. Architect task `T_B` is admitted ~seconds later. Dispatcher reads ADR registry on `main` — max ID is still `0036`. `T_B`'s run-context block contains `Next free ADR IDs: [0037, 0038, ...]`.
3. Both architects start work in parallel. Both produce ADRs at IDs `0037` and `0038`.
4. `T_A` ships first. Registry now has `0037` and `0038`.
5. `T_B` tries to commit. The per-ADR `commit_artifact` checks see the IDs already exist → return `collision`. The architect's batch fails partially (see related gap [#2 — ADR-collision silent-drop](https://github.com/coder-devx/coder-system/pull/_FILL_IN_)).

The race exists because ID allocation is **read-only at dispatch**, not **claim-on-dispatch**. The dispatcher reads the current state; it doesn't reserve.

## Users / personas

- **Operators dispatching multiple specs to architect in parallel.** Today they must manually serialize architect dispatches across specs in the same batch — memory documents the workaround as "serialize PM/architect dispatches; concurrent allocation collides and silent-drops the loser." Under Phase B's higher fan-out, the workaround stops scaling.
- **The architect worker.** Currently produces work that may not commit; wastes a worker slot.

## Goals

- ADR ID allocation at architect-task admission is atomic across concurrent dispatches. Two architects admitted within the same second receive **non-overlapping** ID ranges, even though the registry state on `main` hasn't moved between the two admissions.
- The allocation is durable — recorded in the orchestrator's DB at dispatch time so a re-read on subsequent admissions reflects the claimed range.
- The reservation is **released** if the architect task fails or is cancelled without committing any ADRs; otherwise the next dispatch sees a gap where the cancelled task's IDs would have been.

## Non-goals

- Refactoring the broader ADR registry storage model. The fix is in the dispatcher's allocation path, not in the registry's structure.
- Cross-project ID reservation. Each project has its own ADR registry; this spec scopes to within-project concurrent dispatch.
- Removing the existing read-from-`main`-at-architect-runtime check. That check stays as the cross-link validator; this spec just feeds it a non-colliding range.
- Reservation under operator-side ID overrides. If the operator dispatches with `Next free ADR ID = 0099` explicitly, that override path is unchanged.

## Scope

Two surfaces:

1. **Dispatcher admission path** (`coder-core` `coder_core/workers/dispatcher.py` — the architect-task run-context-block construction). Replace the read-only `max(registry) + 1` allocation with a **claim-on-dispatch** model: at admission, atomically insert an `adr_id_reservation` row in the orchestrator DB recording `(project_id, range_start, range_end, claimed_by_task_id, claimed_at)`. The next-free read becomes `max(max(registry), max(active_reservations.range_end)) + 1`. Concurrent admissions serialize on the unique constraint over the reservation table.

2. **Reservation release** (`coder-core`, same module). When a task transitions to a terminal state (`accepted` / `stuck` with no committed ADRs / `cancelled`), check whether its `claimed_by_task_id` has any registry rows in the claimed range. If none, delete the reservation row to release the IDs. If at least one ID committed, leave the reservation in place (history sentinel) so future allocations don't reuse a partial-commit range.

The implementation uses a single new table `adr_id_reservations` and a single new dispatcher tick step. No changes to the architect's prompt or the registry format. Operator-visible only via a new "ADR reservation" line in the task's run-context info block.

## Acceptance criteria

- **AC1.** Two architect tasks `T_A` and `T_B` admitted concurrently for the same project. Each reservation row is created atomically; the rows do not overlap. `T_A`'s run-context shows `Next free ADR IDs: [0037, 0038]` and `T_B`'s shows `Next free ADR IDs: [0039, 0040]` (or whatever non-overlapping range follows).
- **AC2.** `T_A` ships its ADRs at `0037` and `0038`. `T_B` ships its ADRs at `0039` and `0040`. Registry contains all four. No collision, no silent drop.
- **AC3.** `T_C` is admitted, allocated `[0041]`, then the task fails before committing any ADR. On terminal-state observation the reservation is released. The next admission `T_D` allocates from `0041` again (no gap in the registry).
- **AC4.** `T_E` is admitted, allocated `[0042, 0043]`, ships `0042` but not `0043` (architect emitted only one ADR). On terminal-state observation the reservation is **not** released (partial commit), and the next admission `T_F` allocates from `0044`. The gap at `0043` is intentional history.
- **AC5.** Concurrent integration test: dispatch 20 architect tasks against the same project in a 100ms window. Verify the registry post-completion has 20 contiguous non-overlapping ADR ranges and no `collision` failure_kinds.

## Open questions

- Should the reservation include the **estimated** ADR count (architect run-context says "emit up to N ADRs") and reserve that much? Or reserve a generous slab (e.g., 10 IDs) and release the tail on commit? The trade-off is gap-in-registry size vs. reservation contention. Generous slabs are simpler; tight reservations leave fewer gaps. Lean toward generous (10) for v1; tune if the gap rate becomes load-bearing.
- The reservation release on cancellation requires the orchestrator to observe the terminal-state transition. Today's task-state machine does fire those transitions; verify nothing prevents the release step from running.
- For the cross-project case (out of scope per the non-goals): if two projects share a registry repo (currently `coder-system`), they share an ID space. The reservation table needs to key on `(project_id, registry_repo)` — or just `(registry_repo)`. Worth confirming in design.

## Links

- `feedback_dispatcher_id_race.md` (operator memory) — covered the PM-spec ID race; design notes apply to the ADR variant.
- ADR 0028: allocation guard — dispatcher must supply the id, worker must refuse if missing. This spec extends 0028's allocation semantics with a reservation table.
- Related spec: `0086-architect-adr-collision-failure-kind.md` (this batch) — pairs with this spec; tag collisions properly until the allocation race is closed.
- Related spec: `architect-worker` (active) — extends its admission path. Needs an ADR if the reservation model grows beyond architect tasks (e.g., PM-draft ID reservation, design-ID reservation).

---
id: '0076'
title: Spec-bound architect dispatch from admin UI
type: spec
status: active
owner: ro
created: '2026-05-10'
updated: '2026-05-10'
last_verified_at: '2026-05-10'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- admin-panel
- task-orchestration
parent: pipeline-operations
---

# Spec-bound architect dispatch from admin UI

**Phase:** wip
**Progress:** 0 / 7 acceptance criteria

## Problem

An operator who has landed a fresh WIP spec via PM draft cannot dispatch the matching architect-design task from the admin Pipeline → Create Task UI in a way that produces a correctly bound design. Two bugs compound:

1. **`spec_id` not wirable from the UI.** `TaskCreate` has no `spec_id` field — only `role`, `prompt`, `repo`. The dispatcher gets `task_spec_id=None` and emits `Next free design ID` instead of `Design ID = {spec_id}`. The architect produces a design at the wrong numeric ID with `implements_specs: []`. Per ADR 0026 the design must share the spec's ID; an empty `implements_specs` orphans the design in the audit pipeline.

2. **Co-emitted ADRs fail the cross-link checker.** The orchestrator's write-phase checker reads ADR registry from `main`. When the architect introduces new ADRs alongside the design (the common case for new surfaces), those ADRs are not yet registered. Every artifact in the batch fails with `failure_kind=broken_cross_link`. ~27k tokens of architect output are preserved on the task page but zero artifacts land in the knowledge repo.

Spec 0075 (Coder Studio) hit both legs on its first architect dispatch (task `55316aa7`). The spec_run coordinator cannot break the deadlock — it bootstraps only when PM accept reports `all_pass`, which requires a shipped implementation, which requires a valid design.

## Users / personas

Operators using the admin Pipeline → Create Task UI to manually advance a freshly drafted WIP spec into the architect design stage.

## Goals

- Operator can bind an architect task to a WIP spec at creation time via an autocomplete in the Create Task form.
- When bound, the dispatcher emits `Design ID = {spec_id}` and the architect produces `implements_specs: [spec_id]` with design id matching spec id.
- Co-emitted ADRs from the same architect response no longer fail cross-link validation; intra-batch artifacts are treated as known-existing for that batch's cross-link check.
- Pipeline list and task-detail surfaces give operators visibility into the spec binding.

## Non-goals

- Auto-dispatching architect on PM draft success (operator-initiated dispatch remains the authority surface).
- Changing when the spec_run coordinator bootstraps (still PM accept `all_pass`).
- Relaxing cross-links to non-existent IDs beyond same-response co-emitted artifacts.
- Sourcing the spec autocomplete from anything other than the project's WIP spec registry.

## Scope

Three surfaces:

1. **`TaskCreate` API** (`coder-core`): add optional `spec_id` field. The dispatcher already emits `Design ID = task_spec_id` when `task.spec_id` is set (`dispatcher.py:298`); the field just needs to be wirable from outside the coordinator path. `create_task_in_project` passes it through to the `TaskRow` constructor.
2. **Admin Create Task form** (`coder-admin`): "Bind to spec" autocomplete (role=architect only), sourced from the project's WIP spec registry; hint line under Prompt showing `"Architect will use Design ID = {spec_id} and set implements_specs = [{spec_id}]"`.
3. **Orchestrator cross-link checker** (`coder-core` `dispatcher.py` ~line 1290): build a `batch_known` set from all artifact IDs emitted in the current architect response; union it with the registry-derived set before checking each artifact's outbound cross-links.

Visual affordances on existing pages: `→ spec NNNN` chip on Pipeline list architect rows, spec id in task-detail run-context block.

## Acceptance criteria

- **AC1.** The Create Task form (role=architect) shows a "Bind to spec" autocomplete listing the project's WIP specs by id + title. Selecting one displays the hint `"Architect will use Design ID = 0075 and set implements_specs = [0075]"` below the Prompt field. Leaving the field blank behaves as today.
- **AC2.** `POST /v1/projects/{id}/tasks` accepts `spec_id` in the request body. The created task row has `spec_id` set. The dispatcher run-context block emits `Design ID: 0075` (not `Next free design ID`) for a task with `spec_id = "0075"`.
- **AC3.** The Pipeline list shows a `→ spec 0075` chip on architect task rows where `spec_id` is set. Clicking the chip opens the spec's WIP file in the knowledge browser.
- **AC4.** The task-detail page for a bound architect task displays `spec: 0075` in the run-context info block alongside role and repo.
- **AC5.** An architect task that emits new ADRs alongside the design no longer receives `failure_kind=broken_cross_link` for those ADRs' self-references within the same response. All co-emitted artifacts land in the knowledge repo in one orchestrator phase.
- **AC6.** Re-dispatching architect for spec 0075 via the admin UI bound to spec 0075 produces a design at id `0075` with `implements_specs: ["0075"]` and associated ADRs, all written to the knowledge repo without operator hand-patching.
- **AC7.** Dispatching architect from the Create Task form without selecting a spec produces a valid standalone design at the next-free design ID (current behaviour preserved; regression guard).

## Open questions

- Should "Bind to spec" pre-populate when the operator navigates to Create Task from a spec detail page?
- The `→ spec NNNN` chip link — in-panel knowledge browser or direct GitHub URL for the WIP file? Depends on whether the knowledge browser supports WIP paths at implementation time.

## Links

- ADR 0026: shared numeric ID pool for WIP specs and designs
- ADR 0028: allocation guard — dispatcher must supply the id, worker must refuse if missing
- Incident: task `55316aa7` (spec 0075 first architect dispatch, both failure modes)
- `coder-core` `dispatcher.py:298` — `Design ID` emit path when `task_spec_id` is set
- `coder-core` `dispatcher.py:1290–1301` — cross-link checker rejection sentinel

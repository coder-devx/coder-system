---
id: '0076'
title: Spec-bound Architect Dispatch
type: design
status: wip
owner: ro
created: '2026-05-15'
updated: '2026-05-15'
last_verified_at: '2026-05-15'
implements_specs:
- admin-panel
- spec-lifecycle-coordinator
- task-orchestration
decided_by:
- '0040'
related_designs:
- admin-panel
- worker-communication
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-admin
parent: pipeline-operations
---

# Spec-bound Architect Dispatch

## Context

Two failure modes blocked operator-initiated architect dispatches from the admin UI. First, `TaskCreate` exposed no `spec_id` field, so the dispatcher always emitted `Next free design ID` — the resulting design got the wrong numeric id with `implements_specs: []`, violating ADR 0026 and orphaning it in the audit pipeline. Second, when the architect co-emitted ADRs alongside the design, `commit_artifact` checked cross-links only against the live registry — the design's `decided_by` references to ADRs being written in the same batch always failed `broken_cross_link`, dropping all artifacts from the response. Both modes hit simultaneously on spec 0075 (task `55316aa7`).

## Goals / non-goals

**Goals:** wire `spec_id` from the Create Task form through the API to the dispatcher so the architect receives the correct Design ID; fix intra-batch cross-link false-positives so co-emitted ADRs land alongside their design in one pass.

**Non-goals:** auto-dispatch on PM accept; changing spec_run coordinator bootstrap; relaxing cross-links to non-existent IDs beyond same-response co-emitted artifacts.

## Design

```mermaid
sequenceDiagram
    participant Op as Operator
    participant Form as CreateTaskForm
    participant API as POST /tasks
    participant Disp as dispatcher.py
    participant P4 as Phase 4 writer

    Op->>Form: select spec 0075, submit
    Form->>API: {role:"architect", spec_id:"0075"}
    API->>Disp: task row spec_id="0075"
    Disp->>P4: run-context block has "Design ID: 0075"
    P4->>P4: collect batch_known from all artifact IDs in response
    P4->>P4: commit_artifact(design 0075, batch_known)
    P4->>P4: commit_artifact(ADR 0040, batch_known)
    P4-->>Op: all artifacts land; no hand-patching
```

### Components

**`domain/task.py` (`coder-core`):** `TaskCreate.spec_id: str | None` with `^[0-9]{4}$` validation. `TaskRow.spec_id` column (existing — no new migration). `TaskRead` and `TaskCreated` expose it in responses.

**`workers/dispatcher.py:360` (`coder-core`):** `build_run_context_block` emits `Design ID: {task_spec_id}` when `role == "architect"` and `task_spec_id is not None`; `orchestrate_task` passes `task_spec_id=row.spec_id` at line 739.

**`workers/dispatcher.py:1201` (`coder-core`) — `commit_artifact`:** `batch_known: dict[str, set[str]] | None` parameter. The Phase 4 architect writer builds this dict from all artifact IDs in the worker response before iterating; each `commit_artifact` call unions `batch_known` into the registry-derived `target_known` set before evaluating cross-link refs.

**`CreateTaskForm.tsx` (`coder-admin`):** architect-only `<select>` sourced from `listKnowledgeRegistry(projectId, "specs")` filtered to `folder=wip`. Selecting a spec adds `spec_id` to the POST body; a hint line below the Prompt reads `"Architect will use Design ID = {specId} and set implements_specs = [{specId}]."`  Switching off architect role clears the binding.

**`Pipeline.tsx` (`coder-admin`):** architect task rows where `task.spec_id` is set render a `→ spec NNNN` chip; chip links to `/projects/{id}/specs/{spec_id}` in the in-app Registry browser.

**`TaskDetail.tsx` (`coder-admin`):** run-context info block shows `spec: NNNN` alongside role and repo when `task.spec_id` is set.

### Data flow

1. Operator selects spec `0075` in Create Task (role=architect) → `POST /v1/projects/{id}/tasks` stores `spec_id="0075"` on the task row.
2. Dispatcher emits `Design ID: 0075` in the run-context block; architect produces design at id `0075` with `implements_specs: ["0075"]` and co-emits ADR `0040`.
3. Phase 4 collects `batch_known = {"adrs": {"0040"}, "designs": {"0075"}}` before iterating the artifact list.
4. `commit_artifact(design 0075, batch_known)`: cross-link check on `decided_by: ["0040"]` unions `batch_known["adrs"]` → resolves; design lands.
5. `commit_artifact(ADR 0040, batch_known)`: no outbound cross-links to unknown targets; ADR lands.
6. All artifacts in the knowledge repo; pipeline advances without operator hand-patching.

### Edge cases

- **Unbound dispatch:** `spec_id=None` → dispatcher emits `Next free design ID`; existing standalone-design path unchanged (AC7 regression guard).
- **Batch with no ADRs:** `batch_known` for the design type only; `commit_artifact` union is a no-op for the empty ADR set — no change to single-artifact validation.
- **WIP spec list load failure:** `listKnowledgeRegistry` error is swallowed in `CreateTaskForm`; select renders empty, operator dispatches unbound — non-fatal.
- **Collision on re-dispatch:** `commit_artifact` returns `"collision"` → `failure_kind="design_collision"` on the task, surfaced distinctly from `broken_cross_link` in the admin panel's `FailureKindChip`.
- **Chip link before WIP Registry route ships:** `→ spec NNNN` chip navigates to `/projects/{id}/specs/{spec_id}` via the in-app router; if Registry hasn't mounted a WIP detail route yet, the operator lands on a 404 page — not a broken external URL and recoverable without a deploy.

## Rollout

1. `tasks.spec_id` column exists — no migration needed.
2. Redeploy `coder-core`. `batch_known` path is gated on non-empty co-emitted artifact sets; existing single-artifact responses pass `None` and are unaffected.
3. Redeploy `coder-admin` with `CreateTaskForm` + chip changes. Verify AC1: architect task bound to spec `0075` shows hint text and `spec_id` on the task row.
4. Re-dispatch architect for spec `0075` bound to `0075`; confirm design and ADRs land in the knowledge repo without hand-patching (AC6).
5. Dispatch an unbound architect task; confirm standalone design lands at next-free ID (AC7).

## Links

- ADR 0026 — shared numeric ID pool for WIP specs and designs
- ADR 0028 — allocation guard (dispatcher supplies id, worker refuses if missing)
- ADR 0040 — co-emitted artifact IDs unioned into cross-link validation (this design)
- Incident: task `55316aa7` — spec 0075 architect dispatch, both failure modes
- Related: [admin-panel](./admin-panel.md), [worker-communication](./worker-communication.md)

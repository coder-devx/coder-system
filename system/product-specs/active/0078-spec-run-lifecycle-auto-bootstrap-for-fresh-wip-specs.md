---
id: 0078
title: Spec-run lifecycle auto-bootstrap for fresh WIP specs
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
- '0076'
- task-orchestration
parent: pipeline-operations
---

# Spec-run lifecycle auto-bootstrap for fresh WIP specs

**Phase:** wip
**Progress:** 0 / 7 acceptance criteria

## Problem

The spec_run coordinator drives the architect → TM → developer → reviewer chain once a `spec_runs` row exists in `accepted` state. The only path that creates that row today is `dispatcher.py:1645`: PM `accept` all_pass → `start_run`. PM acceptance requires shipped implementation to grade against; implementation requires a running spec_run. Chicken-and-egg: the chain that builds the implementation can't start until the implementation exists.

Today's workaround — operators hand-dispatch developer tasks one at a time from the Pipeline UI with hand-written prompts — doesn't scale past a handful of specs.

## Users / personas

Operators using the admin panel to advance a freshly drafted WIP spec into the architect → TM → developer → reviewer pipeline without per-task manual dispatch.

## Goals

- Add a "Start lifecycle" button on the admin spec-detail page for WIP specs with no associated spec_run. One click bootstraps the row; the coordinator fires the architect task within one minute.
- Add `POST /v1/projects/{id}/spec-runs` as an explicit API bootstrap surface (201 on create, 200 on idempotent repeat).
- Wire `auto_start_lifecycle: true` (default, opt-out) into the SpecCompose file path so operator-filed specs arrive lifecycle-ready without a manual click.
- Wire the same auto-start into the orchestrator's Phase 4 PM-draft handler so PM-worker-emitted specs get their lifecycle started automatically after the spec file commits.

## Non-goals

- Changing the spec_run state machine (states, transitions, retry policy).
- Removing the PM accept all_pass → start_run path — it remains for the post-implementation audit cycle.
- Auto-starting spec_runs for WIP specs that existed before this spec ships; retroactive backfill is operator-initiated via the new button.
- Cross-project spec_runs.

## Scope

Four changes in the existing spec_run surfaces:

1. **`POST /v1/projects/{id}/spec-runs`** (`coder-core` `api/spec_runs.py`): new bootstrap endpoint. Body: `{wip_spec_id: "NNNN"}`. Calls `service.start_run`; returns 201 + new row on create, 200 + existing row on idempotent repeat.
2. **Admin spec-detail page** (`coder-admin`): show "Start lifecycle" button when `GET /spec-runs/{wip_spec_id}` returns 404. On click: POST to the bootstrap endpoint, then replace the button with a link to the spec_run detail page.
3. **SpecCompose file path** (`coder-core` `api/specs.py` `_file_path`): accept optional `auto_start_lifecycle: bool = True` in `SpecComposeBody`. After `execute_filing` opens the PR, call `service.start_run` when the flag is true.
4. **PM-draft Phase 4** (`coder-core` `workers/dispatcher.py`): after the spec file and registry entry are committed, call `service.start_run` for the new spec's `wip_spec_id`. Use the same swallow-on-exception pattern as `dispatcher.py:1645` so Phase 4 is not gated on lifecycle bootstrap success.

## Acceptance criteria

- **AC1.** A wip spec page with no associated spec_run shows a "Start lifecycle" button. Clicking it creates a spec_run in `accepted` state and the coordinator dispatches the architect task (with `spec_id` set per spec 0076) within one minute. The button is replaced by a link to the spec_run detail page.
- **AC2.** `POST /v1/projects/{id}/spec-runs` with body `{wip_spec_id: "0075"}` returns 201 and the new spec_run row's id. A second identical call returns 200 with the existing row's id.
- **AC3.** The coordinator's first dispatched task — architect — has `spec_id={wip_spec_id}` set on the `TaskRow`, so the design lands at the matching numeric id (per spec 0076 and ADR 0026).
- **AC4.** A spec filed via SpecCompose with `auto_start_lifecycle: true` (the default) gets a spec_run started after the PR opens. The spec-detail page shows the lifecycle progress bar on first load; no manual button click required.
- **AC5.** A spec drafted by the PM worker and committed via Phase 4 gets a spec_run started automatically. The lifecycle progresses — architect task appears in the pipeline — without operator intervention.
- **AC6.** The existing PM-accept all_pass → start_run path still works unchanged (regression guard).
- **AC7.** Pause and resume on spec_runs bootstrapped via the new entry points use the existing `POST /v1/projects/{id}/spec-runs/{wip_spec_id}/pause` and `.../resume` endpoints without modification.

## Open questions

- Should Founder-emitted PM draft tasks for B2C product ideas auto-start their lifecycle, or stay manual until an operator approves the idea? Per spec 0075's idea-queue surface, Founder approval already requires an operator click; auto-start triggered by that approval click is the natural shape. Confirm in design.

## Links

- Spec 0076: spec-bound architect dispatch from admin UI (prerequisite: architect `spec_id` binding for AC3)
- `coder-core` `spec_runs/service.py::start_run` — the idempotent bootstrap function this spec exposes
- `coder-core` `spec_runs/coordinator.py::dispatch_architect` — chain dispatcher (first consumer of the new spec_run rows)
- `coder-core` `workers/dispatcher.py:1645` — the only existing `start_run` call; the new paths add parallel entry points
- `coder-core` `api/spec_runs.py` — the existing pause/resume endpoints the new bootstrap endpoint joins

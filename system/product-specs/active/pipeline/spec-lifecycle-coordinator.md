---
id: spec-lifecycle-coordinator
title: Spec-lifecycle coordinator
type: spec
status: active
owner: ro
created: 2026-05-04
updated: 2026-05-17
last_verified_at: 2026-05-17
summary: Per-spec state machine that auto-dispatches the architect → TM → developer chain between human approval gates.
served_by_designs: ['0076', '0078']
related_specs: [task-orchestration, admin-panel, pm-worker, architect-worker, team-manager-worker, knowledge-api]
parent: pipeline-operations
---

# Spec-lifecycle coordinator

## What it is

A per-spec state machine that generalises the close-cycle backstop one
level up: instead of pipeline-runs tracking one task at a time, a
`spec_run` row tracks each WIP spec through its full lifecycle, and a
Cloud Run Job auto-dispatches the next role's task at each transition.
Human approval gates remain at PM-accept, plan-approve, and ship-merge
per ADR 0015; the coordinator only auto-dispatches at the spawn points
between them. This is what closes the gap between "PM drafted a WIP"
and "developer tasks running" without an operator hand-creating each
intermediate task.

## Capabilities

- **State machine.** Every WIP spec gets a `spec_runs` row that moves
  through `accepted → designing → design_landed → planning →
  plan_pending → implementing → ship_pending → shipped`, plus
  `deprecated` and `paused`. All transitions are written via
  `coder_core.spec_runs.service` (the only writer of
  `spec_runs.state`); audit actions `spec_run.transitioned`,
  `spec_run.paused`, and `spec_run.resumed` let operators reconstruct
  any spec's lifecycle from the audit log alone.

- **Coordinator tick.** `coder-core-spec-coord-tick` Cloud Run Job runs
  `coder_core.spec_runs.coordinator.tick` every 60 s, claims active
  runs with `FOR UPDATE SKIP LOCKED`, and probes the next transition:
  `accepted → designing` via `dispatch_architect` (with `spec_id`
  bound so the design lands at the matching numeric id per ADR 0026);
  `designing → planning` via `dispatch_team_manager` once the
  architect task succeeds. Both dispatchers are idempotent — an
  existing non-terminal task for the same spec reattaches with
  `trigger="manual_override"` rather than duplicating.

- **Four bootstrap entry points.** A row starts in `accepted` from any
  of these surfaces, each idempotent:
  - **Admin "Start lifecycle" button** on the spec-detail page →
    `POST /v1/projects/{id}/spec-runs` (201 on create, 200 on
    idempotent repeat).
  - **SpecCompose** `auto_start_lifecycle: true` (default) — after
    `execute_filing` opens the PR, `service.start_run` is called.
  - **PM-draft Phase 4** — after the spec file + registry entry
    commit, `service.start_run` runs under a swallow-on-exception
    guard so Phase 4 is never gated on bootstrap success.
  - **PM-accept `all_pass`** (historical) — preserved as the
    regression guard for the original post-acceptance path.

- **Operator controls.** `GET /v1/projects/{id}/spec-runs[?state=]`
  lists active runs with state filter; `GET .../spec-runs/{wip_spec_id}`
  returns detail with the full transition-history audit chain. Pause
  and resume via `POST .../{wip_spec_id}/{pause,resume}` — paused runs
  stop dispatching at the next tick. Admin spec-detail page
  (`/projects/:id/specs`, behind `VITE_SPEC_COORDINATOR_ENABLED`)
  exposes the fleet view with per-row pause/resume actions gated to
  admin scope.

## Interfaces

- `POST /v1/projects/{id}/spec-runs` — bootstrap entry point;
  body `{wip_spec_id: "NNNN"}`. 201 on create, 200 on idempotent
  repeat.
- `GET .../spec-runs[?state=]` — list; optional state filter.
- `GET .../spec-runs/{wip_spec_id}` — detail with transition history.
- `POST .../spec-runs/{wip_spec_id}/{pause,resume}` — operator override.
- Cloud Run Job: `coder-core-spec-coord-tick` (Cloud Scheduler, 60 s).
- DB: `spec_runs` (migration 0061, unique on
  `(project_id, wip_spec_id)`).
- Audit actions: `spec_run.transitioned`, `spec_run.paused`,
  `spec_run.resumed` — see [audit-log](../tenancy/audit-log.md).
- Admin: `/projects/:id/specs` (behind
  `VITE_SPEC_COORDINATOR_ENABLED`).

## Dependencies

- [task-orchestration](./task-orchestration.md) — owns the underlying
  task lifecycle the coordinator dispatches into; the coordinator
  uses `tasks.spec_id` binding and the existing dispatch path.
- [pm-worker](../workers/pm-worker.md) — Phase 4 auto-bootstrap path
  + PM-accept regression guard.
- [architect-worker](../workers/architect-worker.md),
  [team-manager-worker](../workers/team-manager-worker.md) — the
  workers the coordinator auto-dispatches into.
- [admin-panel](../knowledge/admin-panel.md) — the "Start lifecycle"
  button and the fleet spec-runs page.
- [knowledge-api](../knowledge/knowledge-api.md) — SpecCompose's
  `_file_path` is one of the bootstrap entry points.
- Postgres (`spec_runs` migration 0061) — state of record.

## Evolution

- 2026-05-04 — Initial ship (spec 0068): `spec_runs` table, service
  module, coordinator tick, two transitions (architect, TM),
  PM-accept Phase 4 bootstrap, admin Specs page.
- 2026-05 — Three additional bootstrap entry points (spec 0078):
  admin "Start lifecycle" button, SpecCompose auto-start,
  PM-draft Phase 4 — plus `spec_id` binding on architect dispatch
  (spec 0076) so the design lands at the matching numeric id.

## Links

- Designs: [spec-bound-architect-dispatch](../../../designs/wip/0076-spec-bound-architect-dispatch.md),
  [spec-run-lifecycle-auto-bootstrap](../../../designs/wip/0078-spec-run-lifecycle-auto-bootstrap.md)
- Related components: [task-orchestration](./task-orchestration.md),
  [admin-panel](../knowledge/admin-panel.md),
  [pm-worker](../workers/pm-worker.md),
  [architect-worker](../workers/architect-worker.md),
  [team-manager-worker](../workers/team-manager-worker.md),
  [knowledge-api](../knowledge/knowledge-api.md)
- ADR 0015 — ship gate lives in the Coder pipeline (constrains the
  coordinator's auto-dispatch scope).
- ADR 0026 — shared numeric id pool for WIP specs and designs (why
  `spec_id` binding matters for architect dispatch).

---
id: self-healing
title: Self-healing stuck pipelines
type: spec
status: active
owner: ro
created: 2026-04-23
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: Reaper for stuck tasks past timeout.
served_by_designs: [self-healing]
related_specs: [task-orchestration, observability, audit-log, escalations, admin-panel]
parent: pipeline-operations
---

# Self-healing stuck pipelines

## What it is

A 5-minute Cloud Run Job runs a small registry of `Remediator`s
against DB state. Each remediator owns a known-safe stuck-pipeline
pattern: detect a target that matches its shape, run the idempotent
recovery the operator would have run, and record the attempt. When
a remediation succeeds, the watchdog closes any open
[escalations](./escalations.md) pointing at the same target with
`resolved_by_id='self_healing'`, so the pager doesn't fire for
something the system already fixed. Safety is provably bounded:
each remediator's worst case is no change — never a wrong change.

## Capabilities

- **Remediator registry.** `coder_core.self_heal.registry`
  enumerates the active `Remediator` implementations. Each
  implements a `protocol.Remediator` interface with
  `detect(session, now) -> list[Target]` and
  `remediate(target) -> Outcome`. Adding a pattern is one file plus
  one line in the registry.
- **v1 pattern: `stuck_queued`.** A `tasks.status='queued'` row
  older than `stuck_queued_min_minutes` (default 15) whose project
  `DispatcherQueue` depth is 0 and `worker_concurrency` is not
  pinned is re-enqueued via the existing override path. Safe
  because re-enqueue is idempotent on task id — a spurious detect
  has no effect.
- **Per-pattern mode.** Each pattern runs in one of three modes
  configurable fleet-wide:
  - `off` — detect skipped entirely.
  - `dry_run` — detect runs, an attempt row is recorded, but
    remediate is not invoked. Used for soak-testing a new pattern.
  - `apply` — detect + remediate + audit.
- **Provably-safe remediations only.** Every pattern's remediation
  uses an existing operator-grade recovery path (retry / re-enqueue
  / replay-chain). A remediator that cannot guarantee no-worse-than-
  no-op does not ship.
- **Per-target-per-pattern daily cap.** `self_heal_attempts` table
  is the dedupe + rate-limit substrate. A second hit within the
  day for the same `(pattern_id, target_id)` lands
  `outcome='skipped_cap'` and escalation proceeds normally —
  preventing a remediator loop on a genuinely broken target.
- **Escalation peer-consumer.** After a successful remediation, the
  watcher enumerates open `escalations` matching the target and
  calls `POST /v1/projects/{id}/escalations/{id}/resolve` with
  `actor_type='system'`, `actor_id='self-healing-watchdog'`,
  `resolved_by_id='self_healing'`. Audit rows on both sides.
- **Audit on every attempt.** Each `self_heal_attempts` row emits
  `self_heal.remediated` on success and `self_heal.failed` on
  error. `skipped_cap` is a row only — no audit, no noise.
- **Rollout flag.** `CODER_SELF_HEALING_ENABLED` (default off)
  short-circuits the entire watchdog tick. Per-pattern `mode`
  provides a second axis — the flag can be on fleet-wide while a
  brand-new pattern stays in `dry_run`.
- **Watchdog is stateless.** Every attempt row is its own
  transaction; crashing mid-tick leaves consistent DB state. Next
  tick resumes from DB alone.

## Interfaces

- **Table (migration 0049):** `self_heal_attempts` — columns
  include `id`, `pattern_id`, `target_type`, `target_id`,
  `project_id`, `mode`, `outcome`
  (`remediated|failed|skipped_cap|dry_run`), `detail jsonb`,
  `attempted_at`. Indexes on `(pattern_id, target_id,
  attempted_at)` for the cap check and `(attempted_at DESC)` for
  recent-activity queries.
- **Package:** `coder_core.self_heal` —
  - `registry.py` lists active remediators.
  - `protocol.py` defines the `Remediator` interface and the
    `Outcome` / `Target` dataclasses.
  - `patterns/stuck_queued.py` — the v1 remediator.
  - `watch.py` — Cloud Run Job entrypoint
    (`python -m coder_core.self_heal.watch`); `tick()` is the
    orchestrator.
  - `models.py` — domain models shared across patterns.
- **Cloud Run Job:** `coder-core-self-heal-tick` invoked every
  minute by Cloud Scheduler `coder-core-self-heal-tick` (matching
  the cadence + naming convention of `coder-core-auto-approve-tick`).
- **Env flags:** `SELF_HEALING_ENABLED` (default false), per-pattern
  mode settings on the config object.
- **Peer call:** `POST /v1/projects/{id}/escalations/{id}/resolve`
  (defined by [escalations](./escalations.md)).

## Dependencies

- [task-orchestration](./task-orchestration.md) — detection reads
  `tasks` + `pipeline_runs` + `DispatcherQueue` depth; remediations
  re-invoke existing override paths (`/tasks/{id}/retry` clone etc).
- [escalations](./escalations.md) — peer consumer of the trigger
  surface; resolver endpoint is the integration seam.
- [audit-log](../tenancy/audit-log.md) — `self_heal.remediated` /
  `self_heal.failed` actions, one per successful or errored
  attempt.
- [observability](./observability.md) — `/metrics` grows a
  `self_heal` block (attempts by outcome, captures — escalations
  resolved by the watchdog).

## Evolution

- 2026-04-22 — Initial ship (spec 0042): watchdog, `stuck_queued`
  pattern, escalation close-out, default flag off.
- 2026-04-25 — `zombie_executing` (timestamp-based) ships; Cloud Run
  Job `coder-core-self-heal-tick` deployed; fleet flag on, pattern in
  `dry_run`. Threshold bumped 25→45 min alongside spec 0056 Phase 1.
- 2026-05-05 — TOCTOU race fix (coder-core#157): atomic CAS in
  remediate() prevents clobbering rows that succeeded mid-tick.
  Post-fix real orphan-death rate ≤ 4% on `coder` project.

## Links

- Designs: [self-healing](../../../designs/active/pipeline/self-healing.md)
- Related components: task-orchestration, escalations,
  observability, audit-log, admin-panel

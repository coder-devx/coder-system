---
id: self-healing
title: Self-healing stuck pipelines
type: spec
status: active
owner: ro
created: 2026-04-23
updated: 2026-05-06
last_verified_at: 2026-05-06
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
- [audit-log](./audit-log.md) — `self_heal.remediated` /
  `self_heal.failed` actions, one per successful or errored
  attempt.
- [observability](./observability.md) — `/metrics` grows a
  `self_heal` block (attempts by outcome, captures — escalations
  resolved by the watchdog).

## Evolution

- **0042 Self-healing stuck pipelines (v1 shipped 2026-04-22,
  coder-core `c992a7b`).** Migration 0049, `coder_core.self_heal`
  package, Cloud Run Job watchdog, `stuck_queued` pattern, escalation
  close-out integration. Default flag off. 556 LoC of tests in
  `tests/test_self_heal_watch.py`. v1 ship scope was `stuck_queued`
  only.
- **`zombie_executing` v1.1 (timestamp-based) shipped 2026-04-25.**
  Adds the second pattern from the original WIP, scoped down: detects
  rows in `status='running'` whose `started_at` is older than
  `zombie_executing_min_minutes` (default 25) and CAS-resets them to
  `queued` for re-dispatch. Deliberately omits the heartbeat-based
  variant (`tasks.heartbeat_at` + `/tasks/{id}/heartbeat`) — that
  needs a migration and a worker-supervisor wrapper, both deferred.
  The pure-timestamp version covers the operationally-felt symptom
  (rows stuck running for hours after a Cloud Run instance died
  mid-dispatch) without any schema change. Pattern uses the
  established mode flag (`self_heal_pattern_zombie_executing_mode`,
  default `off`); rollout is the documented `dry_run` → `apply` ramp.
- **Watchdog infra deployed 2026-04-25.** The Cloud Run Job
  `coder-core-self-heal-tick` runs `python -m coder_core.self_heal.watch`
  every minute, triggered by Cloud Scheduler of the same name —
  matching the existing `coder-core-auto-approve-tick` shape.
  Without this, `tick()` had no callsite and the
  `self_healing_enabled` flag was effectively a no-op. Same deploy
  flipped `SELF_HEALING_ENABLED=true` and
  `SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE=dry_run` — soak begins.
- **`zombie_executing` threshold and mode alignment (2026-04-28).**
  Two operational fixes shipped alongside spec 0056 Phase 1: (1) the
  `coder-core-self-heal-tick` Cloud Run Job had
  `SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE=dry_run` while the service
  had `apply` — the Job's reaper detected zombies but wrote `dry_run`
  attempt rows that filled the daily cap without mutating task rows;
  fixed by flipping the Job env var to `apply`. (2)
  `zombie_executing_min_minutes` bumped 25 → 45 to exceed the worker
  subprocess timeout (`coder_developer_task_timeout_seconds=2400 s =
  40 min`) plus a 5-min grace, preventing premature eviction of live
  workers that were still running within their budget.
- **`zombie_executing` TOCTOU race fix (2026-05-05,
  [coder-core#157](https://github.com/coder-devx/coder-core/pull/157)).**
  The watch-loop tick held one ORM session for the full pass:
  `detect()` loaded the row into the session identity map while
  `status=running`; between `detect()` and `remediate()` the
  worker's writeback (separate pod, separate transaction) flipped
  the row to `status=succeeded`. `session.get()` in `remediate()`
  returned the cached snapshot — the safety-check passed, an ORM
  UPDATE without a status `WHERE` clobbered `failure_kind` /
  `failure_detail` / `error` onto a legitimately-succeeded row.
  Fix: `remediate()` now issues an atomic
  `UPDATE … WHERE id=? AND status='running'` and reports
  `action=already_moved` on `rowcount=0`. Regression test updated
  to reuse the same session for detect + remediate, mirroring
  production (the pre-existing `already_moved` test used fresh
  sessions per call, which inadvertently dodged the bug). Post-fix
  real orphan-death rate on `coder` project (7-day window): 0%
  reviewer, ~4% developer — far below the pre-fix apparent figures
  of 50% / 11% which were measurement artifacts from the race.
- **Role clarification: `zombie_executing` is a guardrail, not a
  recovery path.** Post-spec-0056 Phase 2, the canonical terminal
  writeback is performed by the Cloud Run Job itself before exiting.
  The `zombie_executing` remediator fires only when the Job is
  abnormally terminated before its writeback (genuine OOM, GCP
  eviction, container crash). Per-day-cap + `apply` mode ensure it
  does not loop on healthy runs. Self-heal remains a safety net;
  routine task completion must not depend on it.
- The `orphan_chain_hook` (replay pipeline chain after hook failure)
  pattern is **not yet shipped** — needs
  `/v1/_admin/pipeline-runs/{id}/replay-chain` first.
- **Admin UI.** `/admin/self-heal` listing attempts is **not yet
  shipped** — a follow-up once the fleet flag flips from `off` and
  there's real attempt data worth a page. Operator visibility in v1
  is via `SELECT * FROM self_heal_attempts ORDER BY attempted_at
  DESC` plus the `self_heal.*` audit events.

## Links

- Designs: [self-healing](../../designs/active/self-healing.md)
- Related components: task-orchestration, escalations,
  observability, audit-log, admin-panel

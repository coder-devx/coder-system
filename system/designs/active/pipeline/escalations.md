---
id: escalations
title: Escalations & on-call routing
type: design
status: active
owner: ro
created: 2026-04-23
updated: 2026-04-23
last_verified_at: 2026-04-23
summary: On-call ladder for unresolved task failures.
implements_specs: [escalations]
related_designs: [system-overview, worker-communication, observability-and-cost-tracking, audit-log]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin]
parent: pipeline-operations
---

# Escalations & on-call routing

## What it is

One table (`escalations`) is the source of truth for every open /
acknowledged / resolved pipeline incident. A 1-minute Cloud Run Job
runs two functions against DB state — `scan_triggers` opens new
rows, `advance_rungs` walks the ladder on existing ones — and
advances every row through its policy's rung list until it's acked
or terminal. Three dispatcher functions (Slack channel, Slack DM,
PagerDuty) consume an `EscalationContext` and post. No queues, no
Redis, no in-process timers: Postgres plus Cloud Scheduler plus the
row's `next_rung_due_at` column are the clock.

## Architecture

```mermaid
flowchart TB
  subgraph state [Postgres]
    pr[(pipeline_runs<br/>blocked_since, started_at)]
    t[(tasks<br/>status, stage, updated_at)]
    tm[(task_messages)]
    esc[(escalations)]
    ocs[(on_call_schedules)]
    proj[(projects<br/>sla_* + policy + slack/PD IDs)]
    ae[(audit_events)]
  end

  subgraph job ["Cloud Run Job:<br/>coder-core-escalation-watch"]
    tick[1-min tick]
    scan[scan_triggers]
    open[open_escalation]
    advance[advance_rungs]
  end

  tick --> scan
  scan --> pr
  scan --> t
  scan --> tm
  scan --> proj
  scan -->|dedupe via| esc
  scan --> open
  open --> esc
  open --> dispatch
  tick --> advance
  advance --> esc
  advance --> dispatch

  subgraph dispatch [Dispatchers]
    s0[dispatch_slack_channel]
    s1[dispatch_slack_dm]
    s2[dispatch_pagerduty]
  end

  dispatch --> slack[Slack webhook/API]
  dispatch --> pd[PagerDuty Events API v2]
  dispatch --> ae

  subgraph api ["coder-core HTTP"]
    ack[POST /escalations/:id/ack]
    resolve[POST /escalations/:id/resolve]
    slackhook[POST /v1/_hooks/slack/escalation_ack]
    ocsget[GET/PATCH /projects/:id/on-call]
  end

  slack -. Ack button .-> slackhook
  slackhook --> esc
  slackhook --> ae
  ack --> esc
  ack --> ae
  resolve --> esc
  resolve --> ae
  ocsget --> ocs

  subgraph admin [coder-admin]
    list[/admin/escalations]
    proj_tab[/projects/:id/escalations]
  end

  list --> esc
  proj_tab --> esc
  proj_tab --> ocs

  classDef pg fill:#fff3e0,stroke:#e65100
  class pr,t,tm,esc,ocs,proj,ae pg
```

## Parts

- **`escalations` table (migration 0046).** `id uuid PK`,
  `project_id text FK`, `trigger_kind` enum
  (`stall|failure_streak|sla_breach`), `pipeline_run_id`/`task_id`
  (CHECK one is set), `status` enum
  (`open|acknowledged|resolved|expired`), `policy_name`,
  `current_rung text` (`L0|L1|L2`), `rung_history jsonb`,
  `next_rung_due_at`, `opened_at`, `last_observed_at`,
  `acknowledged_*`, `resolved_*`. Two partial unique indexes on
  `(project_id, trigger_kind, pipeline_run_id|task_id) WHERE
  status='open'` enforce dedupe at the DB level. `escalations_watcher_idx`
  on `(next_rung_due_at) WHERE status='open' AND
  next_rung_due_at IS NOT NULL` keeps the advance query cheap.
- **`on_call_schedules` table (migration 0047).** Overlapping
  windows allowed; resolver picks the most-recently-created row
  whose `[starts_at, ends_at)` covers `now()`.
- **`projects` columns (migration 0048).** `escalation_policy`
  (default `'off'`), `sla_stall_minutes` (60),
  `sla_wall_clock_minutes` (720), `failure_streak_n` (3),
  `failure_streak_window_minutes` (30),
  `escalation_slack_channel_id` (nullable), `pagerduty_routing_key`
  (nullable). `PATCH /v1/projects/{id}` accepts all.
- **`coder_core.escalations.policies`** loads
  `config/escalation_policies.yaml` once at boot into typed
  `EscalationPolicy` dataclasses; a validation check at import time
  ensures every `destination` has a registered dispatcher.
- **`coder_core.escalations.watcher`** owns `scan_triggers`,
  `open_escalation`, and `advance_rungs`. `watch.py` is the Cloud
  Run Job entry point (`python -m coder_core.escalations.watch`).
  Watcher runs each tick as a single DB session; every mutation is
  a discrete commit so crashes don't leave partial state.
- **Dispatchers** (`escalations/dispatchers/`) each consume an
  `EscalationContext` (project + trigger + run/task + rung-history
  + ack-link URL) and return a `DispatchOutcome` (`ok` /
  `skipped:<reason>` / `error:<detail>`). Slack reuses the fleet
  client already used by 0032 regression detector + observability;
  PagerDuty posts to Events API v2 with the project's routing key;
  missing key → `skipped:no_routing_key` + structured warning.
- **Slack interactive hook** (`api/slack_hooks.py`) verifies the
  signing secret, decodes the `action_id` to recover
  `(escalation_id, project_id)`, resolves Slack user ID → internal
  user (fallback: records the raw handle with
  `acknowledged_by_type='slack_external'`), calls the same ack logic.
- **On-call endpoints** (`api/on_call.py`): `GET /on-call` returns
  the resolver's pick, `GET/PATCH /on-call/schedule` lists/replaces
  the schedule rows for a project.

## Invariants

1. **At most one open escalation per `(project, trigger, target)`.**
   Enforced by the DB via the two partial unique indexes; the
   app-level `open_escalation` path catches `IntegrityError` and
   bumps `last_observed_at` on the existing row.
2. **Rungs advance monotonically.** `current_rung` only increases
   through the policy's rung list; `FOR UPDATE SKIP LOCKED` in
   `advance_rungs` prevents concurrent ticks from both advancing
   the same row.
3. **Terminal rungs never re-fire.** `next_rung_due_at=NULL`
   removes the row from the advance query entirely.
4. **Ack / resolve is idempotent.** A second call on a non-`open`
   row returns 200 without re-auditing.
5. **Watcher is stateless.** Crash mid-tick leaves DB state
   consistent; next tick resumes from DB state alone.

## Data flow

### Scenario A — stall → L0 Slack → ack

1. `acme` project has `sla_stall_minutes=60`,
   `escalation_policy=standard`, Slack channel configured.
2. Run `abc` sits at `spec_approval` with `blocked_since=T`.
3. Watcher tick at `T+60min+ε` hits the stall query;
   `open_escalation` inserts a row, `current_rung='L0'`,
   `next_rung_due_at=T+65min`.
4. `dispatch_slack_channel` posts run link + Ack button; audit row.
5. At `T+63min` operator clicks Ack; Slack hook acks; row
   `acknowledged`; `next_rung_due_at=NULL`; audit row.

### Scenario B — unacknowledged ladder to PagerDuty

L0 fires; no click. `advance_rungs` at `T+65min` dispatches L1 DM;
at `T+75min` dispatches L2 PagerDuty. `current_rung='L2'`,
`next_rung_due_at=NULL`. PagerDuty ack doesn't propagate back —
the row stays `open` until resolved manually or by the underlying
run closing.

### Scenario C — 0042 self-healing closes before L1

Watchdog detects the same stall, retries the stuck task, posts
`.../resolve` with `resolved_by_id='self_healing'`. Row transitions
to `resolved` mid-ladder; further rungs stop. Capture rate measured
on the resolver field.

### Scenario D — dedupe

Same stall signal on the same run while the escalation is still
open: `open_escalation` hits the partial unique index →
`IntegrityError` → handler catches, bumps `last_observed_at`, no
dispatch, no audit.

## Interfaces

`/metrics` includes the `escalations` rollup:

```json
"escalations": {
  "open": 4,
  "mean_ack_minutes_7d": 6.2,
  "rung2_rate_7d": 0.12,
  "false_positive_rate_7d": 0.08,
  "by_trigger_7d": {"stall": 11, "failure_streak": 3, "sla_breach": 2}
}
```

Structured-log events: `escalation.opened`, `.rung_fired`,
`.dispatch_skipped`, `.dispatch_error`, `.acknowledged`, `.resolved`.
Five new `escalation.*` audit actions. Per-project fields on
`PATCH /v1/projects/{id}`: SLA minutes, escalation policy, Slack
channel ID, PagerDuty routing key.

## Where in code

- `src/coder_core/escalations/watch.py` — watcher loop entry
- `src/coder_core/escalations/policies.py` — three-rung ladder + quiet hours
- `src/coder_core/escalations/dispatchers/{slack,pagerduty}.py` — rung dispatchers
- `src/coder_core/api/escalations.py` — list / acknowledge / resolve endpoints
- `src/coder_core/api/slack_hooks.py` — Slack interactive-payload acknowledger
- `migrations/0046_escalations.py`, `0047_on_call_schedules.py`, `0048_projects_escalation_columns.py`

## Evolution

Per ADR 0015 the rung ladder lives in the Coder pipeline (not the
managed project). Integrates with the [self-healing](./self-healing.md)
watchdog: auto-resolutions call `.../resolve` with `actor=self_healing`.

## Links

- Spec: [escalations](../../../product-specs/active/escalations.md)
- Related designs: [system-overview](../system-overview.md),
  [worker-communication](./worker-communication.md),
  [audit-log](../tenancy/audit-log.md),
  [observability-and-cost-tracking](./observability-and-cost-tracking.md)

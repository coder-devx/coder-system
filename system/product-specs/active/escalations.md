---
id: escalations
title: Escalations & on-call routing
type: spec
status: active
owner: ro
created: 2026-04-23
updated: 2026-05-13
last_verified_at: 2026-05-13
summary: Three-rung on-call ladder with quiet hours.
served_by_designs: [escalations]
related_specs: [task-orchestration, observability, audit-log, admin-panel, multi-tenancy, continuous-deployment]
parent: pipeline-operations
---

# Escalations & on-call routing

## What it is

When a pipeline run stalls, fails repeatedly, or breaches SLA, the
escalation watcher opens a row and walks a three-rung ladder —
Slack channel → Slack DM to the project's on-call → PagerDuty —
until someone acknowledges or resolves it. Per-project thresholds,
per-project Slack channel, per-project on-call rotation, per-project
PagerDuty routing key. Every transition is an `audit_events` row.
The observability stream already handles metric-shaped alerts
(cost, regressions); this is the pipeline-run-shaped counterpart so
a stall no longer waits for someone to open the admin panel.

## Capabilities

- **Five trigger kinds.** The watcher scans Postgres state every
  minute: `stall` (`pipeline_runs.blocked_since` older than
  `projects.sla_stall_minutes`, default 60), `failure_streak`
  (≥ `projects.failure_streak_n` consecutive `tasks.status='failed'`
  within `failure_streak_window_minutes`, defaults 3 / 30),
  `sla_breach` (`pipeline_runs` open longer than
  `sla_wall_clock_minutes`, default 720 = 12h), and
  `ci_fix_exhausted` — fired by the CI fix-loop watcher (spec 0053)
  when `MAX_CI_FIX_ATTEMPTS` consecutive fix-up tasks fail on a
  managed PR; `target_type='pr'`, `target_id=pr_url`. Additionally,
  `migrate_failure` — fired directly by the `coder-core` deploy
  workflow when the `coder-core-migrate` Cloud Run Job step exits
  non-zero; `target_type='deploy_job'`, payload carries the Cloud Run
  Job execution name and the Alembic error output; severity `high`.
  The three-rung ladder and ack/resolve flow are identical for all
  trigger kinds. DispatcherQueue-blocked tasks are excluded from
  `stall` detection.
- **Three-rung ladder.** Each escalation picks a policy (`off` /
  `standard` / `aggressive`) and advances monotonically. `standard`:
  L0 post to project Slack channel → wait 5 min → L1 DM the on-call →
  wait 10 min → L2 PagerDuty. `aggressive`: L0 → wait 2 min → L2.
  Rungs live in `config/escalation_policies.yaml`; adding a
  destination is one dispatcher function.
- **Per-project on-call rotation.** `on_call_schedules` table stores
  overlapping `(slack_user_id, pagerduty_user_id, starts_at, ends_at,
  timezone)` entries; the resolver picks the most-recently-created
  row whose window covers `now()`. Missing → falls back to the
  project owner identity.
- **Acknowledge + resolve flow.** API `POST
  /v1/projects/{id}/escalations/{id}/acknowledge` and `.../resolve`
  plus a Slack interactive-button hook at
  `POST /v1/_hooks/slack/escalation_ack` (verified via the existing
  Slack signing secret). Ack stops further rungs; resolve closes.
  Calls take `SELECT FOR UPDATE` so a concurrent watcher rung-advance
  serialises with the operator click; a repeat ack/resolve on a
  non-`open` row returns 409 `already_<status>` rather than silent
  re-application.
- **DB-enforced dedupe.** Partial unique indexes on
  `(project_id, trigger_kind, pipeline_run_id)` and
  `(project_id, trigger_kind, task_id)` `WHERE status='open'`. A
  second stall signal on the same run while one is open bumps
  `last_observed_at` instead of re-opening. Different trigger kinds
  on the same run coexist — one run can stall _and_ breach SLA.
- **Audit on every transition.** Five new `escalation.*` actions
  (`opened`, `rung_fired`, `acknowledged`, `resolved`, `expired`)
  registered with `Actions`; each transition writes an
  `audit_events` row inside the same transaction.
- **Admin surfaces.** `/admin/escalations` (fleet) and
  `/projects/:id/escalations` (per-project) render open / acked /
  resolved escalations with age, rung, project, run link, on-call
  identity. Both behind `VITE_ESCALATIONS_ENABLED`. CI-stuck PRs
  surface with a `ci_fix_exhausted` chip distinct from pipeline-run
  stalls.
- **Watcher is stateless.** A 1-minute Cloud Run Job
  `coder-core-escalation-watch` ticked by Cloud Scheduler; every
  mutation is its own transaction, crash mid-tick leaves clean DB
  state, next tick resumes from DB. `SELECT FOR UPDATE SKIP LOCKED`
  prevents two concurrent ticks from double-firing a rung.
- **Rollout flag.** `CODER_ESCALATIONS_ENABLED` gates the watcher
  (default off on first deploy — short-circuits all triggers).
  Per-project `escalation_policy='off'` skips escalation even when
  the fleet flag is on. Backout is an env flip; tables keep existing
  rows.
- **Integration hook for 0042.** The self-healing watchdog calls
  `.../resolve` with `resolved_by_id='self_healing'` when it
  remediates before a human acks, so capture rate is measurable
  on the escalation log.

## Interfaces

- **Tables (migrations 0046, 0047, 0048):** `escalations`,
  `on_call_schedules`, and seven new `projects` columns
  (`escalation_policy`, `sla_stall_minutes`,
  `sla_wall_clock_minutes`, `failure_streak_n`,
  `failure_streak_window_minutes`, `escalation_slack_channel_id`,
  `pagerduty_routing_key`).
- **Endpoints:**
  - `GET /v1/projects/{id}/escalations`
  - `GET /v1/projects/{id}/escalations/{id}`
  - `POST /v1/projects/{id}/escalations/{id}/acknowledge`
  - `POST /v1/projects/{id}/escalations/{id}/resolve`
  - `GET /v1/_admin/escalations?project_id=&status=&trigger=&limit=`
  - `GET /v1/_admin/escalations/{id}`
  - `POST /v1/_hooks/slack/escalation_ack`
  - `GET /v1/projects/{id}/on-call`
  - `GET /v1/projects/{id}/on-call/schedule`
  - `PATCH /v1/projects/{id}/on-call/schedule`
- **Admin pages:** `/admin/escalations`,
  `/projects/:projectId/escalations` (both behind
  `VITE_ESCALATIONS_ENABLED`).
- **Cloud Run Job:** `coder-core-escalation-watch` invoked every
  minute by Cloud Scheduler; same image + service account shape as
  the 0032 regression detector and 0038 rotator.
- **Env flags:** `CODER_ESCALATIONS_ENABLED` (default false),
  `VITE_ESCALATIONS_ENABLED`, `SLACK_SIGNING_SECRET` (reused),
  `PAGERDUTY_EVENTS_API_URL` (defaults to standard endpoint).
- **Runbook:** [escalations-firing](../../runbooks/escalations-firing.md).

## Dependencies

- [task-orchestration](./task-orchestration.md) — the watcher reads
  `pipeline_runs` and `tasks` to detect triggers; `DispatcherQueue`
  state is consulted so queueing doesn't count as stall.
- [observability](./observability.md) — `/metrics` grows an
  `escalations` block (open count, mean-ack, rung-2 rate,
  false-positive rate, by-trigger counts).
- [audit-log](./audit-log.md) — the five `escalation.*` actions
  are registered there; every state transition lands a row.
- [admin-panel](./admin-panel.md) — hosts the two admin pages.
- [multi-tenancy](./multi-tenancy.md) — the per-project tri-state
  flags + Slack/PD configuration sit on the `projects` row.
- [continuous-deployment](./continuous-deployment.md) — the deploy
  workflow fires `migrate_failure` escalations directly via
  `open_escalation` when the migrate step exits non-zero.

## Evolution

- **0041 Escalation policies & on-call routing (shipped 2026-04-22,
  coder-core `c992a7b`).** Migrations 0046/0047/0048,
  `coder_core.escalations` package (watcher, detectors, policies,
  oncall, Slack + PagerDuty dispatchers), `api/escalations.py`,
  `api/on_call.py`, `api/slack_hooks.py`, Cloud Run Job + Scheduler.
  3,000+ LoC of tests. Default flag off fleet-wide; rollout is the
  documented 3-stage ramp (shadow → L0-only fleet → per-project
  full-ladder opt-in with `coder` first).
- **Admin UI shipped 2026-05-03.** `/admin/escalations` (fleet)
  and `/projects/:projectId/escalations` (per-project) pages render
  the existing `EscalationRead` rows from
  `GET /v1/_admin/escalations` and `GET /v1/projects/{id}/escalations`
  with status + trigger filters, rung chips, target run/task deep
  links, and inline `Ack` / `Resolve` actions wired to the existing
  POST endpoints. New `listProjectEscalations` /
  `listFleetEscalations` / `acknowledgeEscalation` /
  `resolveEscalation` client bindings; project sub-nav grows the
  Escalations tab. 6 vitest cases. Behind `VITE_ESCALATIONS_ENABLED`
  (default on). No backend changes — the UI rides the contract that
  shipped on 2026-04-22.
- **0053 CI-fix-exhausted trigger** — the CI fix-loop watcher (spec
  0053) calls the escalation service's `open_escalation` with
  `trigger_kind='ci_fix_exhausted'`, `target_type='pr'`,
  `target_id=pr_url` when `MAX_CI_FIX_ATTEMPTS` is exhausted on a
  managed PR. No schema migration — the existing `escalations` table
  accommodates the new trigger kind; `pipeline_run_id` and `task_id`
  are NULL for PR-scoped escalations, `target_id` carries the PR URL.
  Admin escalations pages surface CI-stuck PRs with a
  `ci_fix_exhausted` chip alongside pipeline-run stalls.
- **0082 — `migrate_failure` trigger kind.** The `coder-core` deploy
  workflow calls `open_escalation` with `trigger_kind='migrate_failure'`,
  `target_type='deploy_job'`, severity `high`, and a structured payload
  (Cloud Run Job execution name + Alembic error) when the
  `coder-core-migrate` step exits non-zero. No schema migration — the
  existing `escalations` table accommodates the new trigger kind.
  Additive to the existing Slack deploy-failure notification. Responds
  to the 2026-05-10 incident where 17 deploys failed silently at the
  migrate step without paging anyone.

## Links

- Designs: [escalations](../../designs/active/escalations.md)
- Related components: task-orchestration, observability, audit-log,
  admin-panel, multi-tenancy, self-healing, continuous-deployment

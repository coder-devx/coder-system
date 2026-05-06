---
id: escalations
title: Escalations & on-call routing
type: spec
status: active
owner: ro
created: 2026-04-23
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: [escalations]
related_specs: [task-orchestration, observability, audit-log, admin-panel, multi-tenancy]
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

- **Three trigger kinds.** The watcher scans Postgres state every
  minute: `stall` (`pipeline_runs.blocked_since` older than
  `projects.sla_stall_minutes`, default 60), `failure_streak`
  (≥ `projects.failure_streak_n` consecutive `tasks.status='failed'`
  within `failure_streak_window_minutes`, defaults 3 / 30), and
  `sla_breach` (`pipeline_runs` open longer than
  `sla_wall_clock_minutes`, default 720 = 12h). DispatcherQueue-blocked
  tasks are excluded — queueing isn't a stall.
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
  re-application. On ack the Slack message is updated in-place (via
  `chat.update`) within 3 seconds to show the acknowledging user's
  display name.
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
  identity. Both behind `VITE_ESCALATIONS_ENABLED`.
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
- **Enriched Slack message format.** L0 channel posts and L1 on-call
  DMs use a Slack Block Kit template that carries: project name, task
  ID, current pipeline stage, trigger kind label (`stall` /
  `failure_streak` / `sla_breach`), human-readable blocked duration
  (e.g. "stalled for 1 h 23 m"), an interactive `Ack` button wired
  to `POST /v1/_hooks/slack/escalation_ack`, and a `View in admin`
  button that deep-links to
  `{CODER_ADMIN_BASE_URL}/projects/:projectId/pipeline/:taskId`. For
  `failure_streak` triggers the message also includes the streak
  count and the stage at which the most-recent task failed. L1 DMs
  carry the same fields and buttons as L0 — no information is
  dropped when the watcher advances rungs. When `CODER_ADMIN_BASE_URL`
  is absent (e.g. local-dev), the dispatcher omits the `View in
  admin` button and logs a config warning; the text fields still
  send so the message remains useful. The `View in admin` button
  links to the task detail page (not the escalations list); a
  secondary plain-text "See escalation" URL points to the escalation
  detail page for operators who need rung history.

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
  `PAGERDUTY_EVENTS_API_URL` (defaults to standard endpoint),
  `CODER_ADMIN_BASE_URL` (used by the Slack dispatcher to construct
  per-task deep-link URLs; omit button gracefully when absent).
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
- [admin-panel](./admin-panel.md) — hosts the two admin pages;
  the task detail route `/projects/:projectId/pipeline/:taskId` is
  the deep-link target for `View in admin`.
- [multi-tenancy](./multi-tenancy.md) — the per-project tri-state
  flags + Slack/PD configuration sit on the `projects` row.

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
- **0062 Enriched Slack message format (shipped 2026-05-06).** The
  Slack dispatcher now uses a Block Kit template that includes project
  name, task ID, pipeline stage, trigger kind, blocked duration, `Ack`
  interactive button, and `View in admin` deep-link button on both L0
  and L1 messages. `failure_streak` messages additionally carry the
  streak count and the failed stage. Introduces `CODER_ADMIN_BASE_URL`
  env var; the button is omitted gracefully when absent. Ack via Slack
  calls `chat.update` within 3 s to display the acknowledging user.
  End-to-end QA verified: synthetic stall alert → `View in admin` →
  task detail → Slack ack in under 2 minutes.

## Links

- Designs: [escalations](../../designs/active/escalations.md)
- Related components: task-orchestration, observability, audit-log,
  admin-panel, multi-tenancy, self-healing

---
id: '0041'
title: Escalation policies & on-call routing
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
served_by_designs: ['0041']
related_specs:
  - task-orchestration
  - observability
  - audit-log
  - admin-panel
  - multi-tenancy
---

# 0041 — Escalation policies & on-call routing

## Problem

Today the pipeline fails silently to a specific human. Cost and
regression alerts ([observability](../active/observability.md) +
[0032](./0032-cost-regression-alerts.md)) fire into Slack, but
_pipeline-health_ signals — a run blocked on a gate for 4 hours, a
task that's failed three times in a row, a run that's been going
for 12 hours when the p95 is 2 — do not. An operator only finds
out because they opened the admin panel and noticed the red.

As we push toward less-frequent human gates (0040) and external
pilots (the 0037/0038/0039 security line), we need the inverse of
"let the system auto-approve easy things": when something _does_
go sideways, the right human must know within minutes, not when
they next open a browser. And "right human" is per-project — pilot
customers will each have a different operator rotation.

## Users

- **Operator on call** — wants a Slack DM or a PagerDuty page the
  moment a run they own needs attention, with enough context
  (project, run link, trigger kind, current rung, how-to-ack) to
  resolve without context-switching to four tabs.
- **Project owner** — wants to configure the per-project SLA
  thresholds and on-call rotation without a coder-core PR. At
  minimum: "page me if a run is stalled > 30 min" / "here's the
  rotation for March."
- **Release manager / team lead** — wants the admin panel to show
  active escalations across the fleet with age, rung, and ack status,
  so they can triage during an incident review.
- **Self-healing watchdog (future, from 0042)** — wants the same
  trigger signals this spec emits, as an additional consumer that
  tries remediation before a human is paged. 0041 produces the
  signal; 0042 is a peer consumer.

## Goals

- When a pipeline stalls, fails repeatedly, or exceeds SLA, route
  a notification to a human within ≤ 2 minutes of the trigger
  condition crossing threshold.
- The notification carries enough structured context that the
  oncall can act from their phone: project, pipeline run URL, a
  one-line summary of what's wrong, and a link to
  `/admin/escalations/{id}`.
- Per-project: every project has its own SLA thresholds and own
  on-call rotation. No fleet-wide "one Slack channel for
  everything."
- Acknowledge in one click: a Slack interactive button (or the
  admin UI) marks the escalation `acknowledged` and stops the next
  rung from firing.
- Audit every rung fire, acknowledge, and resolve — ties into
  [audit-log](../active/audit-log.md) with a new `escalation.*`
  action namespace.

## Non-goals

- **Auto-remediation.** 0042 (self-healing) owns _doing something_
  about a stall. 0041 owns detection + routing only. An escalation
  that 0042 auto-resolves is closed with
  `resolved_by='self_healing'` and no human is paged.
- **Complex multi-level on-call policies.** A rotation in v1 is a
  single person on-call at a time per project. Multi-person
  handoffs, overrides, and layered teams are a phase-2 concern.
- **Custom policy authoring per project.** Three built-in policies
  (`off`, `standard`, `aggressive`) cover the expected range. A
  project picks one by name; editing the policy file itself is a
  coder-system PR. Custom per-project policy bodies are phase-2.
- **Replacing the existing observability alerts.** Cost,
  success-rate, and regression alerts from
  [observability](../active/observability.md) continue as they are.
  Escalations are pipeline-run-shaped, not metric-shaped.
- **Rotation management UI.** In v1 you edit a YAML file + restart,
  or `PATCH` the on-call schedule via the API. An admin rotation
  editor is phase-2.
- **SMS / email / phone.** Slack and PagerDuty only. Anything else
  (Teams, Discord, email digest) is phase-2.

## Scope

### In scope

1. **Three trigger kinds.** The watcher detects three
   pipeline-run-shaped conditions:
   - **Stall.** A `pipeline_runs` row has `blocked_since` older than
     the project's `sla_stall_minutes` threshold, or a task sits in
     a non-terminal stage with no progress (no `task_stage_runs`
     row, no `task_messages` row) for `sla_stall_minutes`.
   - **Failure streak.** A project has had ≥ `failure_streak_n`
     consecutive `tasks` lands in `failed` status within the last
     `failure_streak_window_minutes`, across one or more pipeline
     runs. Default 3 / 30min.
   - **SLA wall-clock breach.** A single `pipeline_runs` row has
     been open for longer than `sla_wall_clock_minutes` end-to-end.

2. **Three rungs.** Each escalation advances through up to three
   destinations, with a wait timer between rungs. The default
   `standard` policy:
   - **L0** (immediate): post to the project's Slack channel,
     public, no ping.
   - **L1** (after `5 min` unacknowledged): DM / @-mention the
     currently on-call operator in Slack.
   - **L2** (after another `10 min` unacknowledged): PagerDuty
     Events API v2 trigger to the project's routing key.
   Rungs are monotonic — L2 fires only if L1 fires only if L0
   fired. Acknowledge at any rung stops advancement.

3. **Per-project on-call schedule.** A new `on_call_schedules`
   table stores rotation entries for each project: a user
   identifier (`slack_user_id` + optional `pagerduty_user_id`), a
   `starts_at` + `ends_at` timestamp, and a `timezone`. At
   escalation time the resolver picks the entry where
   `starts_at ≤ now < ends_at`. Defaults to the project-owner
   identity if no rotation is set.

4. **Escalation policy selection.** `projects.escalation_policy`
   is a text column referencing one of three built-in policies:
   - `off` — never escalate.
   - `standard` — the L0/L1/L2 ladder above.
   - `aggressive` — L0 immediate + L2 after 2 min (skips L1).
   Built-in policy bodies live in
   `coder-core/config/escalation_policies.yaml`.

5. **Acknowledge + resolve flow.** Two endpoints:
   - `POST /v1/projects/{id}/escalations/{id}/ack` — takes optional
     `note`, transitions to `acknowledged`, stops rung advancement.
   - `POST /v1/projects/{id}/escalations/{id}/resolve` — takes
     `resolution` (free text), transitions to `resolved`, emits
     audit row, dismisses in the admin panel.
   Plus a Slack interactive-button `ack` that hits the same endpoint
   with `actor_type='user'` resolved from the Slack user ID.

6. **Dedupe.** A pipeline run can have one open escalation per
   trigger kind. A second stall-trigger on the same run while one
   is open is a no-op (just extends the `last_observed_at`
   timestamp). A new trigger kind on the same run can open a new
   escalation (e.g. a run can stall _and_ SLA-breach
   independently).

7. **Watcher.** A 1-minute Cloud Run Job
   `coder-core-escalation-watch` (same shape as 0032 regression
   detector and 0040 auto-approve tick). Scans pipeline_runs +
   tasks for trigger conditions; opens new escalations; advances
   rungs on existing unacknowledged ones whose rung-wait has
   elapsed.

8. **Admin surface.** `/admin/escalations` page listing fleet-wide
   active escalations with age, rung, project, run link. Per-project
   `/projects/{id}/escalations` tab on the project overview
   showing this project's escalations plus the current on-call.
   Both behind `VITE_ESCALATIONS_ENABLED`.

9. **Audit.** Every escalation state change emits an `audit_events`
   row. Action strings: `escalation.opened`, `escalation.rung_fired`,
   `escalation.acknowledged`, `escalation.resolved`,
   `escalation.expired`.

### Out of scope

- Auto-remediation (0042).
- Email / SMS / Teams / phone destinations.
- A rotation editor UI in the admin panel.
- Custom per-project policy bodies.
- Multi-person on-call layering / handoffs.
- Cross-project rollup alerts (e.g. "the fleet is sad" — covered
  by existing observability Slack posts).

## Acceptance criteria

- **AC1.** A pipeline run `blocked_since` older than the project's
  `sla_stall_minutes` opens a new `escalations` row at the next
  watcher tick (within 1 min). Row has `trigger_kind='stall'`,
  `current_rung='L0'`, and a reference to `pipeline_run_id`.

- **AC2.** Opening an escalation at L0 posts to the project's
  configured Slack channel with the project name, run link, trigger
  reason, and an interactive **Ack** button.

- **AC3.** An unacknowledged L0 escalation advances to L1 after
  `policy.l0_to_l1_wait_minutes` (default 5). L1 DMs the resolved
  on-call user in Slack with the same context.

- **AC4.** An unacknowledged L1 advances to L2 after
  `policy.l1_to_l2_wait_minutes` (default 10). L2 triggers a
  PagerDuty incident via Events API v2 against the project's
  routing key.

- **AC5.** Failure-streak trigger: `failure_streak_n` (default 3)
  consecutive `tasks.status='failed'` rows for a single project
  within `failure_streak_window_minutes` (default 30) opens a
  `trigger_kind='failure_streak'` escalation.

- **AC6.** SLA-wall-clock trigger: a `pipeline_runs` row open for
  longer than `sla_wall_clock_minutes` (default 720 = 12 hours)
  opens a `trigger_kind='sla_breach'` escalation.

- **AC7.** Per-project on-call resolution: `on_call_schedules`
  table with a PATCH endpoint; resolver picks the entry covering
  `now` in the project's configured timezone. Missing schedule
  falls back to the project-owner identity.

- **AC8.** Acknowledge endpoint (API + Slack button) transitions
  to `acknowledged` and stops future rung advancement for this
  escalation. Resolve endpoint closes it.

- **AC9.** Dedupe: second stall signal on the same pipeline run
  while one stall escalation is open does not create a new row.
  Different trigger kind on same run _can_ open a new row.

- **AC10.** Every state transition (open, rung_fired, acknowledged,
  resolved, expired) writes an `audit_events` row with the
  escalation ID as `target_id` and `target_type='escalation'`.

- **AC11.** Fleet flag `CODER_ESCALATIONS_ENABLED`. When off, the
  watcher short-circuits (no triggers open, no rungs advance).
  Default off on first deploy.

- **AC12.** `escalation_policy='off'` on a project skips all
  escalation even when the fleet flag is on.

## Metrics

- **Mean time to acknowledge** — from `opened_at` to
  `acknowledged_at`. Per project. Target < 10 minutes for the
  `standard` policy.
- **Rung-2 rate** — % of escalations that reach L2 PagerDuty.
  Target < 20% of opened escalations — if higher, either thresholds
  are too tight or on-call isn't responsive.
- **False-positive rate** — % of escalations resolved within 2
  minutes of open (suggests the trigger fired but the state was
  already recovering). Target < 15%; tune thresholds if higher.
- **Per-trigger-kind counts** — per-project weekly breakdown of
  opened escalations by trigger kind.
- **Self-healing capture rate (forward-looking, for 0042)** — %
  of escalations closed by `resolved_by='self_healing'` before any
  rung beyond L0 fires. Reported once 0042 ships.

## Open questions

- **Slack channel per project vs per-role channel.** Specs 0032
  and observability post to a single fleet-wide Slack channel.
  0041 needs per-project channels (pilot customers shouldn't see
  each other's escalations). Leaning: new
  `projects.escalation_slack_channel_id` column; fallback to
  fleet channel if unset. Noted in design.

- **PagerDuty routing key per project.** Same shape:
  `projects.pagerduty_routing_key`. Not required — L2 skips
  silently if unset. Leaning: log a structured warning on skip so
  operators notice a mis-configured project.

- **Acknowledge authorship.** A Slack button press maps Slack user
  ID → internal user ID. If the Slack user isn't in our user table
  (e.g. an operator from another team), do we refuse or record
  `actor_type='external'`? Leaning: external with the raw Slack
  handle captured in audit; decision on design.

- **SLA clock for chain-dispatched tasks.** Task-level wait time
  includes DispatcherQueue blocking from 0028. Should the stall
  clock pause while queued vs while executing? Probably yes —
  queueing isn't a stall; executing for 2h is. Design should
  clarify which timestamps define stall.

- **Weekend quiet hours.** Should the watcher suppress L2 paging
  outside business hours for a project, or is that the on-call's
  responsibility (PagerDuty schedule)? Leaning: no quiet-hours in
  v1; PagerDuty schedule is the right place.

## Links

- Related specs:
  [task-orchestration](../active/task-orchestration.md),
  [observability](../active/observability.md),
  [audit-log](../active/audit-log.md),
  [admin-panel](../active/admin-panel.md),
  [multi-tenancy](../active/multi-tenancy.md)
- Design: [0041](../../designs/wip/0041-escalation-policies.md)
- Roadmap entry: [ROADMAP.md](../ROADMAP.md) → Phase 7 / 0041

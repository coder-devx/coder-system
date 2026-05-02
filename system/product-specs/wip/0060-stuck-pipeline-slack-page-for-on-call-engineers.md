---
id: '0060'
title: Stuck-pipeline Slack page for on-call engineers
type: spec
status: wip
owner: ro
created: '2026-05-02'
updated: '2026-05-02'
last_verified_at: '2026-05-02'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- 0058
- 0059
- escalations
- self-healing
- task-orchestration
- admin-panel
- observability
---

# Stuck-pipeline Slack page for on-call engineers

**Phase:** wip
**Progress:** 0 / 7 acceptance criteria

## Problem

The [escalations](../active/escalations.md) infrastructure shipped in April 2026 and already implements the stuck-pipeline Slack paging flow end-to-end: it polls for stalls, walks a Slack channel → DM → PagerDuty ladder, deduplicates per pipeline, and audits every transition. However, `CODER_ESCALATIONS_ENABLED` defaults to `off` and `sla_stall_minutes` defaults to 60 minutes — so today a stalled pipeline still sits unnoticed until someone checks the admin panel the next morning. The product gap is not missing code; it is a combination of a threshold that is too loose and a fleet flag that was never flipped for production.

The user-visible symptom: mean time from stall to human awareness is measured in hours, not minutes, for failures an on-call engineer could resolve in under five minutes if notified promptly.

## Users / personas

- **On-call engineer** (primary): whoever is holding the pager when a pipeline stalls. Needs one actionable Slack message — not noise — containing the task ID, the name of the stuck stage, and a single-click link to the admin panel task-detail view. Cannot afford to log in just to understand scope.
- **Team lead / engineering manager**: needs confidence that stalls surface in minutes, not hours, and that the on-call rotation is actually reachable when something breaks overnight.

## Goals

- Enable fleet-wide Slack paging for stuck pipelines within ≤ 15 minutes of a stall crossing the detection threshold.
- Confirm the Slack message body carries the three fields the on-call needs: task ID, current stuck stage name, and a valid one-click admin-panel deep-link for that task.
- Close the overnight blind spot: mean time from stall to first page drops from an overnight lag to ≤ 16 minutes (threshold + one watcher tick).

## Non-goals

- Building a new watchdog or alerting mechanism — the existing escalations L0 Slack rung already covers this; no new infrastructure is required.
- PagerDuty / email / OpsGenie integration — that is the L2 rung of the existing [escalations](../active/escalations.md) ladder, rolled out separately.
- Auto-remediation of stuck pipelines — that is [self-healing](../active/self-healing.md).
- Admin-panel UI for configuring per-project thresholds — the `projects.sla_stall_minutes` column already exists; a settings page is a separate track.
- Alerting on slow-but-progressing pipelines — only truly stuck (no `updated_at` advancement).

## Scope

- Flip `CODER_ESCALATIONS_ENABLED=true` in the production environment after a short shadow-mode soak confirms detection is not noisy.
- Lower the effective stall threshold from 60 minutes to 15 minutes. Fastest path: set `sla_stall_minutes=15` on the `coder` project row first; change the fleet default only after soak confirms acceptable signal-to-noise.
- Verify the L0 Slack message template includes all three required fields: task ID, current stuck stage name, and a correctly formed admin-panel task-detail deep-link. Patch the template if any field is absent or malformed.
- Confirm the admin-panel task-detail URL pattern (`/projects/{project_id}/tasks/{task_id}` assumed) so the deep-link in the message is navigable without further lookups.
- Set `escalation_slack_channel_id` in production for each active project before enabling the fleet flag.
- Deduplication is enforced by the existing partial unique index on `(project_id, trigger_kind, pipeline_run_id) WHERE status='open'` — verify via integration test before fleet enable.

## Acceptance criteria

- [ ] AC1: With `CODER_ESCALATIONS_ENABLED=true` and `sla_stall_minutes=15`, a pipeline whose active task `updated_at` has not advanced for ≥ 15 minutes triggers a Slack message to the project's `escalation_slack_channel_id` within one watcher tick (≤ 1 minute) of crossing the threshold.
- [ ] AC2: The Slack message body contains all three required fields: (a) the task ID, (b) the name of the stage at which the pipeline is stuck, and (c) a correctly formed one-click deep-link URL to the admin panel task-detail view for that task.
- [ ] AC3: A single stuck pipeline generates at most one Slack L0 page per stall window; subsequent watcher ticks do not re-page the same pipeline. Verified by an integration test that confirms the `(project_id, trigger_kind, pipeline_run_id) WHERE status='open'` partial unique index blocks a second open escalation on the same run.
- [ ] AC4: A pipeline that transitions state (advances `updated_at`) before crossing the 15-minute threshold does not trigger a page.
- [ ] AC5: If `escalation_slack_channel_id` is null for a project, the watcher logs a warning and skips that project's Slack rung without crashing or delaying escalation processing for other projects.
- [ ] AC6: All escalation state transitions (`opened`, `rung_fired`, `acknowledged`, `resolved`) are recorded in the audit log for every page fired during a production soak of ≥ 24 hours, with no missing rows.
- [ ] AC7: The admin panel `/projects/:id/escalations` page correctly lists open, acknowledged, and resolved escalations triggered by the 15-minute stall threshold, including the task ID and stuck stage visible in the row.

## Metrics

- Mean time from stall to first Slack page (target: ≤ 16 minutes end-to-end).
- Daily page volume — baseline established during soak; sudden spikes indicate a noisy pattern or a system-health incident.
- False-positive rate during the 24-hour soak: pages that fire but the on-call finds no real stall when they check.
- Escalation capture rate: fraction of pages acknowledged or resolved within 30 minutes vs. those that age to L1 / expire unacked.

## Open questions

- **Admin panel URL pattern:** Confirm the task-detail deep-link route is `/projects/{project_id}/tasks/{task_id}` (or the correct equivalent) before patching the Slack message template.
- **@mention vs. channel-only:** Should the L0 message @mention the on-call user (requires Slack user-ID lookup via `on_call_schedules.slack_user_id`) or post to the channel without a mention? Recommend channel-only for L0; DM to on-call is already L1 in the existing ladder.
- **Per-role thresholds:** 15 minutes is appropriate for Developer and Architect workers. Should PM or Team Manager tasks use a longer window (they are longer-running by design)? Decision can be deferred to the soak phase — start uniform at 15 minutes.

## Links

- Active infrastructure: [escalations](../active/escalations.md), [self-healing](../active/self-healing.md), [admin-panel](../active/admin-panel.md), [task-orchestration](../active/task-orchestration.md), [observability](../active/observability.md)
- Related WIP: [0058](./0058-slack-on-call-page-for-stuck-pipelines.md) — first draft of this problem, [0059](./0059-slack-on-call-page-for-stuck-pipelines.md) — second draft, includes build-vs-configure open question now resolved here

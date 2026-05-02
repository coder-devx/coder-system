---
id: '0061'
title: Stuck-pipeline Slack page — enablement & message spec
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
- '0060'
- escalations
- self-healing
- task-orchestration
- admin-panel
- observability
---

# Stuck-pipeline Slack page — enablement & message spec

**Phase:** wip
**Progress:** 0 / 7 acceptance criteria

## Problem

When a pipeline stalls — a worker crashes mid-stage, a task exceeds expected runtime, or an external call hangs — the failure is silent. The pipeline sits in a stuck state until someone opens the admin panel, typically the next morning. Mean time to recovery is measured in hours even for failures an on-call engineer could resolve in under five minutes if notified promptly.

The [escalations](../active/escalations.md) infrastructure (shipped April 2026) already implements the full detection-and-paging flow, but two gaps keep it dark in production: `CODER_ESCALATIONS_ENABLED` defaults to `off`, and `sla_stall_minutes` defaults to 60 minutes — far too loose for overnight incidents. Prior drafts [0058](./0058-slack-on-call-page-for-stuck-pipelines.md), [0059](./0059-slack-on-call-page-for-stuck-pipelines.md), and [0060](./0060-stuck-pipeline-slack-page-for-on-call-engineers.md) explored this problem; this spec is the authoritative version that closes the open questions from those drafts and defines a concrete rollout sequence.

## Users / personas

- **On-call engineer** (primary): whoever holds the pager when a pipeline stalls overnight or on a weekend. Needs one actionable Slack message — not noise — that gives enough context to triage without logging in first: what broke, at what stage, and a single click to the right admin panel view.
- **Team lead / engineering manager**: needs confidence that stalls surface in minutes, not hours, and that the on-call rotation is reachable whenever something breaks.

## Goals

- Close the overnight blind spot: mean time from stall to first Slack page drops from a multi-hour lag to ≤ 16 minutes (15-minute threshold + one watcher tick).
- Specify and verify the exact Slack message body — task ID, current stuck stage name, valid one-click admin-panel deep-link — so the on-call can act without a second lookup.
- Establish a safe, soak-gated rollout sequence: shadow → single project → fleet, so the fleet flag flip is low-risk.

## Non-goals

- Building a new watchdog or alerting mechanism — the existing escalations `stall` trigger at L0 already covers this; no new infrastructure is required.
- PagerDuty / email / OpsGenie integration — that is the L1/L2 rungs of [escalations](../active/escalations.md), rolled out separately.
- Auto-remediation of stuck pipelines — that is [self-healing](../active/self-healing.md).
- Per-project channel routing or per-role threshold tuning — the `projects.escalation_slack_channel_id` column and `sla_stall_minutes` already support this; a settings UI is a separate track.
- Alerting on slow-but-progressing pipelines — only truly stuck (no `pipeline_runs` / `tasks.updated_at` advancement).

## Scope

**Message content (required fields, in order):**
1. Task ID (the `tasks.id` UUID or short ID).
2. Stuck stage name (the `tasks.stage` or equivalent human-readable label for where the pipeline is frozen).
3. One-click admin-panel deep-link: `{ADMIN_BASE_URL}/projects/{project_id}/tasks/{task_id}` — confirm exact route against admin panel before patching template.

Deduplication is enforced by the existing partial unique index on `(project_id, trigger_kind, pipeline_run_id) WHERE status='open'` in `escalations` — no new dedup code needed.

**Rollout sequence (three stages, each gated on the prior):**
1. **Shadow mode** (detect only, no page): set `CODER_ESCALATIONS_ENABLED=true` with per-project `escalation_policy='off'` on all projects except `coder`. Soak 24 hours; confirm detection signal is not noisy (zero false positives in shadow audit log).
2. **Single-project L0** (Slack page, `coder` project only): set `sla_stall_minutes=15` and `escalation_policy='standard'` on the `coder` project row. Soak 24 hours; confirm ≤ expected page volume and dedup is holding.
3. **Fleet-wide enable**: change the fleet default `sla_stall_minutes` to 15 and set `escalation_slack_channel_id` + `escalation_policy='standard'` on all remaining active projects.

Config required before fleet enable: `SLACK_ONCALL_CHANNEL` (or per-project `escalation_slack_channel_id`) set for every active project.

## Acceptance criteria

- [ ] AC1: With `CODER_ESCALATIONS_ENABLED=true` and `sla_stall_minutes=15`, a pipeline whose active task `updated_at` has not advanced for ≥ 15 minutes triggers a Slack message to the project's `escalation_slack_channel_id` within one watcher tick (≤ 1 minute) of crossing the threshold.
- [ ] AC2: The Slack message body contains all three required fields in a human-readable format: (a) the task ID, (b) the name of the stage at which the pipeline is stuck, and (c) a one-click deep-link URL to the admin panel task-detail view (`{ADMIN_BASE_URL}/projects/{project_id}/tasks/{task_id}`) that resolves to the correct page without further navigation.
- [ ] AC3: A single stuck pipeline generates at most one Slack L0 page per stall window; subsequent watcher ticks do not re-page the same pipeline. An integration test confirms the `(project_id, trigger_kind, pipeline_run_id) WHERE status='open'` partial unique index prevents a second open escalation row for the same run.
- [ ] AC4: A pipeline that advances `updated_at` before crossing the 15-minute threshold does not trigger a page.
- [ ] AC5: If `escalation_slack_channel_id` is null for a project, the watcher logs a warning and skips that project's Slack rung without crashing or delaying escalation processing for other projects.
- [ ] AC6: The 24-hour shadow soak (stage 1) produces zero Slack pages and zero audit rows with `action='escalation.rung_fired'` — detection ran, no messages sent — confirming the shadow mode gate works before the first live page is enabled.
- [ ] AC7: After the fleet-wide enable (stage 3), the admin panel `/projects/:id/escalations` page lists the open, acknowledged, and resolved escalations triggered by the 15-minute stall threshold, with the task ID, stuck stage name, and deep-link visible in each row.

## Metrics

- Mean time from stall to first Slack page (target: ≤ 16 minutes end-to-end).
- Daily page volume per project — baseline from single-project soak; fleet-wide spikes indicate a noisy pattern or a system-health incident.
- False-positive rate during each soak stage: pages where the on-call finds no real stall.
- Escalation capture rate: fraction of L0 pages acknowledged or resolved within 30 minutes vs. those that age to L1 or expire unacked.

## Open questions

- **Admin panel URL pattern:** Confirm the task-detail deep-link route is `/projects/{project_id}/tasks/{task_id}` (or the correct equivalent) before patching the Slack message template. If the route differs, AC2 requires a template patch.
- **@mention vs. channel-only:** Should L0 messages @mention the current on-call user (requires Slack user-ID lookup via `on_call_schedules.slack_user_id`) or post to the channel without a mention? Recommendation: channel-only for L0; DM to on-call is already L1 in the existing escalations ladder.
- **Per-role thresholds post-soak:** 15 minutes is appropriate for Developer and Architect workers. PM and Team Manager tasks are longer-running by design — revisit after fleet soak if false-positive rate is elevated for those roles.

## Links

- Active infrastructure: [escalations](../active/escalations.md), [self-healing](../active/self-healing.md), [admin-panel](../active/admin-panel.md), [task-orchestration](../active/task-orchestration.md), [observability](../active/observability.md)
- Prior drafts of this problem: [0058](./0058-slack-on-call-page-for-stuck-pipelines.md), [0059](./0059-slack-on-call-page-for-stuck-pipelines.md), [0060](./0060-stuck-pipeline-slack-page-for-on-call-engineers.md)

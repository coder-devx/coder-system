---
id: 0059
title: Slack on-call page for stuck pipelines
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
- escalations
- self-healing
- task-orchestration
- admin-panel
- observability
---

# Slack on-call page for stuck pipelines

**Phase:** wip
**Progress:** 0 / 6 acceptance criteria

## Problem

When a pipeline stalls — a worker crashes mid-stage, a task exceeds expected runtime, or an external call hangs — the failure is silent. No alert fires. The pipeline sits in a stuck state until someone happens to open the admin panel, typically the next morning. Mean time to recovery is measured in hours even for failures a human could resolve in under five minutes if notified promptly.

The existing [escalations](../active/escalations.md) spec ships an L0 Slack notification for stall scenarios, but its default `sla_stall_minutes` threshold is 60 minutes and `CODER_ESCALATIONS_ENABLED` defaults to `off`. This spec captures the product requirement — fast (≤15 min) on-call paging for stuck pipelines — so it can be tracked and accepted independently of the broader escalation ladder rollout.

## Users / personas

- **On-call engineer** (primary): whoever is holding the pager when a pipeline stalls. Needs an actionable alert — not noise — with enough context to triage without logging in first.
- **Team lead / engineering manager**: wants confidence that failures surface fast and that the on-call rotation is actually reachable.

## Goals

- Detect pipelines with no state transition for longer than a configurable threshold (default: 15 minutes).
- Send a single Slack message to the configured on-call channel containing: task ID, the stage at which the pipeline is stuck, and a one-click deep-link to the admin panel task-detail view.
- Keep alert volume low: one page per stuck pipeline, not one per polling tick.

## Non-goals

- Auto-remediation or automatic retries — that is [self-healing](../active/self-healing.md).
- PagerDuty / OpsGenie / email integration — Slack only in this spec.
- Multi-rung escalation ladder or per-project channel routing — that is [escalations](../active/escalations.md).
- Alerting on slow-but-progressing pipelines — only truly stuck (no state transition).

## Scope

- A pipeline is "stuck" when its active task `updated_at` has not advanced for ≥ `STUCK_PIPELINE_THRESHOLD_MINUTES` (default 15).
- Fastest path to ship: configure the existing escalations `stall` trigger with `sla_stall_minutes=15` and flip `CODER_ESCALATIONS_ENABLED=true` fleet-wide. If a separate lightweight watchdog is preferred (lower ops surface), that is also acceptable — Architect decides.
- The Slack message must include: task ID, stuck stage name, and a correctly formed admin panel deep-link to the task-detail view (`/projects/{project_id}/tasks/{task_id}` — confirm route with admin panel).
- An `alerted_at` marker (on the task record, or equivalent dedup in the escalations table) prevents duplicate pages for the same stuck pipeline.
- Config: `SLACK_ONCALL_CHANNEL`, `STUCK_PIPELINE_THRESHOLD_MINUTES` (default 15).

## Acceptance criteria

- [ ] AC1: A pipeline whose active task `updated_at` has not advanced for ≥ `STUCK_PIPELINE_THRESHOLD_MINUTES` triggers a Slack message to `SLACK_ONCALL_CHANNEL` within one polling interval of crossing the threshold.
- [ ] AC2: The Slack message body contains the task ID, the current stuck stage name, and a correctly formed deep-link URL to the admin panel task-detail view for that task.
- [ ] AC3: A single stuck pipeline generates at most one Slack alert; subsequent polling cycles do not re-page for the same stuck pipeline unless it unsticks and re-stalls.
- [ ] AC4: If `SLACK_ONCALL_CHANNEL` is not configured, the watchdog logs a warning and skips alerting without crashing or halting other work.
- [ ] AC5: Pipelines that advance state before the threshold is crossed do not generate an alert.
- [ ] AC6: The detection and alerting mechanism runs independently of the main orchestrator process (as a standalone cron or Cloud Run Job) with a configurable polling interval.

## Metrics

- Mean time from pipeline stall to first Slack page (target: ≤ threshold + one polling interval, i.e. ≤ 16 minutes).
- Daily alert volume — confirms deduplication is holding; sudden spikes indicate a noisy pattern.
- False-positive rate measured during soak before fleet-wide enable.

## Open questions

- **Build vs configure:** Should this be implemented by tuning the existing escalations `stall` trigger (`sla_stall_minutes=15`, enable fleet flag) rather than building a second watchdog? Avoids duplication; risk is coupling this fast page to the full escalation ladder rollout.
- **Admin panel URL pattern:** Confirm the task-detail deep-link route — `/projects/{project_id}/tasks/{task_id}` assumed.
- **@mention:** Should the alert @mention the on-call user directly (requires Slack user-ID lookup) or post to the channel without a mention? Propose: channel-only to start.
- **Default threshold:** Is 15 minutes right for all pipeline types, or should it vary by role (e.g. shorter for Developer, longer for PM)?

## Links

- Related WIP: [0058](./0058-slack-on-call-page-for-stuck-pipelines.md) — earlier draft of this problem
- Active: [escalations](../active/escalations.md), [self-healing](../active/self-healing.md), [admin-panel](../active/admin-panel.md), [task-orchestration](../active/task-orchestration.md)

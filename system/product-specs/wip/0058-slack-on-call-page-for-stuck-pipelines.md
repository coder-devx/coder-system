---
id: '0058'
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
related_specs: []
---

# Slack on-call page for stuck pipelines

**Phase:** wip
**Progress:** 0 / 6 acceptance criteria

## Problem

When a pipeline stalls — a task exceeds its expected runtime, a worker crashes mid-stage, or an external call hangs — the failure is silent. No alert fires. The pipeline sits in a stuck state until someone happens to look at the admin panel, typically the next morning. Mean-time-to-recovery is measured in hours, not minutes, even for failures that a human could resolve in under five minutes if notified promptly.

## Users / personas

- **On-call engineer** (primary): whoever is holding the pager at the moment a pipeline stalls. Needs an actionable alert — not noise — with enough context to triage without logging into anything first.
- **Team lead / engineering manager**: wants confidence that failures surface fast and that the on-call rotation is actually reachable.

## Goals

- Detect pipelines that have been stuck (no state transition) for longer than a configurable threshold.
- Send a single Slack message to the configured on-call channel containing: task ID, the stage at which the pipeline is stuck, and a one-click deep-link to the admin panel task view.
- Keep alert volume low: one page per stuck pipeline, not one per heartbeat tick.

## Non-goals

- Auto-remediation or automatic retries (separate concern).
- PagerDuty / OpsGenie / email integration (Slack only in this spec).
- Alerting on slow-but-progressing pipelines (only truly stuck / no state transition).
- Routing to different channels per project or severity (future work).

## Scope

- A "stuck" pipeline is one whose `updated_at` timestamp on the active task record has not advanced for more than the configured threshold (default: 15 minutes).
- A watchdog cron polls for stuck pipelines and fires the Slack alert.
- The admin panel deep-link uses the existing task-detail route; no new admin panel work is required.
- Configuration: `SLACK_ONCALL_CHANNEL`, `STUCK_PIPELINE_THRESHOLD_MINUTES` (default 15).
- A `alerted_at` field (or equivalent) on the task record prevents duplicate pages for the same stuck pipeline.

## Acceptance criteria

- [ ] AC1: A pipeline whose `updated_at` has not advanced for ≥ `STUCK_PIPELINE_THRESHOLD_MINUTES` triggers a Slack message to `SLACK_ONCALL_CHANNEL` within one polling interval of crossing the threshold.
- [ ] AC2: The Slack message includes the task ID, the current stuck stage name, and a correctly formed deep-link URL to the admin panel task-detail view for that task.
- [ ] AC3: A single stuck pipeline generates at most one Slack alert; no duplicate pages are sent on subsequent polling cycles unless the pipeline unsticks and re-stalls.
- [ ] AC4: If `SLACK_ONCALL_CHANNEL` is not configured, the watchdog logs a warning and skips alerting without crashing.
- [ ] AC5: Pipelines that advance state (i.e. become unstuck) before the threshold is crossed do not generate an alert.
- [ ] AC6: The watchdog can be deployed as a standalone cron job independent of the main orchestrator process, and its polling interval is configurable.

## Open questions

- What is the correct admin panel task-detail URL pattern? Assuming `/tasks/{task_id}` — needs confirmation from the System Admin or existing admin panel routes.
- Should the alert @mention the on-call user directly (requires Slack user ID lookup) or post to the channel without a mention? Start with channel post only.
- Is 15 minutes the right default threshold, or should it vary by pipeline type?

## Links

- Admin panel (existing): see project runbooks for URL.
- Slack Incoming Webhooks or Bot Token API: to be selected by Architect.

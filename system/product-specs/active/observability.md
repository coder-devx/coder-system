---
id: observability
title: Observability
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-15
last_verified_at: 2026-04-15
served_by_designs: [observability-and-cost-tracking]
related_specs: [knowledge-freshness]
---

# Observability

## What it is

The metrics, cost-attribution, and alerting layer over the pipeline.
Every task records its token spend and per-stage durations; aggregates
roll up to per-project daily cost, per-spec cost, and pipeline success
rate; threshold breaches fire Slack alerts; and an admin-panel dashboard
puts the numbers in front of the operator. It is the component that
makes "what did this cost?" and "is the pipeline healthy?" answerable
without SSH.

## Capabilities

- **Per-task cost capture.** Anthropic `usage` (input + output tokens)
  is read from worker responses and written on task completion.
- **Per-stage timing.** Orchestrator hooks write a row to
  `task_stage_durations` on every stage transition, enabling average
  duration per stage across arbitrary windows.
- **Project- and spec-level attribution.** Every metric row carries
  `project_id` and `spec_id`, so cost can be sliced per project, per
  spec, or per pipeline run.
- **Pipeline health.** Success rate over a rolling 24-hour window is
  derived from task outcomes. Fix-loop frequency falls out of
  `fix_attempts` aggregation.
- **Slack alerts.** Fire after every task completion when daily cost
  or success-rate thresholds are breached, with per-alert-type rate
  limiting (1/hour) so a bad day doesn't page twelve times.
- **Admin dashboard.** `/metrics` route with a period selector, summary
  cards, CSS bar charts for daily cost and success rate, and a per-spec
  cost table.
- **Branch GC counters.** `GET /v1/_admin/gc/metrics?period=` exposes
  `deleted_total`, `errors_total`, `skipped_total`,
  `dry_run_deleted_total`, `false_delete_total` — the counter surface
  used by the [branch-cleanup](./branch-cleanup.md) runbook for
  dashboards and the `false_delete_total > 0` SEV-2 alert.

## Interfaces

- `GET /v1/projects/{id}/metrics?period=` — returns daily cost, success
  rate, per-spec cost breakdown, and average stage durations for the
  requested window.
- `/metrics` route in `coder-admin` — dashboard view.
- Slack webhook — cost-threshold and success-rate alerts.
- Postgres `task_stage_durations` table — raw timing data for ad-hoc
  analysis.

## Dependencies

- Task orchestration — the stage transitions and task completions that
  feed every metric.
- Continuous deployment — deploy metadata used to correlate regressions
  with releases.
- Anthropic API `usage` field — source of token counts.
- Slack incoming webhook — alert delivery.

## Evolution

- `0018-observability-and-cost-tracking` — `task_stage_durations`
  (migration 0014), `/metrics` endpoint, Slack alerts with per-type
  rate limiting, admin dashboard with period selector and per-spec
  cost table. Design `0011`.
- `0023` — `gc_events` audit table (migration 0019) and
  `/v1/_admin/gc/metrics` counter surface for the branch-cleanup GC.

## Links

- Designs: —
- Related components: —

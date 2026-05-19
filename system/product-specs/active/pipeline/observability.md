---
id: observability
title: Observability
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-14
last_verified_at: 2026-05-14
summary: Per-task telemetry, token costs, and pipeline metrics.
served_by_designs: [observability-and-cost-tracking]
related_specs: [admin-panel, branch-cleanup, escalations, knowledge-freshness, self-healing, task-orchestration]
parent: pipeline-operations
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
- **Prompt-cache telemetry.** Every completed task records
  `cache_read_input_tokens` and `cache_creation_input_tokens` from the
  CLI envelope (migration 0022). `/metrics` returns per-role
  `cache_stats` with hit rate
  (`cache_read / (cache_read + regular_input)`), and the admin
  `/metrics` page renders the table + an aggregate `CacheCard` chip
  on the project overview. Capture always ran unconditionally; as of
  2026-04-19 the `PROMPT_CACHING_ENABLED` flag is on fleet-wide so
  coder-core prepends the shared per-run context block to every
  worker's system prompt, driving the claude CLI's internal
  `cache_control` markers and producing real hit rates.
- **Per-stage timing.** Orchestrator hooks write a row to
  `task_stage_durations` on every stage transition, enabling average
  duration per stage across arbitrary windows.
- **Project- and spec-level attribution.** Every metric row carries
  `project_id` and `spec_id`, so cost can be sliced per project, per
  spec, or per pipeline run.
- **Pipeline health.** Success rate over a rolling 24-hour window is
  derived from task outcomes. Fix-loop frequency falls out of
  `fix_attempts` aggregation.
- **Slack alerts.** Fire after every task completion when daily cost,
  success-rate, prompt-cache-hit, or per-project budget-soft
  thresholds are breached, with per-alert-type rate limiting (1/hour)
  so a bad day doesn't page twelve times. A separate nightly
  regression alert (spec 0032, `REGRESSION_ALERTS_ENABLED=true` as of
  2026-04-19) fires on per-role cost regressions > +25% versus the
  7-day baseline, deduped per (role, metric, day) via the
  `regression_events` table. The cache-hit-floor alert
  (`SLACK_CACHE_HIT_FLOOR`, default 0 = disabled) resolves each
  project's `prompt_caching_enabled` override before firing so a
  canary carve-out and a fleet-enabled project don't silence each
  other. The budget-soft alert
  (`alert_type=f"budget_soft_{project}_{yyyymm}"`) dedups per
  calendar month. Runbook:
  [`cache-hit-drop`](../../../runbooks/cache-hit-drop.md).
- **Admin dashboard.** `/metrics` route with a period selector, summary
  cards, CSS bar charts for daily cost and success rate, and a per-spec
  cost table.
- **Branch GC counters.** `GET /v1/_admin/gc/metrics?period=` exposes
  `deleted_total`, `errors_total`, `skipped_total`,
  `dry_run_deleted_total`, `false_delete_total` — the counter surface
  used by the [branch-cleanup](./branch-cleanup.md) runbook for
  dashboards and the `false_delete_total > 0` SEV-2 alert.
- **Auto-approval metrics.** `GET /metrics` exposes auto-approval
  telemetry per gate kind (spec / design / plan): auto-approve rate
  (% of artifacts that reached `applied` without manual intervention,
  fleet + per-project), undo rate (% of auto-approved artifacts undone
  before the window closed; fleet target < 5% in the first 30 days;
  a sustained > 10% is a signal the threshold is too low), mean
  wall-clock gate time split into manual vs. auto buckets (target auto
  bucket ≤ 11 minutes — 10-minute window + tick latency), and
  deferral-reason distribution (`score_below_threshold`,
  `risk_flag_present`, `historical_rate_below_95`,
  `insufficient_history`, `project_opted_out`). Downstream-impact
  comparison (developer-task success rate on chains seeded by
  auto-approved vs. manually-approved artifacts) derives from existing
  task-outcome rows joined via `auto_approvals.artifact_id`; a > 3pp
  drop in the auto-approved cohort is a rollback signal surfaced on
  the admin Metrics dashboard.
- **Reviewer finding counts.** On reviewer-task completion the
  orchestrator writes `security_finding_count` and
  `performance_finding_count` to task metadata. `/metrics` includes a
  `request_changes_by_kind` breakdown with `critical_security` as a
  distinct subcategory, tracking the fraction of `request-changes`
  verdicts driven by critical security findings versus AC/convention
  failures. The admin observability dashboard surfaces the
  `critical_security` subcategory as a labelled row on the
  verdict-breakdown table.

## Interfaces

- `GET /v1/projects/{id}/metrics?period=` — returns daily cost, success
  rate, per-spec cost breakdown, average stage durations, per-role
  `cache_stats` with hit rate, `request_changes_by_kind` breakdown
  (including `critical_security` subcategory), and (when
  `AUTO_APPROVE_ENABLED`) auto-approval telemetry for the requested
  window.
- `/metrics` route in `coder-admin` — dashboard view.
- Slack webhook — cost, success-rate, and cache-hit-floor alerts.
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

- 2026-04 — Initial ship (spec 0018): `task_stage_durations`,
  `/metrics`, Slack alerts, admin dashboard; plus `gc_events` for
  branch-cleanup (spec 0023).
- 2026-04-19 — Cost & cache observability week: prompt-cache
  telemetry, per-project token budgets, model-tier routing, cost-
  regression alerts (specs 0029, 0030, 0031, 0032).
- 2026-05 — Auto-approval and reviewer-finding telemetry
  (specs 0040, 0094): auto-approve / undo / wall-clock rate,
  security and performance finding counts per task, breakdown on
  the admin Metrics dashboard.

## Links

- Designs: [observability-and-cost-tracking](../../../designs/active/pipeline/observability-and-cost-tracking.md)
- Related components: [task-orchestration](./task-orchestration.md),
  [knowledge-freshness](../knowledge/knowledge-freshness.md),
  [branch-cleanup](./branch-cleanup.md),
  [self-healing](./self-healing.md), [escalations](./escalations.md),
  [admin-panel](../knowledge/admin-panel.md)

---
id: observability
title: Observability
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: [observability-and-cost-tracking]
related_specs: [knowledge-freshness]
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
  2026-04-19) fires on per-`(role, task_kind, model_id)` cost
  regressions exceeding a configurable threshold (default +25%;
  `architect` defaults to +35% via `regression_thresholds_per_role_kind`)
  versus the 7-day baseline, deduped per `(role, task_kind, model_id,
  metric, day_utc)` via `regression_events`. Suspect commit SHAs from
  both `coder-core` and `coder-system` are stamped on every alert
  (`coder_core.ops.regression_attribution`; degrades to NULL when
  credentials are absent). The cache-hit-floor alert
  (`SLACK_CACHE_HIT_FLOOR`, default 0 = disabled) resolves each
  project's `prompt_caching_enabled` override before firing so a
  canary carve-out and a fleet-enabled project don't silence each
  other. The budget-soft alert
  (`alert_type=f"budget_soft_{project}_{yyyymm}"`) dedups per
  calendar month. Runbook:
  [`cache-hit-drop`](../../runbooks/cache-hit-drop.md).
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
  rate, per-spec cost breakdown, average stage durations, and per-role
  `cache_stats` with hit rate for the requested window.
- `/metrics` route in `coder-admin` — dashboard view.
- Slack webhook — cost, success-rate, and cache-hit-floor alerts.
- Postgres `task_stage_durations` table — raw timing data for ad-hoc
  analysis.
- `GET /v1/_admin/regression/baseline?days=14` — per-`(role, model_id,
  day_utc)` daily medians + p95s from `stage_cost_baseline`; powers
  the admin baseline trendline.
- `GET /v1/_admin/regression/events?open_only=&limit=` — list regression
  events, open-first.
- `POST /v1/_admin/regression/events/{id}/acknowledge` — record actor +
  optional note; suppresses repeat Slack fires for the event's dedupe
  key.

## Dependencies

- Task orchestration — the stage transitions and task completions that
  feed every metric.
- Continuous deployment — deploy metadata used to correlate regressions
  with releases via commit-range attribution.
- Anthropic API `usage` field — source of token counts.
- Slack incoming webhook — alert delivery.

## Evolution

- `0018-observability-and-cost-tracking` — `task_stage_durations`
  (migration 0014), `/metrics` endpoint, Slack alerts with per-type
  rate limiting, admin dashboard with period selector and per-spec
  cost table. Design `0011`.
- `0023` — `gc_events` audit table (migration 0019) and
  `/v1/_admin/gc/metrics` counter surface for the branch-cleanup GC.
- `0029` — prompt-cache telemetry: migration 0022 adds
  `tasks.cache_read_input_tokens` + `cache_creation_input_tokens`,
  `/metrics` exposes per-role `cache_stats` with hit rate, the admin
  Metrics page renders a "Prompt Cache Efficiency" table and the
  ProjectDetail `CacheCard` aggregate chip. `SLACK_CACHE_HIT_FLOOR`
  alert fires when per-project rolling-24h hit ratio drops below the
  floor (gated on effective `prompt_caching_enabled` per project +
  3-task min sample). `PROMPT_CACHING_ENABLED=true` on revision
  `coder-core-00115-vhp` (2026-04-19) so cache_stats are driven by
  real cache_control markers, not a zero baseline.
- `0031` — per-project token budgets: migration 0035 adds
  `projects.budget_{soft,hard}_tokens` tri-state overrides.
  `resolve_budget_limits` is the single resolution point (per-project
  override → fleet default → 0 disables). Dispatcher hard-gate fails
  budget-exhausted tasks with `failure_kind="budget"`; soft-breach
  Slack alerts dedup per month via the yyyymm suffix on
  `alert_type`. `PATCH /v1/projects/{id}` accepts the override
  fields. Rollup table + admin override UI + monthly-reset cron
  deferred to phase 2.
- `0030` — model tier routing: migrations 0036/0037 add
  `projects.pin_top_tier` tri-state + `tasks.model_override`.
  `resolve_tier_model` in the dispatcher routes reviewer tasks to
  Haiku when `tier_routing_enabled=True` OR the project has
  `pin_top_tier=false`. `/metrics` `by_tier` rolls usage up by
  Haiku/Sonnet/Opus classification. `coder` project runs as the
  first canary with `pin_top_tier=false`.
- `0032` phase 1 — cost regression alerts: migration 0038 adds
  `regression_events` with dedupe on `(role, metric, day_utc)`.
  Nightly detector persists findings; acknowledge flow
  (`POST /v1/_admin/regression/events/{id}/acknowledge`) suppresses
  repeat Slack fires. `REGRESSION_ALERTS_ENABLED=true` as of 2026-04-19.
- `0032` phase 2 — granularity + attribution: migration 0059 widens
  `regression_events` with `task_kind`, `model_id`,
  `suspect_commit_range`; dedupe index widened to
  `(role, task_kind, model_id, metric, day_utc)`. `stage_cost_baseline`
  (migration 0040) pre-aggregates per-`(role, model_id, day_utc)` daily
  medians/p95s; `GET /v1/_admin/regression/baseline?days=14` exposes
  the trendline. Threshold granularity is per-`(role, task_kind)`:
  `regression_default_threshold` (fleet) +
  `regression_thresholds_per_role_kind` map, resolved cell → role →
  fleet; `architect` defaults to 0.35. Commit attribution
  (`coder_core.ops.regression_attribution`) queries both repos in one
  nightly pass; degrades to NULL when GitHub credentials are absent.
  Phase-1 rows coexist (null `task_kind`/`model_id` are distinct dedupe
  values).

## Links

- Designs: [observability-and-cost-tracking](../../designs/active/observability-and-cost-tracking.md)
- Related components: [task-orchestration](./task-orchestration.md),
  [knowledge-freshness](./knowledge-freshness.md),
  [branch-cleanup](./branch-cleanup.md),
  [self-healing](./self-healing.md), [escalations](./escalations.md),
  [admin-panel](./admin-panel.md)

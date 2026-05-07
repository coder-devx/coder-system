---
id: observability-and-cost-tracking
title: Observability and Cost Tracking
type: design
status: active
owner: ro
created: 2026-04-12
updated: 2026-04-19
last_verified_at: 2026-04-19
summary: Telemetry, cost accounting, and alerts for the running pipeline.
implements_specs: [observability]
decided_by: []
related_designs: [system-overview, audit-log]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin, coder-system]
parent: pipeline-operations
---

# Observability and Cost Tracking

## What it is

This component gives Coder visibility into what it costs to run and
how healthy the pipeline is. It aggregates per-task token spend,
per-stage wall-clock durations, and success/failure rates into an API
and a dashboard, and fires Slack alerts when cost or success-rate
thresholds are breached. Token counts are already captured per task on
`TaskRow`; this design adds a denormalized stage-duration table, an
aggregation API, the alert check, and the admin panel `/metrics`
view.

## Architecture

```mermaid
flowchart TB
  subgraph core [coder-core]
    orchestrator[Orchestrator]
    dispatcher[Dispatcher]
    durations[task_stage_durations]
    metrics_api["GET /v1/projects/{id}/metrics"]
    alerts[Slack alert check]
  end

  subgraph admin [coder-admin]
    dashboard[/metrics dashboard]
  end

  orchestrator -->|record duration| durations
  dispatcher -->|token counts| tasks[(tasks table)]
  metrics_api --> durations
  metrics_api --> tasks
  dashboard --> metrics_api
  alerts --> slack[Slack webhook]
```

### Parts

- **Migration 0014: `task_stage_durations`** — denormalized table:
  `id`, `task_id`, `project_id`, `stage`, `started_at`, `ended_at`
  (nullable while in-progress), `duration_seconds` (computed on
  end). Index on `(project_id, started_at)` for time-range queries.
- **Orchestrator hook** — on every stage transition, close the
  previous row (`ended_at` + duration) and open the next one. One
  UPDATE + one INSERT per transition.
- **Metrics API** (`api/metrics.py`) —
  `GET /v1/projects/{id}/metrics?period=1d|7d|30d` returns
  `daily_cost`, `success_rate`, `per_spec_cost`,
  `stage_durations_avg`.
- **Slack alerts** (`integrations/slack.py`) — simple webhook POST.
  Checked after each task completes. Two env-var thresholds:
  `SLACK_COST_ALERT_THRESHOLD` (daily token cost),
  `SLACK_SUCCESS_RATE_THRESHOLD` (rolling 24h, default 0.8). In-memory
  rate-limit: one alert per threshold per hour.
- **Admin `/metrics` dashboard** — Recharts-based. Daily cost bar
  chart, success-rate line chart, per-spec cost table, average
  stage durations.

### Data flow

1. A worker completes; the dispatcher writes `cost_input_tokens`
   and `cost_output_tokens` to the task row (existing behavior,
   via `parse_claude_json_envelope()`).
2. On each stage transition, the orchestrator closes the current
   duration row and opens a new one in `task_stage_durations`.
3. When the dispatcher finishes a task, it calls `_check_alerts()`,
   which queries rolling 24h stats and fires the Slack webhook if a
   threshold is breached and rate-limit permits.
4. The admin dashboard polls `GET /metrics?period=…`; the API
   aggregates over `tasks` + `task_stage_durations` for the
   requested window and returns JSON.

### Invariants

- PM, TM, and Architect tasks don't flow through orchestrated
  stages; they get a single `running` duration from `started_at` to
  `finished_at` so they still appear in metrics.
- Missing Slack webhook config = alerts silently skip (graceful
  degradation, matching the CD pattern).
- Empty period = zeroed metrics, never an error.
- Alert rate-limits live in-memory; a restart resets them
  (acceptable for v1).
- Metrics are batch-aggregated on read, not streamed.

## Interfaces

- `GET /v1/projects/{id}/metrics?period=<1d|7d|30d>` →
  `{daily_cost, success_rate, per_spec_cost, stage_durations_avg,
  cache_stats, daily_cache_stats, …}`. The `daily_cache_stats` field
  (one entry per (date × role) over the requested window, with
  `cache_read_tokens`, `cache_creation_tokens`, `total_input_tokens`,
  `cache_hit_rate`, `task_count`) backs the admin "Daily Cache Trend"
  grid; computed at request time from the `tasks` table on the
  existing `(project_id, finished_at)` index. `cache_hit_rate` is
  null when `total_input_tokens = 0`.
- Slack: outbound webhook on threshold breach.
- Admin panel route: `/metrics`.
- Env vars: `SLACK_COST_ALERT_THRESHOLD`,
  `SLACK_SUCCESS_RATE_THRESHOLD`, `SLACK_WEBHOOK_URL`.

## Evolution

- Token capture predates this component (already on `TaskRow` via
  `parse_claude_json_envelope()`).
- `0011-observability-and-cost-tracking` (spec 0018) — added
  migration 0014, the orchestrator duration hook, the metrics API,
  Slack alerts, and the admin dashboard in a single deploy cycle.
- `0037` — audit log as an adjacent operator surface (shipped
  2026-04-19): the audit log sits alongside `/metrics` and the
  Slack alert stream as the third operator surface. Distinction:
  observability answers "is the pipeline healthy?" and "what did
  it cost?"; the audit log answers "who mutated what, when?".
  No coupling on the write side; both read through the same
  structured-log feed but write to separate tables
  (`task_stage_durations`, `regression_events`, `gc_events` here;
  `audit_events` there). See [audit-log](./audit-log.md).
- `0065` — per-role daily cache hit rate trend (shipped
  2026-05-04): `daily_cache_stats` field on the metrics endpoint
  exposes a (date × role) breakdown so operators can spot the day
  a cache-hit-rate regression landed instead of seeing only the
  period aggregate. Backed by an at-request-time SQL groupby; no
  new table. The admin panel renders a colour-coded grid with a
  ▼ marker on day-over-day drops ≥ 30pp.
- `0063` — compliance-gate retry visibility (shipped 2026-05-04):
  new `compliance_retry_events` table (migration 0060) records
  one row per gate invocation (gate_role, attempt_count, outcome,
  failure_kind). New `GET /v1/projects/{id}/compliance-metrics?period`
  returns a rolling-window rollup keyed by gate_role. Admin panel
  adds a ComplianceMetrics page (per-role gate-retry rate + recent
  failures table) so operators can spot a sudden surge in compliance
  retries — typically a worker-prompt regression that's burning
  budget on schema fixes. Behind `VITE_COMPLIANCE_METRICS_ENABLED`.

## Links

- Specs: [`0018`](../../product-specs/wip/0018-observability-and-cost-tracking.md)
- Designs: system-overview
- Services: `coder-core`, `coder-admin`

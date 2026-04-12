---
id: "0018"
title: Observability and cost tracking
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-12
deprecated_at:
reason:
served_by_designs: ["0011"]
related_specs: ["0010", "0011"]
---

# Observability and cost tracking

**Phase:** Later — full self-hosting
**Progress:** 7 / 7 acceptance criteria ✅

## Problem

There is no visibility into how much Coder costs to run or how healthy
the pipeline is. Token spend, compute time, and API call costs are
opaque. Pipeline failures and stage durations are not tracked over time.
Without this data, it is impossible to budget, detect regressions, or
identify which specs are expensive to implement.

## Users / personas

- **Human operator** — needs to know what Coder costs per project, per
  spec, and in total. Needs to be alerted when health degrades.
- **Future Consultant worker** — needs pipeline metrics to observe and
  recommend optimizations.

## Goals

- Per-project cost attribution: Anthropic token spend, compute time,
  API call counts.
- Pipeline health metrics: success rate, stage durations, fix-loop
  frequency.
- Threshold alerts via Slack when costs or failure rates exceed limits.
- Dashboard visible in the admin panel.

## Non-goals

- Real-time streaming metrics (batch/periodic aggregation is fine for v1).
- Cost attribution at the individual AC level.
- Integration with external observability platforms (Datadog, Grafana)
  in v1.

## Scope

- A `task_metrics` table capturing per-task: token counts (input/output),
  stage durations, fix attempts, outcome.
- Aggregation views: per-project daily cost, per-spec cost, pipeline
  success rate over rolling windows.
- Cron job aggregating metrics daily.
- Slack alert when daily cost exceeds configured threshold or when
  success rate drops below threshold.
- New `/metrics` dashboard route in `coder-admin` showing cost and
  health charts.

## Acceptance criteria

- [x] AC1: Token spend (input + output) is recorded per task when a
  worker completes.
- [x] AC2: Stage durations are recorded for every stage transition on
  every task.
- [x] AC3: Per-project daily cost is aggregated and queryable via the
  API.
- [x] AC4: A `/metrics` dashboard in the admin panel shows cost and
  pipeline health charts.
- [x] AC5: Slack alerts fire when daily cost exceeds the configured
  threshold.
- [x] AC6: Slack alerts fire when the pipeline success rate drops below
  the configured threshold over a rolling 24-hour window.
- [x] AC7: All metrics are attributed to the originating project and
  spec, enabling per-spec cost comparison.

## Open questions

- How do we capture Anthropic token counts? From the API response
  `usage` field in each worker call, aggregated in the dispatcher.
- Where is the alert threshold configured? Env var per project, or a
  settings table in Postgres?
- Should the dashboard use server-side chart rendering or a frontend
  charting library?

## Links

- Related specs: [`0010`](../active/0010-task-orchestration-v1.md), [`0011`](../active/0011-continuous-deployment.md)

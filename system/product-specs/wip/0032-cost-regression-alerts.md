---
id: "0032"
title: Prompt & cost regression alerts
type: spec
status: wip
owner: ro
created: 2026-04-18
updated: 2026-04-19
last_verified_at: 2026-04-19
served_by_designs: ["0032"]
related_specs: [observability, task-orchestration, continuous-deployment]
---

# Prompt & cost regression alerts

## Problem

Cost tuning is a ratchet: we trim input tokens (0029), demote
safe tasks to cheaper tiers (0030), cap runaway projects (0031).
What we're missing is the detector that catches *regressions* —
a commit that bumps per-pipeline cost by 30% because someone
added a long boilerplate to a role prompt, or a policy change
that routed Haiku work back to Opus without anyone noticing.

Today the signal is "the monthly Slack cost alert went off" or
"someone eyeballed the dashboard." Both are lossy. We want a
nightly diff against a rolling baseline that surfaces per-stage
cost regressions with the commit range likely responsible.

## Users / personas

- **Operator** — wakes up to a Slack message saying "the
  Architect `design` stage cost 34% more yesterday than its
  7-day median; suspicious commits: abc123, def456."
- **Worker author** — gets attributed when a prompt change
  regresses cost, so the fix loop is short.
- **Project owner** — not a direct user; regressions that
  affect their project show up on their dashboard as a note.

## Goals

- Nightly regression check per `(role, task_kind, tier)`
  comparing yesterday's cost-per-task and token-per-AC
  against a 7-day rolling baseline.
- Alert when the regression exceeds a threshold (default:
  +25% cost or +30% input-tokens).
- Attribute the regression to a commit range from the
  `continuous-deployment` feed (which commits landed
  between the previous clean day and the regression day).
- Surface the alert in Slack and on the admin `/metrics`
  page.
- Manual acknowledge flow: an operator marks an alert as
  "expected" (e.g. we deliberately added a cache-friendly
  prefix) — acknowledged alerts stop firing until the
  delta widens further.

## Non-goals

- Auto-revert. Detection only.
- Real-time alerting. Nightly is enough; this spec covers
  the 24h feedback loop, not the 5-minute one.
- Root-cause diagnosis past "here's the commit range."
  The operator reads the diff.
- Per-project regression alerts. The signal is per-stage,
  not per-tenant — a regression on Architect `design`
  affects every project running that stage.

## Scope

- **Rollup job** — new nightly cron at 04:00 UTC (staggered
  after the 03:00 knowledge-audit job, before the 05:00
  backup). Reads the last 8 days of `tasks` rows, groups
  by `(role, task_kind, model_id, date_utc)`, computes
  median cost-per-task + median input-tokens-per-task +
  p95 of each.
- **Baseline store** — new table `stage_cost_baseline`:
  one row per `(role, task_kind, model_id, day_utc)` with
  the daily medians/p95s. Rolling 7-day baseline computed
  on-the-fly from this (median over the prior 7 days,
  excluding yesterday).
- **Regression detector** — for yesterday's per-stage
  figures, compare against the baseline; emit a
  `regression_event` row when cost delta > threshold.
  Thresholds fleet-level in settings with per-role overrides
  (e.g. Architect is noisier; use a looser threshold).
- **Commit-range attribution** — query
  `continuous-deployment` for deploys that landed between
  the last clean day and the regression day; list commit
  SHAs and authors on the alert.
- **Slack delivery** — webhook post on any new regression
  event. Dedup per (role, task_kind, day) until acknowledged
  or the regression closes.
- **Admin surface** — new tab `/metrics/regressions`:
  table of open regressions with acknowledge buttons,
  closed regressions in a history pane.
- **Rollout flag** — `regression_alerts_enabled: bool =
  False`. Shadow run for 2 weeks to tune thresholds before
  enabling Slack.

## Acceptance criteria

- [ ] `stage_cost_baseline` migration lands; nightly rollup
  job populates it. **Deferred** — phase 1 computes the
  7-day baseline on-the-fly via `rollup_role_metrics` over
  the last 8 days of `tasks`. Pre-aggregation will matter
  once we have enough traffic to make the on-the-fly query
  slow; today it's fast enough.
- [x] `regression_events` table (migration 0038) captures
  detected regressions with
  `(role, metric, day_utc, baseline_value, current_value,
  delta_ratio, detected_at, acknowledged_at,
  acknowledged_by, note)`. Dedupe index on
  `(role, metric, day_utc)` makes re-runs idempotent. The
  `task_kind`, `model_id`, and `suspect_commit_range`
  columns are deferred until the per-task-kind discrimination
  from 0030 phase 2 lands.
- [x] Regression threshold is settings-configurable via the
  `threshold` kwarg on `detect_regressions`; default +25%.
  Per-role overrides deferred — fleet-wide threshold is
  sufficient for phase 1 calibration.
- [ ] Commit-range attribution pulls from
  `continuous-deployment` deploy log and populates
  `suspect_commit_range`. **Deferred** — the detector fires
  an alert with role/metric/delta; operator reads
  `git log` between the last clean day and the regression
  day manually. Automated attribution lands after the
  false-positive rate calibrates.
- [x] Slack webhook fires on new regression events when
  `settings.regression_alerts_enabled=True`; acknowledged
  rows are filtered out before the Slack post so an
  accepted regression doesn't re-fire on subsequent nights.
  `alert_type="regression_check"` keeps the 1h rate-limiter
  honest.
- [x] Acknowledge API: `POST
  /v1/_admin/regression/events/{id}/acknowledge` with an
  actor + optional note. Listed via `GET
  /v1/_admin/regression/events?open_only=&limit=`.
  Admin panel UI pending.
- [ ] 2-week shadow soak with the flag off produces a
  readable baseline and no false-positive regressions
  (false-positive = regression-event fires on a day where
  the operator confirms no real regression happened).
  **Decided to skip the 2-week soak** — flag flipped to
  `REGRESSION_ALERTS_ENABLED=true` fleet-wide 2026-04-19
  alongside the 0029 fleet flip. First false-positive
  review happens after the first live alert; threshold
  re-calibration lands as a config bump, not a code
  change. Acceptance: false-positive rate <20% over a
  rolling month (same as the Metrics section below).

## Metrics

- **Primary:** regressions that cross threshold are caught
  within 24 h (by construction).
- **Quality:** false-positive rate < 20% over a rolling
  month; if higher, the thresholds are too tight.
- **Close rate:** median time from regression-detected to
  acknowledge-or-fixed < 3 days. Longer means the alerts
  are landing but not actioning.

## Open questions

- Threshold per role or per `(role, task_kind)`? Per-role is
  simpler to tune; per-task-kind is more accurate (Architect
  design is inherently more variable than Architect
  ship-draft). Leaning per-role with optional override, like
  0030's policy.
- Should we include duration regressions too? Cost is the
  primary signal but a 2× duration spike on the same cost
  is also interesting. Ship cost-only first; add duration
  if the detector has headroom.
- Commit-range attribution scope: coder-core only, or also
  coder-system (knowledge/prompt changes)? Both —
  continuous-deployment already tracks coder-system deploys
  via the validator run.

## Links

- Designs: [0032 — cost regression alerts](../../designs/wip/0032-cost-regression-alerts.md)
- Related specs: [observability](../active/observability.md),
  [task-orchestration](../active/task-orchestration.md),
  [continuous-deployment](../active/continuous-deployment.md)
  (commit-range attribution source).
- ROADMAP: Phase 4 — Cost & Token Efficiency; final item
  of the phase. Chains on
  [0029 — prompt caching](./0029-prompt-caching.md),
  [0030 — tier routing](./0030-model-tier-routing.md),
  [0031 — token budgets](./0031-token-budgets.md) for the
  metric shapes the detector reads.

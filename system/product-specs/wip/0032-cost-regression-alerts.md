---
id: "0032"
title: Prompt & cost regression alerts
type: spec
status: wip
owner: ro
created: 2026-04-18
updated: 2026-04-29
last_verified_at: 2026-04-29
served_by_designs: ["0032"]
related_specs: [observability, task-orchestration, continuous-deployment]
parent: pipeline-operations
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

- [x] `stage_cost_baseline` migration (0040) lands; the
  nightly regression cron calls
  `upsert_stage_baseline_for_day` to populate yesterday's row
  per `(role, model_id="", day_utc)`. Dedupe index on
  `(role, model_id, day_utc)` keeps re-runs idempotent. The
  7-day baseline detector still runs on-the-fly from `tasks`
  for phase 1; the table is the read path for the admin
  trend-line and the pre-aggregation step-up once traffic
  warrants swapping the detector to read from it. Rows
  returned by `GET /v1/_admin/regression/baseline?days=14`.
- [x] `regression_events` table (migration 0038) captures
  detected regressions with
  `(role, metric, day_utc, baseline_value, current_value,
  delta_ratio, detected_at, acknowledged_at,
  acknowledged_by, note)`. Phase 2 (migration 0059) adds
  `task_kind`, `model_id`, and `suspect_commit_range`
  columns and widens the dedupe index to
  `(role, task_kind, model_id, metric, day_utc)` so a
  regression on `architect/design/sonnet` doesn't dedupe
  with `architect/knowledge_audit/haiku` for the same UTC
  day. Phase-1 rows persist with both qualifiers null and
  coexist on the same day as phase-2 rows because null is a
  distinct dedupe value.
- [x] Regression threshold is settings-configurable via
  `regression_default_threshold` (fleet-wide) and
  `regression_thresholds_per_role_kind` (per-(role, task_kind)
  overrides; lookup order cell → role → fleet default).
  Default ships `architect: 0.35` to absorb the noisier
  cost shape; the detector echoes the resolved threshold
  back on the finding so the alert + audit row record what
  bar tripped.
- [x] Commit-range attribution pulls from
  `continuous-deployment` deploys (push-to-main on
  `coder-core` + `coder-system`) and populates
  `suspect_commit_range` on every persisted event.
  Implemented in `coder_core.ops.regression_attribution` —
  the cron queries the GitHub commits between the
  current-window start and end for both repos in one pass
  per nightly run, JSON-encodes the SHA / author / message
  list, and stamps it on every finding from the same UTC
  day. Graceful degrade: a server without GitHub credentials
  installed (or a test path) sets the column to NULL and
  the admin tab falls back to "operator reads `git log`."
- [x] Slack webhook fires on new regression events when
  `settings.regression_alerts_enabled=True`; acknowledged
  rows are filtered out before the Slack post so an
  accepted regression doesn't re-fire on subsequent nights.
  `alert_type="regression_check"` keeps the 1h rate-limiter
  honest.
- [x] Acknowledge API: `POST
  /v1/_admin/regression/events/{id}/acknowledge` with an
  actor + optional note. Listed via `GET
  /v1/_admin/regression/events?open_only=&limit=`. Admin
  panel's `/metrics/regressions` tab renders the open-first
  event list with per-row acknowledge button + note input;
  the same tab shows the 14-day baseline trendline per role
  (median + p95 sparkline sourced from `stage_cost_baseline`).
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

## Decisions

Resolved 2026-04-27 ahead of phase-2 increment dispatch.

- **Threshold granularity — per-(role, task_kind).** Aligns
  with 0030's `(role, task_kind)` enum; gives the detector
  enough resolution to distinguish "architect design" from
  "architect ship-draft" (inherently different cost shapes).
  More tuning surface than per-role, but the accuracy gain is
  worth it.
- **Duration regressions — cost-only in v1.** Cost is the
  primary signal. A 2× duration spike on the same cost is
  interesting but secondary; add duration as a follow-up if
  the detector has headroom and the cost-only signal proves
  insufficient.
- **Commit-range attribution scope — coder-core +
  coder-system.** Both. Continuous-deployment already tracks
  coder-system deploys via the validator run, so the join is
  cheap; knowledge/prompt changes that drive cost regressions
  would be invisible if scoped to coder-core alone.

## Open questions

_None — all resolved. See Decisions above._

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

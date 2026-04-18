---
id: "0032"
title: Prompt & cost regression alerts
type: spec
status: wip
owner: ro
created: 2026-04-18
updated: 2026-04-18
last_verified_at: 2026-04-18
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
  job populates it.
- [ ] `regression_event` table captures detected
  regressions with `(role, task_kind, model_id, day_utc,
  baseline_median, current_median, delta_pct,
  suspect_commit_range)`.
- [ ] Regression threshold is settings-configurable with
  per-role overrides; default +25% cost / +30% input-tokens.
- [ ] Commit-range attribution pulls from
  `continuous-deployment` deploy log and populates
  `suspect_commit_range`.
- [ ] Slack webhook fires on new regression events when
  `regression_alerts_enabled=True`; deduped per (role,
  task_kind, day) via a dedupe key on the event row.
- [ ] Admin panel `/metrics/regressions` tab lists open
  and historical regressions; acknowledge button sets
  `acknowledged_at` + `acknowledged_by` on the row.
- [ ] 2-week shadow soak with the flag off produces a
  readable baseline and no false-positive regressions
  (false-positive = regression-event fires on a day where
  the operator confirms no real regression happened).

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

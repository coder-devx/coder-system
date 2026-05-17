---
id: '0095'
title: Cache-hit and cost-regression observability is wrong or absent
type: spec
status: wip
owner: ro
created: '2026-05-14'
updated: '2026-05-14'
last_verified_at: '2026-05-14'
progress: '2 / 3 acceptance criteria'
deprecated_at: null
reason: null
served_by_designs:
- observability-and-cost-tracking
- prompt-caching-architecture
- cost-regression-alerts
related_specs:
- observability
parent: pipeline-operations
---

# Cache-hit and cost-regression observability is wrong or absent

**Phase:** wip
**Progress:** 2 / 3 acceptance criteria

> **ID-renumber note:** This spec was originally drafted as 0094, but
> spec 0094 was shipped to active earlier the same day (reviewer
> security/performance analysis — see commit `ecedd78`). The first two
> shipped PRs reference the old ID in their commit messages and code
> comments: [coder-core#299](https://github.com/coder-devx/coder-core/pull/299)
> (closes AC1) commit message reads "spec 0094 AC1", and
> [coder-core#300](https://github.com/coder-devx/coder-core/pull/300)
> (closes AC3) carries "spec 0094 AC3" in both its commit message and
> in a code comment in `_resolve_model`. Both should be read as
> referring to **this spec (0095)**; the shipped 0094 is the reviewer
> spec.

## Problem

Three independent gaps in the observability spec 0029/0032 were uncovered by a live Cloud SQL analysis of tasks created in window `2026-05-07` → `2026-05-13` (220 tasks total, 92.8M input tokens seen, 85.7M of them cache_read). Together they mean the system reports cache health and cost regressions with values the operator cannot trust or act on, even though the underlying machinery is shipped and `PROMPT_CACHING_ENABLED=true`.

### 1. `cache_hit_rate` formula divides by the wrong denominator

`coder_core.metrics.service.aggregate_metrics` and `get_daily_cache_stats` compute hit-rate as `sum(cache_read_input_tokens) / sum(cost_input_tokens)`. Anthropic's `usage.input_tokens` reports only the **uncached** portion of input — cached bytes are separately reported in `cache_read_input_tokens` and `cache_creation_input_tokens`. Dividing cache-read by uncached-only produces a ratio that explodes as caching works: last week's fleet aggregate evaluates to **162,535 %**.

Consequences:
- The admin "Daily Cache Trend" grid and the per-role cache_hit_rate column on `/metrics` render unusable numbers.
- The `slack_cache_hit_floor` setting (designed to fire below 30 %) cannot be enabled because real values evaluate to >1000 %, so the floor would never trigger and a cache regression would not page anyone.
- The runbook [`cache-hit-drop`](../../runbooks/cache-hit-drop.md) instructs operators to compare against the floor — that path is currently dead.

Correct formula: `cache_read_input_tokens / (cost_input_tokens + cache_read_input_tokens + cache_creation_input_tokens)`.

### 2. Nightly regression cron has never persisted a baseline

The `stage_cost_baseline` table contains **zero rows** (table-wide, not just last week). `regression_events` is also empty. Either the Cloud Scheduler trigger that calls `coder_core.ops.regression_cron.run_regression_check` is not wired, the `REGRESSION_ALERTS_ENABLED` env var is being read as false at runtime, or the cron is firing and exception-ing silently.

Effect: spec 0032's "we catch a cost regression next morning" guarantee is not actually live. Operators have no automated signal that a prompt rewrite or deploy moved per-stage cost up.

### 3. `tasks.model` is NULL on team-manager and on cancelled / failed dev tasks

54 of 220 tasks last week (24.5 %) carry `model = NULL`, including **all 15 team-manager dispatches** and 17 cancelled developer tasks. Per `coder_core.domain.task.TaskRow:268` the column is supposed to be stamped at dispatch and never mutated. The team-manager worker's dispatch path is missing the stamp.

Effect: per-(role, model) splits in the metrics service and the regression detector's `(role, task_kind, model_id)` grouping (`rollup_role_metrics`, `RoleModelStats`, `TierStats`) silently exclude or mis-bucket those rows. Tier-mix decisions cannot account for team-manager at all.

## Users / personas

- **Operator reading `/metrics`.** Today they see a cache_hit_rate column that is mathematically wrong and an empty regressions tab.
- **Operator triaging a cache regression.** Cannot rely on the Slack floor; must manually run the corrected query.
- **Anyone tuning tier routing (spec 0030).** Per-model rollups exclude 25 % of traffic.

## Goals

- `/metrics` `cache_stats[*].cache_hit_rate` and `daily_cache_stats[*].cache_hit_rate` return values in `[0.0, 1.0]` and match the design's "fraction of total input tokens served from cache" definition.
- `slack_cache_hit_floor=0.30` can be enabled and fires only on real drops, not on every request.
- `stage_cost_baseline` accumulates one row per active (role, model_id) per UTC day, starting the day the cron is verified live. `regression_events` accumulates a row whenever the detector finds a breach.
- `tasks.model` is non-NULL for every team-manager dispatch made after the fix lands.

## Non-goals

- Backfilling historical `tasks.model` rows. Forward-looking only.
- Re-tuning regression thresholds — that's a separate calibration once data lands.
- Adding new metrics. This spec restores the correctness of metrics that already exist.

## Scope

Three independent surfaces; ship in any order.

1. **Formula fix** — `coder_core/metrics/service.py` (`aggregate_metrics` daily-cache + per-role rollups, `get_daily_cache_stats`) and the cache-floor alert in `coder_core/workers/dispatcher.py:2611`. Update unit tests that assert the wrong shape. No migration, no admin-FE change (chart consumes the corrected field directly).
2. **Regression cron diagnosis** — read 7 d of Cloud Logging filtered on the trigger endpoint to determine cause; either flip a config, fix wiring, or file a follow-up bug if the failure is in the rollup code itself.
3. **TM model stamp** — locate the dispatch path in `coder_core/workers/team_manager.py` + `coder_core/workers/dispatcher.py` that skips setting `TaskRow.model`. One-line fix. Add a regression test that a freshly-dispatched TM task has non-NULL model.

## Acceptance criteria

1. **AC1 — formula fix.** ✅ **Closed 2026-05-14** by [coder-core#299](https://github.com/coder-devx/coder-core/pull/299) (merged `c71e69c`, CD-deployed). `aggregate_metrics`, `get_daily_cache_stats`, and the dispatcher cache-floor alert now divide by `cost_input + cache_read + cache_creation`. Regression test `test_cache_hit_rate_bounded_when_caching_works` asserts the ratio stays in `[0, 1]` with realistic prod ratios. Spot-check after deploy: `slack_cache_hit_floor` can now be raised from 0.0 to ~0.3 per the design.

2. **AC2 — regression cron diagnosis filed.** Diagnosed 2026-05-14; ✅ documented, ❌ not yet provisioned. **Root cause**: there is no Cloud Scheduler job that invokes `POST /v1/_admin/regression/check`. Cloud Scheduler currently runs `coder-core-self-heal-tick`, `coder-core-auto-approve-tick`, `coder-core-spec-coord-tick`, `coder-core-rotate-secrets`, `knowledge-audit-nightly`, `coder-core-founder-tick-*`, `coder-core-studio-metrics-tick`, `coder-core-dispatcher-rekick-tick` — none of these calls the regression endpoint. The only live callers are per-project admin dashboard GETs (`GET /v1/projects/{id}/regressions`) which pass `skip_slack=True` and intentionally bypass persistence (the comment in `regression_cron.run_regression_check:344-353` says project-scoped reads "shouldn't create global audit rows"). Hence `stage_cost_baseline` and `regression_events` are both empty fleet-wide despite the detector reporting findings on `2026-05-10` and `2026-05-13`. **Fix plan**: provision a new Cloud Scheduler job (HTTP-target pattern, matching `coder-agent-self-improve`) that fires once a night against the admin endpoint with OIDC auth, OR add a `coder-core-regression-tick` Cloud Run Job alongside the other ticks. Belongs in its own wip spec because it's an infra provisioning change with a runbook, not a code patch — operator should dispatch it as a developer task once spec is written.

3. **AC3 — TM model stamp.** 🟡 **In flight** as [coder-core#300](https://github.com/coder-devx/coder-core/pull/300) (pushed 2026-05-14, awaiting CI). One-line fix in `coder_core/workers/dispatcher.py:_resolve_model`: the role-default dict was keyed on `"team_manager"` (underscore) but every other dispatcher path uses `"team-manager"` (hyphen). Added the hyphenated key, kept the underscored one defensively (same dual-key pattern as `_low_tier_model_for`). Regression test asserts `_resolve_model` returns a non-None model for every known role plus the underscore variant, and honours `model_override`.

## Risks

- **Formula fix changes admin chart values dramatically.** Old values were nonsense, new values will be in `[0, 1]`. The chart legend may need a label change but the field name stays the same.
- **Diagnosing the cron may surface a deeper issue** (e.g. Cloud Scheduler trigger never created during a deploy). Scope this spec to triage + decision; the fix may need its own spec.

## Out of scope (intentionally deferred)

- Output-token verbosity audit (separate spec).
- Re-prompt cache-creation overhead investigation (separate spec).
- Per-task_kind baseline widening — flagged in `regression_cron.py:24-27` as "left for after the phase-2 detector calibrates"; still appropriate to defer.

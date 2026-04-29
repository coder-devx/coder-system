---
id: "0032"
title: Prompt & cost regression alerts
type: design
status: wip
owner: ro
created: 2026-04-18
updated: 2026-04-29
last_verified_at: 2026-04-29
implements_specs: ["0032"]
decided_by: []
related_designs: [observability-and-cost-tracking, worker-communication]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin]
---

# Prompt & cost regression alerts

## Context

After 0029 / 0030 / 0031, we've got cost trimming, tier routing,
and budget enforcement — three mechanisms pushing per-task cost
down. What none of them detects is a *regression*: a change that
moves cost up for non-obvious reasons. Today the feedback loop is
"someone notices next month." We want nightly detection with
commit-range attribution so fixes land same-week.

Mechanism is simple: a nightly job computes per-stage daily
medians, compares yesterday against a 7-day rolling baseline,
files a `regression_event` row when the delta exceeds a threshold,
pulls commit SHAs from the deploy log for attribution, and
notifies Slack.

## Goals / non-goals

**Goals**
- Nightly detection keyed on `(role, task_kind, model_id)`.
- Rolling 7-day baseline stored in a rollup table (not
  recomputed from raw `tasks` each night).
- Threshold-based filtering with per-role overrides.
- Commit-range attribution from `continuous-deployment`.
- Admin panel surface with acknowledge flow.
- Shadow-soak capability: capture events with flag off for
  threshold tuning before enabling Slack.

**Non-goals**
- Real-time detection.
- Auto-revert.
- ML-based root-cause analysis. The operator reads the diff.
- Per-project alerting (signal is per-stage, fleet-wide).

## Design

```mermaid
flowchart TB
  subgraph core [coder-core]
    tasks[(tasks)]
    cron[nightly 04:00 UTC]
    baseline[(stage_cost_baseline)]
    detector[regression detector]
    events[(regression_event)]
    deploys[(deploy_log)]
    slack[Slack webhook]
    api[/regressions API]
    ack[POST /regressions/:id/ack]
  end

  subgraph admin [coder-admin]
    tab["/metrics/regressions tab"]
    ackbtn[acknowledge button]
  end

  cron --> tasks
  cron -->|upsert daily rollup| baseline
  cron --> detector
  detector -->|read prior-7d median| baseline
  detector -->|read yesterday median| baseline
  detector -->|read commits between last_clean_day and yesterday| deploys
  detector -->|write regression rows| events
  detector -->|fire if enabled + new event| slack
  api --> events
  tab --> api
  ackbtn --> ack
  ack --> events
```

### Parts

- **Migration: `stage_cost_baseline`** — one row per
  `(role, task_kind, model_id, day_utc)`. Columns:
  - `role TEXT NOT NULL`
  - `task_kind TEXT NOT NULL`
  - `model_id TEXT NOT NULL`
  - `day_utc DATE NOT NULL`
  - `task_count INT NOT NULL`
  - `median_cost_tokens BIGINT NOT NULL`
  - `p95_cost_tokens BIGINT NOT NULL`
  - `median_input_tokens BIGINT NOT NULL`
  - `median_output_tokens BIGINT NOT NULL`
  - `PRIMARY KEY (role, task_kind, model_id, day_utc)`
  Populated by the nightly job; rolling baselines
  (7d median-of-medians) computed on-the-fly.
- **Migration: `regression_event`** — one row per detected
  regression. Columns:
  - `id UUID PRIMARY KEY`
  - `role TEXT NOT NULL`, `task_kind TEXT NOT NULL`,
    `model_id TEXT NOT NULL`, `day_utc DATE NOT NULL`
  - `metric TEXT NOT NULL` (enum: `cost` | `input_tokens`)
  - `baseline_value BIGINT NOT NULL`
  - `current_value BIGINT NOT NULL`
  - `delta_pct REAL NOT NULL`
  - `threshold_pct REAL NOT NULL` (what tripped)
  - `suspect_commit_shas TEXT[]`
  - `suspect_commit_authors TEXT[]`
  - `acknowledged_at TIMESTAMPTZ NULL`
  - `acknowledged_by TEXT NULL`
  - `ack_reason TEXT NULL`
  - `closed_at TIMESTAMPTZ NULL` (auto-close when
    subsequent days return under threshold)
  - `dedupe_key TEXT NOT NULL UNIQUE` —
    `{role}/{task_kind}/{model_id}/{day_utc}/{metric}`
    prevents the same alert firing twice.
- **Nightly rollup job** (`coder_core.workers.cost_rollup`,
  new) — APScheduler cron at `04 00 * * *` UTC. Steps:
  1. Compute yesterday's daily rollup. SQL:
     `SELECT role, task_kind, model_id, COUNT(*),
     percentile_cont(0.5) WITHIN GROUP (ORDER BY cost),
     … FROM tasks WHERE status='succeeded' AND
     date_trunc('day', completed_at) = yesterday
     GROUP BY role, task_kind, model_id`.
  2. Upsert into `stage_cost_baseline`.
  3. For each stage, compute 7-day median-of-medians
     from the prior 7 rows.
  4. Compare yesterday vs 7d median. Threshold check per
     metric; emit a `regression_event` row if over.
  5. Attribute commits: query
     `continuous-deployment` for deploys between
     `last_clean_day_for_stage` and yesterday; write the
     SHAs + authors onto the event.
  6. If flag on: fire Slack for each new event
     (`dedupe_key` uniqueness = first write wins; retry
     safe).
  7. Auto-close: events whose current day is under
     threshold get `closed_at` set.
- **Threshold configuration** — in settings:
  ```python
  regression_cost_delta_threshold: float = 0.25  # 25%
  regression_input_tokens_delta_threshold: float = 0.30
  regression_thresholds_per_role: dict[str, dict[str, float]] = {
      "architect": {"cost": 0.35, "input_tokens": 0.40},
      # architect is noisier; loose threshold
  }
  ```
  Lookup order: per-role override → fleet default.
- **`continuous-deployment` integration** — implemented in
  `coder_core.ops.regression_attribution`. Continuous-
  deployment is push-to-main for both `coder-core` and
  `coder-admin`, with `coder-system` validator runs
  tracking knowledge/prompt deploys in the same model — so
  the canonical record of "what shipped" is the GitHub
  commit history of those repos, not a separate
  `deploy_log` table. The attributor pages
  `GET /repos/{org}/{repo}/commits?since&until` for each
  configured repo (default
  `["coder-devx/coder-core", "coder-devx/coder-system"]`)
  and JSON-encodes the SHA / author / message / repo list
  onto every regression event landed for that UTC day:
  ```python
  async def attribute_commit_range(
      since: datetime, until: datetime, settings: Settings
  ) -> list[CommitInfo]: ...
  ```
  Suspect persistence runs once per cron tick (one repo
  pass per night, not per finding) and the same blob is
  stamped onto every finding from the same window.
  Graceful degrade: a server without GitHub credentials
  installed sets `suspect_commit_range` to NULL and the
  admin tab renders the row without the suspects strip.
  Test seam: `set_commit_attributor(stub)` lets unit tests
  inject canned commit lists without standing up the
  GitHub Protocol module.
- **Regressions API** — `GET /v1/_admin/regressions` (admin
  JWT). Returns open events + last 30 days of closed
  events. `POST /v1/_admin/regressions/{id}/ack` with
  `{reason: "expected; added cache-friendly prefix"}`
  sets `acknowledged_at`.
- **Admin panel tab** — `/metrics/regressions`. Table:
  `date | role.task_kind | metric | delta | commits |
  ack status`. Click row → detail with baseline vs current
  sparkline and commit diff links. Acknowledge modal with
  reason textarea.
- **Slack message format:**
  ```
  ⚠️ Cost regression: architect.design (+34% cost)
  • Baseline (7d median): 184K tokens/task
  • Yesterday: 247K tokens/task
  • Suspects (coder-core): abc1234 (alice), def5678 (bob)
  • Admin: https://coder-admin.…/metrics/regressions/<id>
  ```
- **Rollout flag** — `regression_alerts_enabled: bool = False`.
  Event detection runs regardless; Slack delivery is gated.

### Data flow

**Happy nightly run (no regression):**

1. 04:00 UTC cron fires.
2. Rollup yesterday: 12 stages × 3 models = 36 rows upserted.
3. For each stage: delta < threshold → no event.
4. Job exits; log line `"regression_check: 0 new events"`.

**Regression detected:**

1. Rollup: architect.design on Sonnet shows 247K input
   tokens median, up from 184K (35% delta).
2. Detector: 35% > 25% fleet threshold AND > 30% input-
   tokens threshold. Event created with
   `dedupe_key="architect/design/sonnet/2026-04-18/input_tokens"`.
3. Commit attribution: last clean day was 2026-04-15;
   deploys between 15 and 18 → SHAs `abc123`, `def456`.
4. Slack fires if flag on.
5. Admin tab shows the new row.
6. Operator reads the diff, acks with reason.
7. Next night: same stage is back under threshold → event
   gets `closed_at` set.

**Shadow mode:**

Flag off. Steps 1–5 run but step 4 Slack skipped. Events
accumulate in the table; operators review via the admin
tab to tune thresholds before going live.

### Invariants

- **One event per `(stage, day, metric)`**. The
  `dedupe_key` unique constraint means a retry of the
  nightly job is idempotent — the INSERT conflicts and
  becomes a no-op.
- **Baseline excludes the day under test.** Rolling
  7-day median uses days N-8 through N-1 (inclusive),
  not N. Otherwise a big regression self-masks.
- **Ack is sticky until the regression widens.** An
  acknowledged event stays silent even if the current
  value drifts further — but a *new day* that crosses
  the threshold produces a *new* event (new dedupe key).
- **Auto-close is conservative.** An event auto-closes
  only after 3 consecutive days under threshold — a
  one-day dip doesn't count as fixed.

## Open questions

- How does the detector handle stages with low task
  volume? A stage with 3 tasks/day has noisy medians.
  First cut: skip stages with <10 tasks/day in baseline
  (configurable floor). Pin in review.
- Per-role thresholds are settings-configurable; does
  that want to live in the same `template/` YAML as
  0030's routing policy, so a project can have its own
  thresholds? Probably not — this is fleet-wide
  detection, not per-project.
- Should we also detect *improvements* (a commit that
  dropped cost by 30%)? A "nice" signal for worker
  authors but not actionable. Skip for first cut.

## Rollout

Two phases:

**Phase 1 — shadow.** Rollup job + baseline + detector +
event table all land. Flag off. Admin tab renders.
Events accumulate; operators review weekly to tune
thresholds. 2-week minimum before Phase 2.

**Phase 2 — live Slack.** Flag on. Alerts fire. Monitor
false-positive rate for the first month; if >20%,
widen the per-role threshold.

**Backout plan.** `regression_alerts_enabled=False` —
Slack stops; detection keeps running; events still
land in the table but silently. Expected backout: one
config flip.

## Links

- Specs: [0032 — cost regression alerts](../../product-specs/wip/0032-cost-regression-alerts.md),
  [observability](../../product-specs/active/observability.md),
  [task-orchestration](../../product-specs/active/task-orchestration.md),
  [continuous-deployment](../../product-specs/active/continuous-deployment.md).
- ADRs: none yet.
- Services: coder-core (rollup job, baseline + events
  migrations, detector, API), coder-admin (regressions
  tab).
- Related designs: [0029 — prompt caching](./0029-prompt-caching.md),
  [0030 — tier routing](./0030-model-tier-routing.md),
  [0031 — token budgets](./0031-token-budgets.md),
  [observability-and-cost-tracking](../active/observability-and-cost-tracking.md)
  (the metrics rollup this builds on),
  [worker-communication](../active/worker-communication.md).

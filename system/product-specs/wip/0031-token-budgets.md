---
id: "0031"
title: Per-project token budgets & cost gates
type: spec
status: wip
owner: ro
created: 2026-04-18
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ["0031"]
related_specs: [observability, task-orchestration, multi-tenancy, admin-panel]
---

# Per-project token budgets & cost gates

## Problem

Today there's no cost cap per project. A runaway prompt, a
mis-configured spec that triggers a 50-developer-task fan-out, or
a new project with an unusually-verbose architect prompt can burn
through the monthly Anthropic budget without anyone noticing until
the invoice arrives. The only feedback loop is `SLACK_COST_ALERT_THRESHOLD`,
which is fleet-level and fires after the spend has happened.

We need per-project budgets that *gate* — a soft threshold that
warns and auto-throttles (downshifts 0030's tier routing to low
tier), and a hard threshold that queues new tasks behind an
operator override. Billable unit is tokens, not dollars — the
dollar-per-token rate moves with the Anthropic price list, but
tokens are the primary lever we control.

## Users / personas

- **Project owner** — sees their current spend on the project
  dashboard, gets a Slack ping at soft, gets an override
  prompt at hard. The budget belongs to them.
- **Operator** — manages the soft/hard defaults fleet-wide
  (the fallback when a project hasn't set its own),
  approves/denies hard-cap overrides, tunes the downshift
  behaviour.
- **Worker** — its dispatch is transparently downshifted or
  queued. A queued task is a first-class state, not a failure
  — the worker does not retry.

## Goals

- Per-project monthly token budget with soft + hard
  thresholds, settable via admin panel or
  `PATCH /v1/projects/{id}`.
- Fleet-level defaults for projects that haven't set their own.
- At soft: Slack warning to the project owner + auto-downshift
  tier routing (0030) to low tier for the remainder of the
  month; configurable per-project.
- At hard: new tasks land in a `budget_blocked` state; operator
  override via admin panel creates a 24 h exemption window.
- Current-month spend visible on project detail + admin panel.
- `GET /v1/projects/{id}/budget` returns `{soft_used, soft_cap,
  hard_used, hard_cap, period_reset}`.

## Non-goals

- Dollar-denominated billing. Tokens are the unit; dollar
  translation is a display concern.
- Monthly reset via Anthropic billing cycle. Use a fixed
  UTC-calendar month for simplicity; can re-visit if the
  Anthropic invoice cycle doesn't align.
- Per-role budgets. Too fine-grained — fleet signal is
  "project's over", not "project's Reviewer role is over".
- Revenue-share or charge-back to end customers. That's a
  billing/BD problem, not a coder-core problem.

## Scope

- **Migration** — `projects.budget_soft_tokens BIGINT NULL`,
  `projects.budget_hard_tokens BIGINT NULL` (NULL = use fleet
  default). Fleet defaults live in settings:
  `budget_default_soft: int`, `budget_default_hard: int`.
- **Budget roll-up** — `project_budget_period` denormalized
  table, one row per `(project_id, yyyymm)` with
  `tokens_used`, `tokens_charged`, `downshifted_at`,
  `blocked_at`, `last_override_at`, `override_granted_by`.
  Closed hourly by a cron worker; updated in-session by the
  task-completion hook.
- **Task gating** — pre-dispatch check: if the project's
  current-month `tokens_used > hard_cap`, new tasks land with
  `status=budget_blocked` and do not dispatch. An operator
  override sets `tasks.budget_override_granted_at` to let
  that specific task through.
- **Downshift** — soft breach triggers a per-project flag
  `budget_downshift_active_until_month_end`. 0030's
  `_model_for_task` checks this flag and forces the
  `low_tier` selection while it's set.
- **Alerts** — Slack on soft (`project {id}: 80% of
  monthly budget`) and hard (`project {id}: over budget;
  tasks blocked`). Dedupe per (project, threshold, month).
- **Admin panel** — new `Budget` column on the projects list
  showing `used / soft / hard` (e.g. `1.2M / 2.0M / 3.0M`)
  with a progress bar; project detail gets a budget card
  with period-reset countdown and a "set budget" affordance.

## Acceptance criteria

- [x] `projects.budget_{soft,hard}_tokens` columns land via
  migration 0035 as nullable tri-state (NULL = fleet default,
  positive = override, 0 = disabled for this project). Fleet
  defaults continue to live as `project_token_{soft,hard}_limit`
  in settings. The `project_budget_period` rollup table is
  deferred — current monthly queries use a dynamic
  month-start filter and are fast enough at current traffic.
- [ ] Task-completion hook increments
  `project_budget_period.tokens_used` atomically per task.
  (Deferred with the rollup table — the on-the-fly month query
  replaces the need until traffic justifies pre-aggregation.)
- [x] Pre-dispatch gate refuses to dispatch when
  `tokens_used >= hard_cap`; the task row fails with
  `failure_kind="budget"`. Resolution runs through
  `coder_core.api.projects.resolve_budget_limits` so a
  per-project override takes effect immediately.
- [x] Soft breach sets `projects.budget_downshift_at = now()`
  (migration 0039); `resolve_tier_model` in
  `coder_core.workers.dispatcher` checks the stamp ahead of the
  policy resolution, forcing the low-tier route while the stamp
  is non-NULL. `pin_top_tier=True` still wins so audit projects
  never silently downshift.
- [x] Slack alerts fire once per (project, threshold, month) via
  `alert_type=f"budget_soft_{project_id}_{yyyymm}"` — the 1h
  in-memory rate limiter dedupes within-hour, the yyyymm
  suffix dedupes within-month. **Latent**: every project's
  `budget_soft_tokens` is currently NULL → falls to fleet
  `project_token_soft_limit=0` → alert disabled. Configure
  via PATCH when caps are set.
- [x] `GET /v1/projects/{id}/budget` returns the current-period
  rollup with resolved per-project limits; `PATCH
  /v1/projects/{id}` accepts `budget_soft_tokens` /
  `budget_hard_tokens` updates.
- [x] Admin panel renders the Budget column + project detail
  card + override affordance. The card surfaces active override
  window + `granted_by`, soft-breach downshift state, and
  grant/revoke buttons calling the new
  `POST/DELETE /v1/_admin/projects/{id}/budget/override`
  endpoints. Override bounded to 1..168 h (7 days max — longer
  is a signal to raise the cap).
- [x] Monthly reset cron clears every project's
  `budget_downshift_at` via
  `POST /v1/_admin/budget/monthly-reset` (Cloud Scheduler at
  00:05 UTC on the 1st). Rollup-table reset is still deferred;
  the on-the-fly month query re-reads from `tasks`, so clearing
  the downshift stamp is all the cron needs to do.

## Metrics

- **Primary:** no project exceeds its hard cap without an
  operator override; soft-breach→downshift→back-under-cap
  cycle is observable in the weekly review.
- **Guardrail:** no task is `budget_blocked` for longer than
  1 h unless an operator actively decided that — a queue of
  silent `budget_blocked` tasks is a symptom of the
  approval flow being broken.
- **Audit:** count of `override_granted_by` events per
  month; a steady rise is a signal to raise the project's
  hard cap rather than keep overriding.

## Decisions

Resolved 2026-04-27 ahead of phase-2 increment dispatch.

- **Hard-cap trip mid-run.** Already-dispatched tasks finish
  (abandoning a running task loses more value than finishing
  it). The pre-dispatch gate stops the rest — a pipeline with
  10 queued dev tasks does not dispatch them all after the
  cap trips. Pre-dispatch gate is the load-bearing piece.
- **Budget period — calendar month.** Simpler for operators.
  Invoice-cycle alignment would require coder-core to know the
  Anthropic invoice boundary (which it doesn't today). Revisit
  if a tenant requests it.
- **Soft-breach notification — Slack webhook for v1.** Webhook
  infrastructure already exists. Project-owner email is a
  follow-up; not a v1 blocker.

## Open questions

_None — all resolved. See Decisions above._

## Links

- Designs: [0031 — token budgets](../../designs/wip/0031-token-budgets.md)
- Related specs: [observability](../active/observability.md),
  [task-orchestration](../active/task-orchestration.md)
  (pre-dispatch gate hook),
  [multi-tenancy](../active/multi-tenancy.md)
  (per-project data isolation),
  [admin-panel](../active/admin-panel.md)
  (budget UI).
- ROADMAP: Phase 4 — Cost & Token Efficiency; chains on
  [0030 — model tier routing](./0030-model-tier-routing.md)
  (downshift leverages tier routing) and feeds
  [0032 — regression alerts](./0032-cost-regression-alerts.md)
  (budgets are the per-project alert threshold).

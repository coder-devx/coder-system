---
id: "0069"
title: Canonical project-state endpoint and consumers
type: spec
status: wip
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
summary: ~
served_by_designs: ["0069"]
related_specs:
  - admin-panel
  - observability
parent: ~
---

# Canonical project-state endpoint and consumers

## Problem

A 2026-05-09 walk of the deployed admin panel found the same project
quantities reported with different values on different pages. For the
`coder` project at the same instant:

- Project Overview: workers `0/4` idle, queue `0`.
- Pipeline: `Retry 27 stuck` button.
- Inbox: `27 items across 1 project need a human`, oldest 15d.
- Fleet: active runs `0`, **8 blocked**.
- Escalations: `No escalations match the current filter`.
- Overview · Cache hit: `351301%`. TaskDetail · Cache hit rate: `366900%`.
- Metrics 7d: total `139`, succeeded `18`, failed `8` — 113 unaccounted;
  success rate `92.8%` matches neither ratio.

Each surface re-derives counters and totals in the browser from its
own slice of the same data. The operator has no way to know which
number to believe, and the pattern silently invites the same bug on
every new page.

ADR 0031 commits to a single server-computed source for these
counters. This spec implements it.

## Users / personas

- **Operator** opening the admin panel after an alert. Today: reads
  three different "stuck" counts on three pages and guesses. After:
  one number, same on every surface, with a `derived_at` chip telling
  them how fresh it is.
- **Page author** adding a new operator surface. Today: writes a fresh
  reducer over `tasks`, gets the math wrong in some edge case, ships
  another inconsistency. After: renders from one typed payload.
- **Reviewer worker** auditing the panel. Today: every dashboard
  module needs its own correctness check. After: the canonical
  endpoint is the single thing to test.

## Goals

When this ships:

- Every operator surface that shows project-level totals (header pill,
  Overview cards, Pipeline counts, Inbox badge, Fleet rows, Metrics
  summary cards) reads from `GET /v1/projects/{id}/state`.
- Cross-page numbers reconcile by construction. The 27 / 8 / 0
  contradiction above cannot recur.
- The cache-hit-rate unit bug (`351301%` / `366900%`) is gone — fixed
  once, server-side.
- The Metrics summary cards math reconciles (`total = succeeded +
  failed + running + queued + stuck + blocked + paused + cancelled`).
- A fleet sibling endpoint `GET /v1/admin/state` returns the same
  shape rolled up across projects, used by [Fleet.tsx](../../coder-admin/src/pages/Fleet.tsx).

## Non-goals

- Changing what each page *displays*. This is a re-source, not a
  redesign. The visual layout and filter affordances stay. WIP 0070
  (Now) and 0071 (failure-mode grouping) make the layout changes.
- New SSE channel design. We extend the existing pipeline-events SSE
  to broadcast `project.state.changed` deltas; we don't add a new
  transport.
- Cross-project authorisation. The endpoint is project-scoped exactly
  like every other `/v1/projects/{id}/...` call (multi-tenancy
  invariants apply unchanged).

## Scope

In:

- New endpoint `GET /v1/projects/{id}/state` returning, in one call:
  `{counts: {running, queued, stuck, blocked, paused, failed_recent,
  succeeded_today, succeeded_7d, cancelled_recent}, cost: {tokens_today,
  tokens_7d, cache_hit_rate, budget_state, budget_used_pct}, workers:
  {active, total}, oldest: {stuck_age_seconds, unapproved_plan_age_seconds},
  derived_at}`.
- New endpoint `GET /v1/admin/state` returning `{projects: [{id,
  state}], totals: {...}}` with the same schema rolled up.
- SSE event `project.state.changed` broadcast on any field-affecting
  transition; payload is the full state object so the frontend can
  cache a single "current" copy per project.
- Frontend refactor: [Projects.tsx](../../coder-admin/src/pages/Projects.tsx),
  [ProjectDetail.tsx](../../coder-admin/src/pages/ProjectDetail.tsx),
  [Pipeline.tsx](../../coder-admin/src/pages/Pipeline.tsx),
  [Inbox.tsx](../../coder-admin/src/pages/Inbox.tsx),
  [Fleet.tsx](../../coder-admin/src/pages/Fleet.tsx), and
  [Metrics.tsx](../../coder-admin/src/pages/Metrics.tsx) read counters
  exclusively from this endpoint. Local recompute paths are deleted.
- Server-side fix for the `cache_hit_rate` calculation (current bug
  produces values >100%) and the success-rate formula in the metrics
  summary cards.
- A hard lint or AGENTS.md rule in `coder-admin` barring
  page-local recomputation of canonical counters.

Out:

- Any new visual designs (covered by WIPs 0070–0073).
- Renaming the panel's existing routes.

## Acceptance criteria

- **AC1.** `GET /v1/projects/{id}/state` returns the schema in
  Scope/In within p95 ≤ 200ms over a representative project (`coder`)
  on Cloud Run, joining task, run, plan, gate, and budget data in one
  query plan.
- **AC2.** For a single fixed instant on the `coder` project, the
  values rendered on Projects, ProjectDetail, Pipeline, Inbox, Fleet,
  and Metrics for `running`, `queued`, `stuck`, `blocked`, `paused`,
  and `tokens_7d` are identical (same int / same string).
- **AC3.** `cache_hit_rate` is bounded `[0.0, 1.0]` in the response
  and rendered as a percentage with one decimal place; the prior
  `351301%` / `366900%` outputs are unreproducible from any input.
- **AC4.** Metrics summary cards satisfy `total == succeeded +
  failed + running + queued + stuck + blocked + paused +
  cancelled` for any 7-day window of the `coder` project; the
  reconciliation is asserted in a backend test.
- **AC5.** SSE `project.state.changed` fires within 2s of any
  state-affecting transition (task status change, plan approval,
  budget bump, escalation open) and the admin panel updates the
  affected counters from the event payload without re-fetching.
- **AC6.** A repository-level guardrail (eslint rule, custom AST
  check, or AGENTS.md hard rule reinforced by a CI grep) prevents new
  page-local recomputation of canonical counters in `coder-admin`.
- **AC7.** `GET /v1/admin/state` returns the per-project array plus
  fleet totals using the same schema, and powers
  [Fleet.tsx](../../coder-admin/src/pages/Fleet.tsx)'s four header
  cards plus the per-project table row.

## Metrics

- p95 endpoint latency ≤ 200ms post-ship; tracked alongside other
  `/v1/projects/...` endpoints.
- Number of distinct browser code paths that compute project-level
  counters: drops from current N (≥6) to 1.
- Operator confusion incidents tagged `dashboard-mismatch` in the
  weekly retro: drops to zero by 30-day soak.

## Open questions

- Cache key shape for the endpoint — per-project rolling 1s window vs
  per-request join? Defer to design (WIP 0069).
- Whether the SSE event carries the full payload or just the changed
  fields. Defer to design.

## Links

- ADR: [0031](../../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- Design: [0069](../../designs/wip/0069-canonical-project-state.md)
- Related: [admin-panel](../active/knowledge/admin-panel.md), [observability](../active/pipeline/observability.md)

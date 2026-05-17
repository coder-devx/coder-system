---
id: "0070"
title: Now — operator's actionable queue as default landing
type: spec
status: wip
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
summary: ~
served_by_designs: ["0070"]
related_specs:
  - admin-panel
  - escalations
  - self-healing
parent: ~
---

# Now — operator's actionable queue as default landing

## Problem

The admin panel's default landing route is the projects table — a
list, not a queue. Real signal is split across surfaces and partly
hidden:

- 27 stuck developer tasks for 4–15 days surface only on
  [Inbox.tsx](../../coder-admin/src/pages/Inbox.tsx), which is itself
  unreachable from project context (no nav entry, no badge on
  Overview). Operator must know the URL or the `⌘K` action.
- One plan draft for spec 0060 has been sitting **5 days** waiting
  for approval and surfaces only as a single row on the per-project
  Plans page.
- Open ship gates, regressions, budget breaches, and escalations live
  on four further pages each with its own filter UI.

The operator round-robins tabs to figure out "what wants my
attention right now". The Inbox aggregator partially solves this but
still requires a click-through per row, has no inline actions, and is
invisible from project context.

## Users / personas

- **Operator on shift.** Today: opens the panel, sees a project
  table, has to remember to visit Inbox / Plans / Escalations /
  Regressions / ShipGate to find work. After: lands on a single
  ranked list of every actionable thing with inline action buttons.
- **Operator who just resolved one item.** Today: navigates back to
  the table they came from, re-applies filter state. After: stays on
  Now, the row they actioned disappears, the next item moves up.
- **Project owner glancing at the panel.** Today: scans 4 projects
  in a table; doesn't know if anything needs them. After: top of Now
  is "actions across N projects" with a project filter chip.

## Goals

When this ships:

- The default route at `/` is **Now** — every actionable item across
  every project the operator can see, ranked by severity × age, in
  one ordered list.
- Each row exposes its primary actions inline (approve / reject /
  retry / ack / bump / pause / open). The operator can resolve
  common items without navigating to a detail page.
- The current `/inbox` page is removed; its aggregator becomes Now's
  data source.
- A persistent header pill on every page shows `Now: N actions
  pending` and links back; the count updates live.
- Items that need privileged context (multi-task overrides, gate
  bodies, audit trails) link out to the relevant detail page; Now
  itself never becomes a tabbed mini-app.

## Non-goals

- Displaying *non-actionable* health information (charts, trends,
  cost graphs) — those stay on Metrics / Fleet.
- Replacing per-project pages. Pipeline, Runs, Plans, Specs etc.
  remain; Now is a global cross-project surface, not a substitute.
- Real-time chat or comment threads on items. Out of scope; lives in
  detail pages.

## Scope

In:

- New `/` route rendering Now. Replaces the current `Projects.tsx`
  landing.
- `Inbox.tsx` page deleted; the existing
  `/v1/admin/inbox` aggregator endpoint extended (or replaced) to
  include the six row kinds in Goals: `plan-review`, `open-gate`,
  `stuck-task`, `stuck-group` (see WIP 0071), `regression`,
  `budget-breach`, `escalation`.
- A typed payload per row containing: `project_id`, `kind`,
  `severity` (critical/warning/info), `label`, `detail`, `age_seconds`,
  `actions: [{id, label, confirm: bool}]`, `target: {type, id}` for
  the detail-page click-through.
- Inline action endpoints (or wiring to existing endpoints) for:
  approve plan, reject plan, retry stuck task, retry stuck group,
  ack regression, bump budget, pause project, ack escalation. Each
  writes an `audit_event` with `correlation_id` linking back to the
  Now row that triggered it.
- A persistent header pill component (`<NowBadge/>`) imported into
  `App.tsx` showing the count for the current operator scope.
- A small filter strip: project chip multi-select, kind multi-select.
  Filter state is URL-encoded so deep-links work.
- Loading / empty / error / after-action toast states defined as
  separate render paths, each tested.

Out:

- Failure-mode grouping logic — that's WIP 0071.
- Drive mode handoff from Now — that's WIP 0073.
- A "Today" or "Yesterday" historical recap — out of scope; Now is
  the present tense only.

## Acceptance criteria

- **AC1.** Logging in lands the operator on `/`, which renders the
  Now surface. The previous Projects table is reachable from the
  command palette and from a `/projects` route, but is no longer
  default.
- **AC2.** The Now list shows, at minimum, these row kinds with
  realistic data on the `coder` project: `plan-review`, `open-gate`,
  `stuck-task`, `regression`, `budget-breach`, `escalation`. Each
  row has at least one inline action button that fires without
  navigation.
- **AC3.** Clicking an inline action calls the corresponding API,
  shows a 3s success toast, removes the resolved row from the list,
  and writes an `audit_event` whose `correlation_id` is recoverable
  from the toast.
- **AC4.** The header `<NowBadge/>` is present on every page inside
  `App.tsx`, polls or subscribes to the count, and updates within 2s
  of any item resolution.
- **AC5.** Project filter, kind filter, and the URL-encoded state
  round-trip: a deep-link to `/?project=coder&kind=stuck-task`
  renders the filtered list directly.
- **AC6.** All four canonical states render correctly with no
  spinners — empty (`Nothing waiting. {derived_at}.`), loading
  (`Loading…` text-only), error (raw message in mono + retry
  button), single-action toast (auto-dismiss 3s).
- **AC7.** `Inbox.tsx`, `inbox.test.tsx`, and the `/inbox` route are
  deleted from `coder-admin`. Any remaining link target redirects
  to `/`.

## Metrics

- Median time from login to first resolved action: target ≤ 30s
  (today: requires 1 navigation to Inbox + 1 click-through + 1 detail
  action ≈ 60-120s).
- Percentage of operator sessions that visit only `/` to triage:
  target ≥ 60% by 30-day soak.
- Stuck-task age oldest in queue: dropping from 15d (today) to ≤ 24h
  by 30-day soak as inline retry-all becomes routine.

## Open questions

- Severity scoring formula. Does open-gate always outrank stuck
  unless gate age < stuck age? Defer to design (WIP 0070).
- How to handle items the operator *cannot* action (no permission)
  — hide row, show row with disabled action, or render with a
  "request access" button? Defer to design.

## Links

- ADR: [0031](../../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- Design: [0070](../../designs/wip/0070-now-landing-surface.md)
- Depends on: [0069](./0069-canonical-project-state.md)
- Related: [admin-panel](../active/knowledge/admin-panel.md), [escalations](../active/pipeline/escalations.md), [self-healing](../active/pipeline/self-healing.md)

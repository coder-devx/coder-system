---
id: "0031"
title: One canonical project-state read for every operator surface
type: adr
status: proposed
date: 2026-05-09
deciders: [ro]
supersedes:
superseded_by:
relates_to_designs: ["0069", "0070", "0071", "0072", "0073"]
---

# ADR 0031 — One canonical project-state read for every operator surface

## Context

A live walk of the deployed admin panel on 2026-05-09 found the same
quantities reported with different values on different pages of the
same project (`coder`):

- Project Overview: workers `0/4` idle, queue `0`.
- Pipeline header: `Retry 27 stuck`.
- Inbox: `27 items across 1 project need a human`, oldest 15d.
- Fleet: active runs `0`, **8 blocked**.
- Escalations: `No escalations match the current filter`.
- Overview · Cache hit: `351301%`. TaskDetail · Cache hit rate: `366900%`.
- Metrics 7d: total `139`, succeeded `18`, failed `8` — 113 tasks
  unaccounted, success rate `92.8%` matches neither the terminal
  ratio nor the all-task ratio.

These are not six bugs. They are the same bug surfacing in six places:
**every operator-facing page computes its own version of the project's
totals from a different slice of the same data, in the browser.** The
operator has no way to know which number to believe.

The same shape will reappear every time we add a page (Now, drive
mode, replay), because the current pattern silently invites it.

## Options considered

1. **Status quo + best-effort consistency reviews.** Page authors
   review each other's counter logic.
   - Pros: no new endpoint, no migration.
   - Cons: doesn't scale; the bugs above already passed review.

2. **One canonical server-side endpoint that every surface reads.**
   `GET /v1/projects/{id}/state` returns the joined, server-computed
   counters and cost totals, plus a `derived_at` timestamp. Pages may
   render their own *list contents* (the actual rows of a table), but
   never recompute totals.
   - Pros: numbers reconcile by construction; unit/coercion bugs (the
     `351301%` cache hit) get fixed once; new pages are render
     concerns, not counter concerns.
   - Cons: page authors must accept the canonical schema even when a
     specialised count would be cheaper to inline; adding a new
     counter requires extending the endpoint.

3. **Database view + per-page direct reads.** Each page reads its own
   subset of a shared SQL view.
   - Pros: keeps the view as the single source of truth.
   - Cons: doesn't help the browser-side coercion bugs (cache hit
     rate, success-rate formula); each page still re-implements its
     own join shape; SSE invalidation is harder.

## Decision

Option 2. **All admin-panel surfaces that display project-scoped
counters or cost totals read them from one canonical endpoint
(`GET /v1/projects/{id}/state`).** Page-local recomputation of these
totals is forbidden going forward. A matching `GET /v1/admin/state`
returns the fleet-wide rollup using the same schema.

Browser code may still compute *list* contents (filter the pipeline
table, group the inbox, paginate the audit log). It must not
recompute the headline totals those lists summarise.

## Rationale

One source of truth means operators see consistent numbers across
pages by construction, not by review discipline. The endpoint joins
the data once, on the server, in one place where coercion bugs and
formula errors can be tested. Adding a new operator surface becomes a
question of "which counters do I render?" — never "how do I count?".

The phase that follows this ADR (WIPs 0069–0074) consolidates the
operator surface around this rule. WIP 0069 introduces the endpoint
and migrates the existing pages; subsequent WIPs (Now, failure-mode
grouping, task replay, drive mode, SpecCompose write) consume it
without recomputation.

## Consequences

- **Positive.**
  - Counters reconcile across pages by construction.
  - Cache-hit-rate unit bug and the metrics summary-card math get
    fixed once, server-side, during WIP 0069.
  - SSE invalidation has a single payload shape to broadcast.
  - New operator surfaces are cheaper to add.
- **Negative.**
  - Page authors must accept the canonical schema even where a
    specialised count would be smaller in isolation.
  - Adding a new counter requires extending the endpoint, not just a
    frontend change.
- **Follow-ups.**
  - WIPs 0069–0074 (Phase 9 — Operator surface coherence) ship under
    this rule.
  - On WIP 0069 ship, the `coder-admin` AGENTS.md gains a hard rule
    barring page-local recomputation of the canonical counters.

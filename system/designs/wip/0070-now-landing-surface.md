---
id: "0070"
title: Now — operator's actionable queue as default landing
type: design
status: wip
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
summary: ~
implements_specs: ["0070"]
decided_by: ["0031"]
related_designs:
  - escalations
  - audit-log
  - worker-communication
affects_services:
  - coder-core
  - coder-admin
affects_repos:
  - coder-core
  - coder-admin
parent: ~
---

# Now — operator's actionable queue as default landing

## Context

Spec [0070](../../product-specs/wip/0070-now-landing-surface.md)
makes Now the default landing route. The operator currently
round-robins Inbox / Plans / Escalations / Regressions / ShipGate to
piece together "what wants my attention". Each page is a tab,
nothing is inline-actionable, and the cross-project Inbox is
unreachable from project context.

This design covers: the API shape Now consumes, the row taxonomy,
the inline-action model, the live-update transport, and the
header-pill component that surfaces the count site-wide.

## Goals / non-goals

- **Goals.** One ranked list, six row kinds, inline actions per
  row, live updates via the same SSE pattern WIP 0069 introduces.
- **Non-goals.** No grouping logic — that's WIP 0071. No drive-mode
  hand-off — that's WIP 0073. No historical recap.

## Design

```mermaid
flowchart TB
  subgraph backend [coder-core]
    aggSvc[NowAggregator]
    plans[(task_plans)]
    gates[(gates)]
    tasks[(tasks · stuck)]
    regs[(regression_events)]
    bud[(project_budgets)]
    esc[(escalations)]
  end
  plans --> aggSvc
  gates --> aggSvc
  tasks --> aggSvc
  regs --> aggSvc
  bud --> aggSvc
  esc --> aggSvc
  aggSvc -->|GET /v1/now| api[Handler]
  aggSvc -. now.changed SSE .-> sse[(SSE channel)]
  api --> hook[useNow hook]
  sse --> hook
  hook --> page[/Now page/]
  hook --> badge[<NowBadge/>]
  page -->|inline action POST| handlers[Action handlers]
  handlers -->|writes| audit[audit_events]
  handlers -. now.changed SSE .-> sse
```

### Components

- **`NowAggregator`** (new module in `coder-core`,
  `src/coder_core/now/aggregator.py`). Composes the six row kinds
  from their respective tables in one query plan, applies the
  operator's project-scope (which projects the JWT can see), ranks
  by severity × age.
- **`NowItem` model.** Pydantic. Fields: `project_id`, `kind`
  (literal: `plan-review` | `open-gate` | `stuck-task` |
  `stuck-group` | `regression` | `budget-breach` | `escalation`),
  `severity` (`critical` | `warning` | `info`), `label`, `detail`,
  `age_seconds`, `actions` (list of `NowAction` — `id`, `label`,
  `confirm: bool`), `target` (typed link target).
- **HTTP handler.** `GET /v1/now?project=…&kind=…` returns
  `{items: [NowItem], derived_at, total}`. Project and kind filters
  intersect.
- **SSE.** New event type `now.changed` on the existing pipeline
  events channel. Payload is `{added: [NowItem], removed:
  [item_id], updated: [NowItem]}` so the frontend can splice
  without re-rendering the world. Falls back to a full re-fetch on
  any unknown delta shape.
- **Frontend.** `useNow()` hook subscribes to SSE, caches the list
  in state, exposes `{items, isStale, error, refresh}`. The Now
  page renders one ordered list. `<NowBadge/>` is a tiny consumer
  that shows the count and renders inside `App.tsx` header.

### Data flow

A typical flow — operator clicks `[approve]` on a plan-review row:

1. Click handler calls `POST /v1/projects/{id}/plans/{planId}:approve`
   (existing endpoint).
2. Server approves, writes `audit_event(actor=human:{email},
   correlation_id={now_item_id}, action="plan.approved")`.
3. Server emits `now.changed` SSE with `removed: [now_item_id]`.
4. Frontend `useNow` splices the item out; the list re-renders
   with the next item moved up. A 3s success toast shows "Plan
   approved".

Severity scoring (provisional, defer to implementation tuning):

```
score = severity_weight[severity] * 1000 + min(age_seconds, 86400 * 7)
```

Where `severity_weight = {critical: 3, warning: 2, info: 1}`. Sort
descending. This gives critical-old > critical-new > warning-old >
warning-new > info-anything, with ties broken by age. The exact
weights are tunable; the *shape* (severity dominates age, age breaks
ties within severity, age caps at 7d) is the design choice.

### Edge cases

- **Item the operator can't action.** Server returns the row with an
  empty `actions` list and a `permission` field. UI renders the row
  with a disabled inline button labelled `request access`; clicking
  opens a small popover linking to the relevant access flow. This
  preserves visibility — the operator sees the queue depth even for
  items they can't resolve.
- **Stale SSE on bad network.** `useNow` flips `isStale=true` after
  60s without an event; UI adds an amber "stale" chip near the
  refresh button. Manual refresh always works.
- **Duplicate item between Now and a per-project page.** A
  plan-review row on Now and the Plans page are the same plan; both
  reflect approval immediately because both subscribe to the same
  state. No drift possible.
- **Item count on the badge during transitions.** The badge shows
  the cached count; SSE deltas update it in <2s. Hard refresh
  always reconciles.

## Open questions

- Bulk-action shape from Now itself (e.g. select 3 stuck rows,
  retry all). Probably out for v1; WIP 0071's `stuck-group` covers
  the common case. Confirm during implementation.
- Whether to surface a "snooze" action per row (e.g. `snooze 1h`).
  Tempting; risks turning Now into a todo app. Defer.

## Rollout

1. Build NowAggregator + endpoint + SSE behind flag
   `CODER_NOW_ENABLED`. Shadow at `/now-preview`.
2. Wire `<NowBadge/>` first (read-only). Validate counts match.
3. Wire one inline-action kind at a time (start with `plan-review`,
   easiest), confirm audit + SSE invalidation work.
4. Add the rest of the action kinds; do them as one PR each so any
   regression is small.
5. Flip default landing to `/now` for ops accounts (canary), then
   all admins.
6. Delete `Inbox.tsx` and `/inbox` route in the same PR that flips
   default landing fleet-wide.

## Links

- Spec: [0070](../../product-specs/wip/0070-now-landing-surface.md)
- ADR: [0031](../../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- Depends on design: [0069](./0069-canonical-project-state.md)
- Services: [coder-core](../../services/coder-core.md), [coder-admin](../../services/coder-admin.md)

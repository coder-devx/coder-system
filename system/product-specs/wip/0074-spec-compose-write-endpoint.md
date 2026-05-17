---
id: "0074"
title: SpecCompose write endpoint and draft hand-off to Now
type: spec
status: wip
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
summary: SpecCompose [file spec] writes via POST /v1/projects/{id}/specs (branch + commit_tree + PR); Stage 1 shipped, Stage 2 (drafts) deferred.
served_by_designs: []
related_specs:
  - admin-panel
  - knowledge-api
parent: ~
---

# SpecCompose write endpoint and draft hand-off to Now

## Problem

The [`SpecCompose.tsx`](../../coder-admin/src/pages/SpecCompose.tsx)
page is the panel's most polished surface — two-column compose form,
live cost forecast based on similar shipped specs, role-tagged
acceptance criteria, live markdown preview. A 2026-05-09 walk
confirmed it works end-to-end visually.

It cannot file specs. The page banner reads:

> Preview: markdown preview only. coder-core does not yet expose a
> write endpoint for new specs.

Filing a new spec today still requires the CLI (or a hand-rolled PR
against the per-project knowledge repo). The compose page exists
but is decorative.

## Users / personas

- **Operator with a 5-minute idea.** Today: opens the panel, fills
  in the form, gets a forecast, *cannot file*, falls back to CLI or
  GitHub UI. After: clicks `[file spec]`, gets an ID, sees the spec
  appear on the Specs page and (if left as draft) on Now.
- **PM worker that drafted a spec via API.** Today: writes directly
  through the Knowledge Write API with full PR machinery. After:
  same path — this WIP doesn't change worker flows.
- **Reviewer** auditing newly-filed specs. Today: only sees specs
  after a PR lands. After: same — this WIP files via the same write
  pipeline; reviewer sees the same PR.

## Goals

When this ships:

- The "Preview only" banner is gone. `[file spec]` is enabled.
- Filing a spec from the panel produces the same artifact shape and
  PR shape as the CLI, going through the existing Knowledge Write
  API (no parallel write path).
- The post-write states are first-class: `saving`, `filed`,
  `validation-failed`. The form doesn't blank-out on success
  before the operator sees what happened.
- Drafts that aren't filed within 24h surface as a `draft-spec`
  row on Now (WIP 0070), with `[resume]` and `[discard]` inline
  actions.
- The Specs page distinguishes `draft` rows from `shipped` rows —
  today they render identically.

## Non-goals

- A new schema for specs. We use the existing spec frontmatter and
  body shape as defined by `system/product-specs/_TEMPLATE.md`.
- A panel-side knowledge editor for arbitrary artifacts. We wire
  one form (SpecCompose) to one endpoint; broader editors are out
  of scope.
- Skipping reviewer / PR workflow. The endpoint files via the
  existing write pipeline; whatever validation / approval applies
  to a CLI-filed spec applies here.

## Scope

In:

- New endpoint `POST /v1/projects/{id}/specs` accepting the
  SpecCompose payload (`title`, `phase`, `summary`, `goal`,
  `non_goal`, `acceptance_criteria: [{role, text}]`, `depends_on`).
- Internally, the endpoint calls the existing Knowledge Write API
  to commit the new spec under
  `system/product-specs/wip/{id}-{slug}.md` and update the
  matching `registry.yaml` entry — atomically, in one PR, on the
  project's knowledge repo. Same machinery as the CLI flow.
- Server returns `{spec_id, pr_url, status: "filed" | "draft"}`.
  `draft` is the state when validation passes but the operator
  chose `[save draft]` instead of `[file spec]`. `filed` opens a
  PR.
- Validation errors return a typed list of field-level errors
  (`field`, `code`, `message`) so the panel can anchor each error
  to the relevant input.
- Frontend: remove the "Preview only" banner; wire `[file spec]`
  and `[save draft]`; render `saving` / `filed` / `validation-failed`
  states per WIP 0074 design notes (folded into the existing page,
  no new design file).
- Specs page row redesign (`Specs.tsx`): draft state chip (violet),
  `[resume]` and `[discard]` inline actions, `stale` chip after 7d
  of inactivity.
- Now (WIP 0070) integration: a `draft-spec` row kind appears for
  drafts older than 24h with `[resume]` and `[discard]` inline.

Out:

- Editing a spec already merged to `wip/`. (Use the knowledge
  editor / PR flow.)
- Discarding a `filed` spec from the panel. (PR close + git
  delete, same as today.)

## Acceptance criteria

- **AC1.** `POST /v1/projects/{id}/specs` files a spec via the
  existing Knowledge Write API and returns `{spec_id, pr_url,
  status: "filed"}`. The created file matches `_TEMPLATE.md`'s
  WIP frontmatter and the registry is updated in the same PR.
- **AC2.** The `[file spec]` button on `SpecCompose.tsx` is
  enabled, hits AC1, and on success the form is replaced by an
  emerald-tinted "Filed as 00NN — {slug}" card with `[open spec]`,
  `[view in roadmap]`, `[start another]` actions. The "Preview
  only" banner is removed from the page.
- **AC3.** `[save draft]` posts the same payload with
  `status: "draft"`. No PR is opened. The form is preserved for
  resume.
- **AC4.** Validation failures return a typed field-error list and
  render anchored to their fields with rose borders; no global
  toast.
- **AC5.** A draft sitting >24h surfaces on Now as a `draft-spec`
  row with `[resume]` and `[discard]` inline actions; `[discard]`
  removes the draft and writes an `audit_event`.
- **AC6.** The Specs page row distinguishes `draft` from
  `shipped` — `draft` rows have a violet state chip, age, owner,
  and `[resume]` / `[discard]` on hover; `stale` chip appears on
  drafts untouched > 7d.
- **AC7.** Filing concurrent specs against the same project does
  not double-allocate IDs (the dispatcher-injected allocation
  guard from ADR 0028 applies unchanged).

## Metrics

- Spec compose start → file PR median: drops from
  CLI-equivalent (5–15min including auth, branch, push) to ≤ 2min
  in-panel.
- Number of specs filed through the panel per week: emerges from
  zero (today) and trends up.
- Drafts >7d stale per project: ≤ 3 by 30d soak.

## Open questions

- Whether `[file spec]` should require an explicit confirm modal
  given it opens a real PR. Probably yes; defer to UI iteration on
  first ship.
- Whether the panel should show a live preview of the resulting
  PR diff before opening it. Useful, but adds endpoint surface
  area; consider as a follow-up.

## Links

- ADR: [0031](../../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- Depends on: [0069](./0069-canonical-project-state.md), [0070](./0070-now-landing-surface.md)
- Related: [admin-panel](../active/knowledge/admin-panel.md), [knowledge-api](../active/knowledge/knowledge-api.md)

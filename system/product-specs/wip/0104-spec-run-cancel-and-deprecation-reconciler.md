---
id: 0104
title: Spec-run cancel verb + auto-cancel on WIP deprecation
type: spec
status: wip
owner: ro
created: '2026-05-19'
updated: '2026-05-19'
last_verified_at: '2026-05-19'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- task-orchestration
- admin-panel
- knowledge-api
- audit-log
parent: pipeline-operations
---

# Spec-run cancel verb + auto-cancel on WIP deprecation

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

A `spec_runs` row represents the orchestrator's commitment to drive one WIP spec from draft → architecture → plan → implementation → ship → active. It has lifecycle states (`pm_pending`, `architect_pending`, `tm_pending`, `plan_pending`, `implementing`, `ship_pending`, `shipped`) but no terminal "abandoned" state. When an operator deprecates a WIP spec in the knowledge repo (e.g. because it duplicated another, or scope was rejected), the matching spec-run row stays alive forever — paused via `paused_reason: manual` at best — and surfaces in the Now feed as a `paused_spec` informational item indefinitely.

This bit us on 2026-05-19: six near-duplicate specs (0097, 0098, 0100, 0101, 0102, 0103) were consolidated into canonical spec 0099. The WIP files moved to `deprecated/` in coder-system commit `d6379ae`, but the six matching spec-runs in coder-core remained at `state=plan_pending paused_reason=manual` because no API verb exists to cancel them. The Now feed now permanently lists six dead specs as "paused spec" rows until an operator clears them by some out-of-band mechanism.

The deeper gap: the orchestrator's state machine and the knowledge-repo state diverge. The orchestrator believes it's actively driving six specs that no longer exist. There is no reconciler.

## Users / personas

- **Pipeline operators** consolidating, deprecating, or otherwise abandoning a WIP spec — today they have to manually pause the run and live with the residual entry in the Now feed.
- **Future-self operators** auditing "what happened to spec NNNN?" who today have to read git history because the spec-run row gives no answer.

## Goals

- A spec-run can transition to a terminal `cancelled` state via an explicit operator action, with a reason and (optional) `superseded_by_spec` pointer.
- When a WIP spec is deprecated in the knowledge repo, the matching spec-run auto-cancels on the next reconciler tick — no manual API call required.
- Cancelled spec-runs drop out of operator-facing surfaces (Now feed, plan-approval queue, ship-approval queue).
- The cancellation reason and (when applicable) the superseding spec ID are queryable, so "where did spec 0097 go?" has a one-hop answer.

## Non-goals

- Cancelling individual tasks inside a spec-run — task-level cancellation is a separate concern (override → skip_to_stage).
- Cascading kill of in-flight dev-task work on `task/*` branches — the cancel verb stops the orchestrator from spawning new tasks but lets in-flight tasks complete or fail on their own.
- Backfilling historical `paused_reason: manual` runs whose WIPs are still in `wip/` — the reconciler only catches WIPs that have moved to `deprecated/`.

## Scope

**New terminal state.** Add `cancelled` to the `spec_runs.state` enum, alongside the existing `shipped`. Cancelled is terminal — no further task spawning, no resume verb.

**New columns** on `spec_runs`: `cancelled_at TIMESTAMPTZ`, `cancelled_by TEXT`, `cancelled_reason TEXT`, `superseded_by_spec TEXT`. All nullable, default null. Single forward migration; no backfill.

**New endpoint.** `POST /v1/projects/{project_id}/spec-runs/{wip_spec_id}/cancel` accepts `{reason: string, superseded_by_spec: string|null}`. Transitions any non-terminal run to `state=cancelled`, stamps the four new columns, writes a `spec_run.cancel` audit event, returns the updated row. Cross-project access returns 404 (tenant isolation).

**Auto-reconciler.** A new dispatcher tick (`coder-core-spec-run-reconcile-tick`, hourly Cloud Scheduler) walks every non-terminal spec-run and asks the knowledge API for the matching WIP file. If the WIP is missing from `wip/` (moved to `deprecated/` or fully deleted) OR has `status: deprecated` in its frontmatter, the reconciler auto-cancels the run with `cancelled_reason='wip_deprecated_in_knowledge_repo'`. If the deprecated WIP's frontmatter has a `superseded_by` field naming an existing spec, the reconciler stamps `superseded_by_spec` accordingly.

**Now feed.** The Now feed already filters out `state=shipped` runs; extend it to also filter `state=cancelled`. Both `open_gate` and `paused_spec` item kinds skip terminal states.

## Acceptance criteria

- **AC1.** `POST /v1/projects/{project_id}/spec-runs/{wip_spec_id}/cancel` with `{reason: "duplicate"}` transitions a `plan_pending` run to `state=cancelled` and stamps `cancelled_at`, `cancelled_by` (actor's id), and `cancelled_reason`. Returns the updated row. A subsequent `GET /spec-runs/{wip_spec_id}` shows the cancelled state and metadata.
- **AC2.** Cancelling a run from project A from project B's URL returns 404 (tenant isolation, asserted by an integration test).
- **AC3.** A spec-run whose matching WIP file has been moved to `deprecated/` (or has `status: deprecated` frontmatter) is auto-cancelled by the reconciler tick within one scheduler interval, with `cancelled_reason='wip_deprecated_in_knowledge_repo'`. If the deprecated WIP frontmatter has a `superseded_by` field, `superseded_by_spec` is populated from it.
- **AC4.** Cancelled spec-runs do not appear in the Now feed (`open_gate` or `paused_spec` item kinds) for any operator, regardless of `paused_reason`.
- **AC5.** Every cancel action (explicit endpoint OR reconciler-driven) writes a `spec_run.cancel` audit event row with the spec-run id, actor, reason, and (if set) `superseded_by_spec`, recoverable via the existing audit-log surface.

## Metrics

- Zero `paused_spec` Now-feed items for spec-runs whose WIP file is absent from `wip/` within 24 h of this spec shipping (immediate cleanup of the existing 6 zombies + any future ones).
- Reconciler tick runs with `entries_cancelled` counter exposed for operator observability.

## Open questions

- Should the reconciler also auto-cancel runs whose WIP file has been *renamed* (e.g. id changed in frontmatter)? Defaulting to no — that's a different class of event and likely needs operator review.
- The new `superseded_by` frontmatter field on deprecated WIPs is new — does it need a separate spec / registry-validator extension? Defaulting to "tolerated as a free-form string by validate.py until a follow-up spec formalizes it."
- Should `state=cancelled` runs become eligible for hard-delete after some retention period (e.g. 90 days)? Defaulting to "keep forever" for audit-log lineage; revisit if the table grows unbounded.

## Links

- Related specs: [task-orchestration](../active/pipeline/task-orchestration.md), [admin-panel](../active/knowledge/admin-panel.md), [knowledge-api](../active/knowledge/knowledge-api.md), [audit-log](../active/tenancy/audit-log.md)
- Surfaced during the 2026-05-19 consolidation of 6 knowledge-reads-panel duplicate specs into canonical 0099 (coder-system commit `d6379ae`).
- Parallel ship-time hygiene gap shipped same day: [coder-core#306](https://github.com/coder-devx/coder-core/pull/306) — co-batch cross-link awareness + active-body shape enforcement at ship time.

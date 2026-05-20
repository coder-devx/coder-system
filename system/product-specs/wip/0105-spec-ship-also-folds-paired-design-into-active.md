---
id: 0105
title: Spec ship also folds the paired design into active/
type: spec
status: wip
owner: ro
created: '2026-05-20'
updated: '2026-05-20'
last_verified_at: '2026-05-20'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- task-orchestration
- knowledge-api
- admin-panel
- architect-worker
parent: pipeline-operations
---

# Spec ship also folds the paired design into active/

**Phase:** wip
**Progress:** 0 / 6 acceptance criteria

## Problem

AGENTS.md rule 5 says "When a WIP spec/design ships, its content is merged into active/". The orchestrator partially honors this: when an operator approves a ship gate, the PM ship-draft generates merges for the **spec** body only and the ship endpoint folds the spec WIP into `active/`. The paired **design** WIP — drafted alongside the spec by the architect and carrying mermaid diagrams / schemas / file:line refs / invariants the spec body deliberately doesn't carry — is left orphaned in `wip/` with `implements_specs` pointing at the numeric ID that no longer resolves.

Observed today (2026-05-20): eight specs shipped to `active/` (0075, 0077, 0079, 0080, 0089, 0091, 0096, 0099). All eight paired designs ended up in `system/designs/deprecated/` with a `deprecated_reason` noting "spec shipped, design never paired-shipped — re-author against the active surface if needed." The engineering content (architecture diagrams, data flow, invariants) became archived history rather than current-state context in `designs/active/`. Two older shipped specs (0088, 0094) follow a different but equally non-compliant pattern: their designs sit in `wip/` indefinitely after the spec ships.

The structural cause: there is no architect-side ship-draft workflow paralleling the PM ship-draft. The spec-run state machine tracks the **spec** WIP, dispatches PM tasks at each lifecycle stage, and emits a `ship_pending` gate against the spec only. Design merges are not generated and there is no `design-run` (or `design_ship_pending`) state. The `POST /knowledge/ship` endpoint accepts one WIP at a time (`wip_type: "spec" | "design"`) so even with hand-built merges, two ship calls would be needed per pair — but no one is generating the design-side merge body.

The consequence: `designs/active/` falls behind `product-specs/active/`. An architect picking up a fresh task and reading `designs/active/knowledge/admin-panel.md` does not see today's Studio sidebar / Idea Queue / WorkerKnowledgeReadsPanel / TimeoutCallout engineering decisions. The "active design = current truth" invariant breaks silently every ship.

## Users / personas

- **Pipeline operators** approving a ship gate from the admin Now feed — today they only see and act on the spec ship; the design ship is invisible.
- **Architects** drafting designs on freshly-dispatched tasks — they read `designs/active/` to ground in current-state engineering and silently miss decisions that landed since the corresponding spec shipped.
- **Future-self operators** auditing "where is the design for active spec X?" — today the answer is "in deprecated/ or wip/ under a stale numeric ID" rather than "in designs/active/ at the matching subject slug."

## Goals

- A single ship-gate approval folds **both** the spec WIP and the paired design WIP into `active/` atomically, in one operator action.
- The architect generates design-side ship merges in a parallel ship-draft task, the same way the PM does for spec merges today.
- The spec-run lifecycle tracks design ship state (or surfaces it as a paired sub-state) so the Now feed reflects the true completion.
- Backfill path: an operator action that, for an already-shipped spec, generates the missing design merges and ships them retroactively (for the 8 designs deprecated today + 2 designs in wip/).

## Non-goals

- Changing AGENTS rule 5 itself — the rule is right; the orchestrator implementation is the gap.
- Adding a third artifact type (ADR, etc.) to the ship flow — ADRs are append-only (AGENTS rule 4) and don't ship-fold; this spec scopes to spec+design only.
- Changing the `POST /knowledge/ship` per-WIP API contract — the atomicity can be a thin wrapper or a new `POST /knowledge/ship-pair` endpoint; this spec captures the intent and lets the architect choose.

## Scope

**Architect ship-draft.** A new dispatcher task role (or a new mode of the existing architect role) that, given a `wip_spec_id` whose spec-run is at `ship_pending`, fetches the paired design WIP, reads the spec's ship-draft merges (so it knows the active spec targets), and generates analogous design-side merges targeting `designs/active/...`. Output shape mirrors the PM ship-draft: a JSON `result` with `merges: [{artifact_type: "design", artifact_id, action, patch}, ...]`.

**Paired-ship surface.** An operator-facing action that, given a `wip_spec_id`, ships **both** the spec merges and the design merges as a single transaction (sequential `POST /knowledge/ship` calls is fine if commits land back-to-back; a single `POST /knowledge/ship-pair` is fine too). Now-feed item shows one combined "Ship gate — NNNN" entry, not two.

**Spec-run state.** A new transition or sub-state representing "spec shipped, design pending" — or a state-machine rule that requires both shipped before the spec-run becomes terminal `shipped`. The current spec-run model treats `shipped` as "PM merges committed"; this spec extends `shipped` to mean "both spec and design content live in active/".

**Backfill verb.** A one-shot operator action (`POST /knowledge/ship-paired-design/{wip_spec_id}` or similar) that runs the architect ship-draft against a spec that has already shipped without its design. Used for the 10 outstanding cases (8 deprecated today + 0088 + 0094).

**Admin-panel surface.** The existing ship-gate row in the Now feed renders `+1 design` when a design merge is staged; the click-through detail view shows both spec and design merge previews side-by-side. The operator approves once and both fold.

## Acceptance criteria

- **AC1.** When an operator approves a ship gate for `wip_spec_id`, both the spec WIP file and the paired design WIP file (matched by `implements_specs == wip_spec_id`) are folded into `active/`. The two commits land back-to-back on `coder-system/main`; the WIP files are both deleted; `validate.py` passes after the second commit.
- **AC2.** The architect produces a design ship-draft task (analogous to the existing PM ship-draft) before the ship gate fires. The draft's `result` carries `merges` of `artifact_type: "design"` only; the spec-run's `current_task_id` reflects the pending architect step.
- **AC3.** A spec-run only reaches terminal `state: shipped` when BOTH the spec and the design have shipped. If the design ship-draft fails or rejects, the spec-run stays at `ship_pending` (sub-state `design_pending`) and the Now-feed entry surfaces "design ship blocked: <reason>" without losing the already-merged spec content.
- **AC4.** The Now feed renders one combined ship-gate entry per `wip_spec_id` (not two), and the click-through detail view shows the spec merges and the design merges side-by-side so the operator approves once.
- **AC5.** An operator backfill verb `POST /v1/projects/{id}/spec-runs/{wip_spec_id}/ship-paired-design` dispatches an architect ship-draft for the design portion of an already-shipped spec, lands it on next approval, and clears the orphan design from `deprecated/` (or `wip/`) by folding it into `designs/active/`. Runs cleanly against the 10 known outstanding cases: 0075, 0077, 0079, 0080, 0088, 0089, 0091, 0094, 0096, 0099.
- **AC6.** `designs/active/REGISTRY.md` and `designs/active/*` reflect every spec's engineering decisions within 24 hours of the spec ship — measured by an audit script that asserts each `active` spec has a paired `active` design with `implements_specs: [spec_subject_slug]`.

## Metrics

- Drift between `product-specs/active/*` and `designs/active/*`: target zero within 7 days of any ship.
- Operator-time per ship gate: should not exceed the current spec-only flow by more than one decision-click (the architect's merges are auto-generated; the operator's approval is one click for the pair).

## Open questions

- Should `POST /knowledge/ship` gain a `wip_type: "spec+design"` mode (single transactional call) or should the orchestrator just issue two sequential `wip_type: "spec"` and `wip_type: "design"` calls atomically from the server side? The latter is simpler but loses transactional rollback if the second call fails after the first commit lands. Architect to decide.
- For specs already shipped without a design (today's 10 cases), should the backfill architect generate merges from scratch (reading the active spec to infer what the design should describe) or from the deprecated/wip-bound design body (reading the original engineering content)? Both are doable; the latter preserves architect intent.
- Does the audit script for AC6 belong in `coder-system/scripts/` (alongside validate.py) or in `coder-core` as a metric endpoint? Architect to decide.

## Links

- Related specs: [task-orchestration](../active/pipeline/task-orchestration.md), [knowledge-api](../active/knowledge/knowledge-api.md), [admin-panel](../active/knowledge/admin-panel.md), [architect-worker](../active/workers/architect-worker.md)
- AGENTS rule 5 (the contract being broken): `AGENTS.md` §"Lifecycle" rule 5
- Surfaced 2026-05-20 by the PM-of-the-Coder-System (operator) review of 8 design-side gaps after a high-throughput ship day (8 specs in one session).
- Existing related work: [coder-core#306](https://github.com/coder-devx/coder-core/pull/306) hardened the ship endpoint's validators (co-batch cross-link awareness + active-body shape enforcement); this spec extends the surrounding *workflow* to cover the paired design fold.

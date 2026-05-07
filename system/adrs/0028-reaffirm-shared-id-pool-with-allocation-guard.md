---
id: "0028"
title: Reaffirm shared WIP id pool with mandatory dispatcher-injected allocation
type: adr
status: accepted
date: 2026-05-07
deciders: [ro]
supersedes:
superseded_by:
relates_to_designs: []
---

# ADR 0028 — Reaffirm shared WIP id pool, with a mandatory allocation guard

## Context

ADR [0026](./0026-shared-numeric-id-pool-for-wip-specs-and-designs.md)
established a single shared numeric ID pool across `wip/` specs and
`wip/` designs: a numeric ID names one roadmap item, and the same
number appears on the spec file and the design file when both exist.

On 2026-05-05 the spec-lifecycle coordinator dispatched architect
tasks for specs 0045 / 0047 / 0048 / 0062 as part of a backfill.
Three of the four architect outputs returned `id: "0068"` instead of
the spec id they were prompted with (a hand-cut design at 0068
poisoned the model's prior). This produced an invalid design at
`wip/0068-…md` that had to be reverted (PR #69), and four spec runs
had to be paused.

The defect was **not** the shared-pool decision — it was that the
coordinator's `dispatch_architect` path skipped the same prompt
enrichment the chained dispatcher does. The architect's
[design.md](../roles/software-architect/tasks/design.md) task
contract assumes a `# Run context` block carrying `Design ID` (when
chained) or `Next free design ID` (when unchained). The coordinator
sent a bare `design: NNNN` prompt, the run-context block was absent,
and the worker fell back to *inferring* an id instead of refusing.
The fallback heuristic landed on the same wrong number three times
out of four.

The shared pool isn't the problem. **Allowing the agent to allocate
an id at all** is the problem.

## Options considered

1. **Reverse ADR 0026 — go back to per-folder pools.** Doesn't fix
   the bug (the architect could still hallucinate a design id). Loses
   the "WIP 00NN names a roadmap item" property that PM grounding,
   roadmap entries, and cross-link mechanics depend on. Big migration
   for no causal gain.
2. **Switch to prefixed IDs (S0062 / D0062).** Same disambiguation
   value as separate pools; same lack of fix for the actual bug;
   ergonomic regression already rejected in ADR 0026.
3. **Reaffirm ADR 0026 and add an allocation guard (this ADR).**
   The id is *always* dispatcher-supplied. A worker that doesn't see
   the run-context allocation field must refuse to create a numbered
   file rather than invent one.

## Decision

Adopt option 3.

**The shared numeric pool from ADR 0026 stands as written.**

**Allocation guard.** A worker creating a new numbered `wip/` file
must use the id the dispatcher provided in the `# Run context` block
(`Design ID`, `Next free design ID`, or `Next free spec ID`).
Workers MUST NOT compute or guess a numeric id from prior files,
prompt history, or model priors. If the run-context block is missing
or omits the relevant id field, the worker MUST refuse the task with
a structured error (`reason: missing-allocation-context`) instead of
producing output. The refusal is the failure mode — a numbered file
written without dispatcher-supplied id is a bug.

**Dispatcher contract.** Every code path that dispatches a PM
`draft` task or an architect `design` task — chained, coordinator,
or one-shot — must inject the run-context block with the appropriate
allocation field. The chained dispatcher already does this; the
spec-lifecycle coordinator path was missing this enrichment as of
2026-05-05 and is treated as a bug to be fixed in coder-core.

## Rationale

- The bug surfaces a contract violation, not a numbering issue. A
  pool change won't prevent agents from inventing identifiers when
  the dispatcher leaves the slot empty.
- The shared-pool model is what the project actually uses for
  cross-linking, roadmap tracking, and the "WIP 00NN names a
  roadmap item" shorthand. Reversing it would invalidate every
  matched-pair WIP from the first dozen ships and force a permanent
  spec-id-vs-design-id disambiguator into every worker prompt.
- Refuse-on-missing-context is cheap to implement (one assertion in
  each task contract, one structured error code) and surfaces
  dispatcher gaps as visible task failures instead of silent
  bad-output ones.
- The fix bites the right surface: the dispatcher is where ids are
  allocated, so the dispatcher is where allocation must be
  guaranteed.

## Consequences

- **Positive:**
  - The 2026-05-05 failure mode (silent wrong-id design files)
    becomes a loud refusal instead.
  - ADR 0026 remains stable; no cross-link sweep, no roadmap
    renumbering.
  - The contract is symmetric: dispatcher allocates, worker
    consumes — no overlap, no fallback.
- **Negative:**
  - One-time edits to `roles/product-manager/tasks/draft.md` and
    `roles/software-architect/tasks/design.md` to spell out the
    refusal-on-missing-context rule.
  - Every dispatcher path needs an audit. The chained dispatcher
    is correct today; the coordinator's `dispatch_architect` is
    not (tracked in coder-core; this ADR doesn't fix code).
- **Follow-ups:**
  - Update the two task contracts above as part of this change
    (knowledge side).
  - Track the coder-core coordinator fix separately. This ADR
    does not block on it: workers will already refuse cleanly,
    so the coordinator gap surfaces as failed tasks instead of
    poisoned files.

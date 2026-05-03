---
id: "0026"
title: Shared numeric ID pool for WIP specs and designs
type: adr
status: accepted
date: 2026-05-03
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: []
---

# ADR 0026 — Shared numeric ID pool for WIP specs and designs

## Context

[AGENTS.md](../../AGENTS.md) rule 6 says:

> WIP specs and designs use zero-padded 4-digit IDs aligned with the
> roadmap. Look at the highest existing WIP + deprecated ID before
> assigning a new one. Numeric IDs are never reused.

The rule does not explicitly say whether `wip/` IDs are pooled across
specs and designs or allocated per-folder. Historical behaviour was
pooled — every numbered WIP in the project's first dozen ships had a
spec file *and* a design file with the same number, both describing
the same roadmap item (0029 prompt-caching, 0030 model-tier-routing,
…). A reader saying "WIP 0029" meant one roadmap item with a
spec/design pair.

Recently the convention drifted:

- **Spec-only WIPs.** 0058–0061 (deleted in PR #54) were duplicate
  Slack-paging specs with no design siblings.
- **Design-only WIPs.** 0057 (`role-prompt-knowledge-layout`) and
  0062 (`navigation-tree-pattern`) have no spec sibling — they're
  pure-engineering work.
- **Same-number / different-topic.** As of 2026-05-03, spec 0062
  (`actionable-pipeline-stuck-slack-notifications`) and design 0062
  (`navigation-tree-pattern`) coexist on completely unrelated
  topics, allocated independently a day apart. Same shape with spec
  0063 vs design 0063.

A reader saying "WIP 0062" can no longer disambiguate without
specifying which folder. PM and Architect workers grounded on
"prior precedent for 0062" would consult the wrong file half the
time.

## Options considered

1. **Per-folder pools (status quo).** `wip/` specs and `wip/` designs
   are independent allocations. Pros: zero migration cost. Cons: the
   "WIP 00NN" shorthand is ambiguous; a roadmap-item tracker has to
   carry both `(spec_id, design_id)` to point at one item; humans
   have to know the prefix.

2. **Single shared pool (this ADR).** A numeric ID names one
   roadmap item. That item has 0–1 spec file *and* 0–1 design file,
   both numbered the same. New WIPs pick the next free number from
   `max(spec, design, deprecated)` across both folders. Pros:
   restores historical convention; "WIP 0029" unambiguously names
   a roadmap item; the design's `implements_specs` cross-link
   collapses to "same number". Cons: requires renumbering the two
   recent collisions (design 0062, design 0063) and updating
   cross-links.

3. **Add a folder prefix to all IDs.** `S0062` for specs, `D0062`
   for designs. Pros: ambiguity gone forever. Cons: inconsistent
   with every other ID in the system (ADRs, services, repos, …),
   visually noisy, and IDE / grep tooling has to learn the
   convention.

## Decision

**Option 2.** WIP specs and designs share one numeric ID pool. New
WIPs pick the next free number from
`max(specs/wip, designs/wip, specs/deprecated, designs/deprecated) + 1`.
Same-numbered spec + design files describe the same roadmap item;
design's `implements_specs: ['<id>']` matches spec's `id`. A WIP
exists with only a spec, only a design, or both — never two
unrelated files at the same number.

[AGENTS.md](../../AGENTS.md) rule 6 is amended to make the pool
shared explicitly.

## Rationale

- This is what the project actually did for the first dozen ships.
  We're naming the convention, not inventing it.
- The "WIP 00NN names a roadmap item" mental model is what humans
  and PM workers already use. The shared pool makes that shorthand
  resolvable.
- Cost is bounded: one ADR, one rule edit, two file renumbers, and
  cross-link updates in two design frontmatter blocks. No active-
  side work, no test changes.
- Per-folder pools would require either prefixed IDs (option 3,
  ergonomic regression) or a "spec-id vs design-id" disambiguator
  threaded through every roadmap entry, every ADR cross-reference,
  every PM-worker prompt — forever.

## Consequences

- **Positive:**
  - "WIP 0029" / "WIP 0046" remains an unambiguous handle.
  - PM-worker grounding on prior WIPs no longer hits the
    same-number-different-topic trap.
  - Roadmap entries continue to carry one ID per item.
  - Cross-link `design.implements_specs == spec.id` is mechanical:
    same number.
- **Negative:**
  - Renumbering design 0062 → 0066 and design 0063 → 0067 (lowest
    free numbers above the current max) requires a one-time
    cross-link sweep. Done in the same PR as this ADR lands.
- **Follow-ups:**
  - When allocating a new WIP, the PM / Architect worker prompt
    should read the highest existing ID across both folders. The
    `roles/<role>/tasks/draft.md` and `architect.md` task contracts
    should explicitly mention this. Tracked separately.

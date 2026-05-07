---
id: "0030"
title: INDEX preload scope is authoring roles only (PM + Architect)
type: adr
status: accepted
date: 2026-05-07
deciders: [ro]
supersedes:
superseded_by:
relates_to_designs: [navigation-tree-pattern]
---

# ADR 0030 — INDEX preload scope is authoring roles only (PM + Architect)

## Context

ADR [0029](./0029-unified-generated-knowledge-index.md) established
a single unified `system/INDEX.md` and said *"workers preload
`system/INDEX.md` regardless of role; cross-cutting work (Reviewer
needing both views) costs zero extra round trips."* It motivated the
change in part by citing the Reviewer's pre-merge friction:
*"Cross-cutting decisions (a Reviewer noticing a missing spec while
gating a design) require a second fetch."*

Post-merge reality (2026-05-07):

- Only **PM** and **Architect** task contracts inject the INDEX
  preamble (`_common.md`, plus PM modes `draft`/`ship`/`audit`/`accept`
  and Architect modes `design`/`ship`).
- **Reviewer** task contract explicitly states: *"The Reviewer does
  not get an INDEX preload — the work is grounded [in the PR
  diff]."*
- **Team-Manager** task contract explicitly states: *"not preload
  an INDEX or the spec body."*
- The `coder-core` dispatcher gates the preload on a hardcoded set:
  `_ROLES_WITH_INDEX_PRELOAD = frozenset({"pm", "architect"})`.

So the implementation is narrower than ADR 0029's prose. There are
two ways to resolve the gap: extend the preload to Reviewer + TM
(matching ADR 0029's prose), or document that the preload is
intentionally scoped to authoring roles (matching the ADR-0029-era
implementation). This ADR takes the second path.

## Options considered

1. **Extend INDEX preload to Reviewer + Team-Manager.** Matches
   ADR 0029's prose. Costs: a per-task fetch (~few hundred tokens
   from cache) on every review and every decomposition, even though
   most of those tasks need only the artifact at hand. The
   "cross-cutting decision" Reviewer scenario the ADR cited is
   real but rare; an INDEX-equipped Reviewer that doesn't actually
   navigate the tree pays the cache-write cost for nothing.
2. **Drop INDEX preload entirely; let every role fetch on demand.**
   Eliminates the gap by levelling everyone down. Penalises PM and
   Architect, who genuinely traverse the tree to assign `parent:`
   on new artifacts.
3. **Codify the as-built scope: PM and Architect only (this ADR).**
   The INDEX is grounding for *authoring* — picking the right
   `parent:`, surveying neighbouring components, deciding whether
   to extend a category or open a new one. Roles that don't author
   new artifacts (Reviewer reviews one diff; Team-Manager
   decomposes one spec into per-stage developer tasks) don't need
   the map; they need the artifact body, which they already
   receive.

## Decision

Adopt option 3.

**INDEX preload scope.** `system/INDEX.md` is preloaded as a
`run_context` section for **authoring** workers only:

- PM in modes: `draft`, `ship`, `audit`, `accept`.
- Architect in modes: `design`, `ship`.

It is **not** preloaded for Reviewer (`review`), Team-Manager
(`decompose`), or Developer (`implement`). Those roles operate on a
fixed artifact (the PR diff, the spec body, the task brief) the
dispatcher provides via other preamble sections.

**Authoritative source.** The dispatcher's
`_ROLES_WITH_INDEX_PRELOAD` constant in
`coder_core.workers.dispatcher` is the single point of enforcement.
This ADR is the knowledge-side anchor; any change to that constant
must update this ADR and re-link the affected task contracts.

**Cross-cutting case.** When a Reviewer or Team-Manager genuinely
needs to navigate the index (e.g. a reviewer flags that a
component lacks an active spec), they fetch `system/INDEX.md` via
`gh api` like any other knowledge file. The fetch is rare;
preloading on every task to cover the rare case is the wrong
trade-off.

## Rationale

- **The INDEX is a navigation map, not a context dump.** Authoring
  workers traverse it to place new content. Review/decompose
  workers operate on a single artifact whose `parent:` is already
  stamped by an authoring worker upstream — the navigation work
  has already happened.
- **Cache-write cost is not free.** Adding ~100 lines × every
  review and decomposition adds up; the same cache slot is better
  spent on the diff or the spec body for those roles.
- **The constraint is auditable.** With the scope spelled out here
  and gated by a single dispatcher constant, knowledge-vs-code
  drift is detectable: a contract change that adds an "INDEX
  preload" hint to a non-authoring role's task contract should
  fail review against this ADR.
- **ADR 0029's prose overshot the as-built decision.** This ADR
  refines that scope without reversing the unified-index direction
  — INDEX is still one file for the whole system, still drift-checked,
  still rendered from `parent:` + `summary:`. What changes is who
  the dispatcher hands it to.

## Consequences

- **Positive:**
  - Reviewer and Team-Manager task contracts stay stable; their
    "no INDEX preload" stance is policy, not oversight.
  - The hardcoded `_ROLES_WITH_INDEX_PRELOAD` set has a
    knowledge-repo home — future edits land in lockstep.
  - Cache-write cost stays scoped to where the INDEX is actually
    used.

- **Negative:**
  - The cross-cutting case ADR 0029 cited (a Reviewer flagging a
    missing spec) costs one explicit `gh api` fetch instead of a
    preload-paid-for "for free" lookup. Acceptable: the
    motivating scenario is rare in practice and the fetch is a
    single tool call.

- **Follow-ups:**
  - **coder-core**: add an info-level log line on
    `system/INDEX.md` 404 inside `_read_optional_file` (today the
    404 path is silent). Managed-project bootstrap that hasn't
    generated the unified INDEX should surface as a visible
    "preload skipped" event instead of a silent missing
    `## Knowledge index` section in the worker prompt. Tracked
    separately; this ADR doesn't block on it.
  - **coder-core**: surface a metric for `_preload_index` cache
    misses (None returns) so a managed project running with no
    INDEX is visible from the admin panel.
  - Consider mirroring `scripts/render_index.py` (and the
    validator's drift check) into `template/` so a managed project
    bootstrapped from the template can regenerate the INDEX
    without copying the system repo's tooling.

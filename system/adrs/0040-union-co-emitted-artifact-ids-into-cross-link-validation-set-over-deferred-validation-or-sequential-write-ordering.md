---
id: '0040'
title: Union co-emitted artifact IDs into cross-link validation set over deferred
  validation or sequential write ordering
type: adr
status: proposed
date: '2026-05-15'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- '0076'
---

# ADR 0040 — Union co-emitted artifact IDs into cross-link validation set over deferred validation or sequential write ordering

## Context

When the architect produces a design and one or more ADRs in a single response, Phase 4 writes each artifact via `commit_artifact`, which validates outbound cross-links against the live registry. The design's `decided_by` field references the co-emitted ADR's id — but that ADR is not yet in the registry at the time the design is checked. Every architect response that introduces new ADRs fails `broken_cross_link` on the design, dropping all artifacts. The fix must keep the early-validation guarantee (don't let hallucinated links through) while allowing same-response artifact references to resolve.

## Options considered

**Option A — Sequential write ordering.** Write ADRs before the design so that by the time the design is checked, ADRs are in the registry. Requires Phase 4 to infer or declare a dependency order among co-emitted artifacts. Fragile: new cross-link field combinations (e.g. an ADR referencing a design in `relates_to_designs`) invert the order; the logic would need to topological-sort an arbitrary dependency graph.

**Option B — Defer cross-link validation to ship time.** Remove the write-time check; validate only at `/ship`. Preserves the happy path but allows hallucinated cross-links to persist through the entire development cycle (spec draft → design → developer tasks) and surface only at the operator-triggered ship gate. Contradicts the design goal of the 0076 cross-link checker, which was added precisely to surface these early.

**Option C — Union co-emitted IDs into the known set (chosen).** Before iterating the artifact list, Phase 4 collects all artifact IDs from the worker response into a `batch_known` dict keyed by type. Each `commit_artifact` call receives `batch_known` and unions it with the registry-derived `target_known` set before checking cross-link refs. Co-emitted IDs are treated as known; all other validation is unchanged.

## Decision

Option C — add `batch_known: dict[str, set[str]] | None` to `commit_artifact` and populate it from the current architect response's artifact list in Phase 4.

## Rationale

Option C is scope-limited: only IDs that appear in the same worker response get the trust extension; arbitrary non-existent IDs still fail. It requires no graph analysis, no write ordering, and no change to the ship-time validator. The early-validation guarantee is preserved for hallucinated links — only genuine co-emitted references are exempted. Option A's topological-sort complexity grows with every new cross-link field added to the schema. Option B would silently regress the write-time gate added to catch broken links before they accumulate.

## Consequences

- Phase 4 architect writer must build `batch_known` before iterating, adding one pass over the response artifact list (negligible cost).
- `commit_artifact` callers that do not supply `batch_known` (all existing non-architect paths) are unaffected — the parameter defaults to `None` and the union branch is skipped.
- An architect response that intentionally references an ADR from a *prior* response (already in the registry) continues to resolve correctly via the registry-derived set.
- Audit: `knowledge.create` events for co-emitted artifacts are still emitted individually, so the audit log remains artifact-granular.

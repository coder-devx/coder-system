---
id: "0022"
title: Structural Jaccard similarity as the v1 pattern-discovery mechanism
type: adr
status: proposed
date: 2026-04-28
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: ['0048']
---

# ADR 0022 — Structural Jaccard similarity as the v1 pattern-discovery mechanism

## Context

Design 0048 needs a mechanism to find "this decision / this problem
statement has appeared in multiple projects." The mechanism must
produce a `pattern_groups` table row linking the matching artifacts
across projects. The constraints from the spec are:

- **Cheap** — computed offline (daily Cloud Run Job, not per-request).
- **Deterministic** — the same knowledge snapshots must always
  produce the same groupings (per AC6).
- **Auditable** — an operator must be able to open a group and
  understand *why* these two ADRs were matched without reading a
  model explanation.
- **No LLM spend** — ADR 0014 rejected LLM-based freshness scoring
  for the same cost and opacity reasons; those reasons apply here too.

Four mechanisms were evaluated:

1. **Manual operator annotation** — operators tag each ADR/spec with
   a fleet-scope "pattern label" that the indexer uses to group members.
2. **Structural Jaccard on title/problem tokens** — tokenise and
   compute bag-intersection similarity; group when score ≥ threshold.
3. **LLM-based semantic similarity** — embed artifact bodies, cluster
   in vector space, surface clusters as pattern groups.
4. **Audit-emitted hints** — workers tag their own output with
   "this decision resembles pattern X"; the indexer reads these tags
   to form groups.

## Options considered

1. **Manual annotation.** Operators know their fleet and could
   annotate with precision. Pros: zero false positives (human
   labelled), rich labels. Cons: does not scale; requires the fleet
   to be large and operators to have already surveyed it cross-project
   (the very problem 0048 is trying to solve). The bootstrapping
   paradox — you need the surface to find patterns, but you need to
   know the patterns to build the surface — makes this a dead end for
   the initial fleet.

2. **Structural Jaccard (this ADR).** Tokenise the artifact's
   decision-bearing text (ADR title, spec `## Problem` paragraph);
   compute Jaccard on token bags; group transitively where score ≥
   configurable floor. Pros: deterministic, zero LLM cost, auditable
   (operator can reproduce the score manually), floor is a single
   config knob. Cons: vocabulary-sensitive (two ADRs that make the
   same decision in different words may not group); requires threshold
   tuning per fleet size.

3. **LLM-based semantic similarity.** Embed artifact bodies; group by
   cosine similarity in embedding space. Pros: handles
   paraphrasing and vocabulary divergence. Cons: embeds must be
   refreshed on every artifact change; embedding calls cost money at
   scale; the score is opaque (ADR 0014 rejected this for freshness;
   same rationale applies here — a similarity of 0.81 cannot be
   explained to a operator without a narrative). Also contradicts the
   spec's non-goals ("No embedding store, no LLM-as-similarity").

4. **Audit-emitted hints.** Workers tag their own output with pattern
   labels; the indexer reads those tags. Pros: high precision when
   workers are active. Cons: chicken-and-egg — the surface only grows
   after workers have been using it for weeks. The bootstrapping value
   is zero on day 1 when the fleet has 2 projects and no prior worker
   consultations.

## Decision

Adopt **option 2 — structural Jaccard** as the sole v1 discovery
mechanism. v1 floors: 0.5 for `adr` title tokens, 0.4 for
`spec_problem` first-paragraph tokens. A threshold-tuning runbook
documents the spot-check protocol for each fleet-size milestone.

## Rationale

**Determinism and auditability.** Jaccard on a token bag is a
two-line formula. An operator can open two ADRs, compute the overlap
by hand, and reproduce the score. This property is load-bearing for
operator trust in the surface: a group that is hard to explain is a
group that will be ignored.

**No new infrastructure.** Option 3 requires an embedding model, a
vector store per project, and refresh triggers on every commit.
Option 4 requires a round-trip of worker activity before any value
accrues. Option 2 requires only a tokeniser and a set-intersection
function — both ship inside the indexer module with no external
dependencies.

**Alignment with ADR 0014.** The freshness design explicitly rejected
semantic similarity because of cost, opacity, and the risk of noisy
signals. Adopting it here for discovery would create an inconsistency
in how the system treats similarity across the knowledge surface.

**Acceptable miss rate for v1.** Vocabulary divergence (the Jaccard
blind spot) is unlikely to be severe within a small fleet where the
same operator wrote both ADRs. With 2 projects, any false-negative
group is observable by a manual review — and the threshold tuning
runbook provides the correction loop. At larger fleet sizes, if the
miss rate becomes material, option 3 can be added as a secondary
signal behind the same interface without changing any consumer code.

## Consequences

- **Positive.** Discovery is fully deterministic and requires no
  external model calls.
- **Positive.** The threshold is a single config knob; tuning is a
  PR + runbook entry.
- **Positive.** No embedding store, no LLM budget line for the
  indexer.
- **Negative.** Vocabulary divergence (two ADRs making the same
  decision in different words) produces false negatives. Mitigated
  by the threshold-tuning runbook and operator spot-checks.
- **Negative.** Initial floors (0.5/0.4) are hand-calibrated and
  will need adjustment as the fleet grows. The runbook documents
  this explicitly.
- **Follow-up.** If the citation rate KPI (fraction of worker
  outputs that cite a returned pattern) stays below 10% after
  tuning, re-evaluate whether LLM-assisted discovery should be
  added as a *secondary* signal. This would require a separate ADR.

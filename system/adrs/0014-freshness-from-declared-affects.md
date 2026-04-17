---
id: "0014"
title: Knowledge freshness derives from declared affects, not semantic similarity
type: adr
status: accepted
date: 2026-04-17
deciders: [ro]
relates_to_designs: ["0043"]
---

# ADR 0014 — Knowledge freshness derives from declared affects, not semantic similarity

## Context

Spec 0043 asks for a per-artifact freshness score so the Knowledge
API, the Architect worker, and the admin panel can tell fresh content
from rot. The score needs to be:

- **Deterministic** — two reads at the same repo HEAD produce the
  same score, so callers can cache and compare across days.
- **Cheap** — computed on every Knowledge API read without
  calling out to a model or a vector store.
- **Auditable** — an operator can look at the number and explain
  it from inputs already in the repo.
- **Defensible when wrong** — a false "stale" reading should be
  traceable to a specific declared field, not to a model's opinion.

Artifacts today already declare their connection to code via
`affects_services`, `affects_repos`, and cross-link fields
(`depends_on`, `related_designs`, `implements_specs`, etc.). Those
declarations are the mechanism by which the repo claims to "cover"
a part of the real system.

## Options considered

1. **Derive freshness from declared `affects_*` and cross-links
   (this ADR).** Score = weighted sum of age-since-verify, commit
   activity in declared targets since verify, and transitive
   dependency freshness. Pure function of repo + git state.
2. **Semantic similarity between the artifact body and the code it
   covers.** Score drops as embeddings drift. Requires an embedding
   model, a vector store per project, and re-embedding on every
   code change.
3. **LLM-graded freshness.** Send the artifact + the code diff since
   verify to a model and ask "is this still accurate?" Run on a
   schedule; cache the verdict.
4. **Explicit decay only** — freshness is purely age-based, with no
   activity or dependency signal. Simple, but indistinguishable from
   "no signal at all" for quiet subsystems.

## Decision

Adopt **option 1 — derive freshness from declared `affects_*` and
cross-links**. `FreshnessService.score(artifact)` is a pure function
of the artifact's `last_verified_at`, commit activity in the paths
it declares, and the `min` freshness of its declared dependencies.
No model call. No embedding index. No out-of-repo state.

## Rationale

**Determinism and audit.** A score computed from declared fields
and git is reproducible, diffable, and explainable. When an
artifact scores 42 we can point at the specific commit(s) to the
declared `affects_service` that pulled the score down. An embedding
score of 0.61 cannot be defended the same way — the operator asks
"why?" and the honest answer is "the embedding says so".

**Cost.** The Knowledge API is read on every worker turn. Option 1's
score is cents-per-read (git metadata + a registry walk). Option 2
adds an embedding lookup per read and an index refresh per code
commit; option 3 adds an LLM call. Both options change freshness
from a property-of-reads into a cost center.

**Alignment with existing discipline.** The repo already requires
`affects_*` fields, and 0043's back-fill migration surfaces the
artifacts that don't declare them. This ADR makes those fields
load-bearing, which reinforces a discipline we already want:
artifacts that can't name what they cover are artifacts we cannot
trust to cover anything. Option 2 accidentally rewards artifacts
that don't declare their scope — if the embedding sees the code,
it doesn't care whether the artifact admitted which code.

**Noisy alternatives are worse than silent ones.** A semantic-
similarity score swings on wording changes that don't affect
correctness (renaming a variable in the code, rewriting a design's
prose for clarity). Every false-positive "stale" reading trains
the operator to ignore the score. A declared-field score is quieter
but more trustworthy — and 0043's audit loop compensates for its
blind spots by re-verifying on a schedule.

**Escape hatch.** The three-term weighted sum is revisitable in a
single config block (`freshness/weights.py`). If after a quarter of
use we find the score is systematically wrong, we can:
- tune the weights,
- add a fourth term (e.g. a per-project "last audit verdict" signal),
- or, as a last resort, replace the service with one of options 2/3
  behind the same interface. No reader code changes.

## Consequences

- **Positive.** Score is cheap, deterministic, and explainable.
  The admin badge can show *why* an artifact is stale ("commit
  activity in coder-core since 2026-03-20") without a narrative
  summary from a model.
- **Positive.** `affects_*` becomes load-bearing, which pushes
  artifact authors to declare what they cover — a discipline that
  also helps spec 0046 (graph-aware retrieval).
- **Positive.** No new infrastructure. No vector store, no
  embedding model, no LLM budget line.
- **Negative.** Artifacts that lie (or omit) in their `affects_*`
  declarations get an artificially high score. Mitigated by the
  audit loop, which re-reads the artifact against real code; a
  `needs_rewrite` verdict exposes a bad declaration.
- **Negative.** Doc-only prose drift (a spec that describes a
  behaviour the code never actually implemented) is invisible to
  the signal. Accepted — that is what the nightly Architect audit
  exists to catch.
- **Negative.** Weights are a judgement call and the first set
  (`0.3/0.5/0.2`) is a guess. Calibration requires a week of
  shadow data. Not a long-term cost, but the first month's scores
  are noisier than the steady state.
- **Follow-up.** If the audit's `needs_rewrite` rate stays high
  after weight calibration, that's the signal to add option 3's
  LLM-graded path as a *secondary* input — not a replacement —
  into the same weighted sum.

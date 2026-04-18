---
id: "0015"
title: Ship gate lives in the Coder pipeline, not in GitHub branch protection
type: adr
status: accepted
date: 2026-04-17
deciders: [ro]
relates_to_designs: [knowledge-write-api, team-manager-worker, architect-worker]
---

# ADR 0015 — Ship gate lives in the Coder pipeline, not in GitHub branch protection

## Context

Spec 0044 adds a "ship gate": a step that refuses to complete a
cycle until the shipping WIP's content has been merged into
`active/` atomically, with a Reviewer attestation matching every
acceptance criterion. The gate has to live somewhere. Two obvious
places:

1. **In the Coder pipeline**, as a ship stage that runs after the
   developer PR merges and before Team Manager closes the cycle.
   Enforced by coder-core + coder-admin.
2. **In GitHub branch protection**, as a required check (e.g. a
   GitHub Action that fails if a WIP file is deleted without a
   matching `active/` edit, or as a required review from a
   "coder-ship" bot).

Both could work. The difference matters for blast radius, operator
mental model, and future evolution.

## Options considered

1. **Gate in the Coder pipeline (this ADR).** The ship endpoint
   (`POST /v1/projects/{id}/knowledge/ship`) is the only sanctioned
   path. The admin panel's pipeline view shows the Ship gate with
   the merges and attestation, and the operator approves or rejects
   there. Team Manager's close-cycle call is the backstop.
2. **Gate in GitHub branch protection.** A required status check
   on the default branch that parses the PR diff, looks for WIP
   deletes, and fails if there's no matching `active/` edit. The
   check could also require a specific reviewer label
   (`ship-attested`).
3. **Both.** Pipeline gate for the normal path; branch protection
   as a belt-and-suspenders last line of defense. More checks is
   nominally safer.

## Decision

Adopt **option 1 — gate in the Coder pipeline**. GitHub branch
protection continues to enforce the ordinary PR merge requirements
(required checks, CODEOWNERS) and is **not** extended with a
ship-specific rule. The admin-panel ship gate plus the Team Manager
close-cycle check are the only enforcement points.

## Rationale

**Ownership.** Coder is the system that knows what a "WIP ship"
means — which WIP correlates to which developer task, which
`active/` files are candidates, which Reviewer is authorised to
attest. Encoding that logic in a GitHub Action duplicates it
outside the system that owns it, which means it drifts. The
pipeline gate stays in one place with one test suite.

**Blast radius of false positives.** A branch-protection check
that blocks merges based on WIP state would affect *every* PR
touching the knowledge repo, including ones that have nothing to
do with a WIP ship (template edits, runbook additions, glossary
fixes, ADR appends). The logic to distinguish "this PR ships a
WIP" from "this PR is an unrelated edit" exists in the Coder
pipeline's task state, not in the PR diff alone. Putting the
check at the PR layer forces us to re-derive pipeline state from
file paths — brittle and prone to false blocks.

**Reviewer identity.** The Reviewer worker is authenticated in
the Coder system (per-role service account, ADR 0006). Encoding
"a valid attestation requires a coder-core-authenticated reviewer"
in GitHub terms would require provisioning a GitHub App, teaching
it to sign attestations, and teaching branch protection to verify
the signature. Heavy for the value.

**Rejection semantics.** The spec allows rejecting a ship
*after* the PR has merged — the code is live, only `active/`
lags. A branch-protection gate cannot reject a post-merge ship;
the merge has already happened. The pipeline gate runs
post-merge by design (`knowledge-ship-draft` dispatches when the
developer task closes), and the rejection loop is native to it.

**Backstop depth.** The pipeline gate is the primary check;
Team Manager's close-cycle step is a structural backstop that
catches anything that slipped past. Two checks, one system. Adding
branch protection makes three checks across two systems — and
three checks in two systems is not meaningfully safer than two in
one, given the two are both correctness-critical.

**Operator mental model.** A single system owning the gate means
a single place where the operator can debug a block. "Why didn't
my cycle close?" → one view, one error. A GitHub status check
block surfaces in the PR UI, which the operator reaches via a
different path than the admin panel they already have open.

## Consequences

- **Positive.** All ship logic lives in one system with one audit
  trail. Pipeline state is the source of truth for "is this WIP
  shippable".
- **Positive.** Branch protection stays simple. No GitHub App,
  no signed attestations, no out-of-band status check to maintain.
- **Positive.** Rejection after PR merge is representable.
- **Positive.** The Reviewer worker's 0025 schema loop already
  retries on shape errors — the gate inherits that guarantee for
  free.
- **Negative.** A human who bypasses the pipeline and hand-merges
  a PR that deletes a WIP file is not stopped by the gate. The
  close-cycle backstop catches the resulting orphan, but it's
  post-hoc. Mitigated by the pipeline being the only sanctioned
  path for ship-time changes; the runbook is explicit.
- **Negative.** If the pipeline itself is down, ship is also
  blocked. Acceptable: a pipeline outage already blocks worker
  work, and ship is a worker-driven step.
- **Follow-up.** If the hand-merge-bypass pattern shows up in the
  orphan-WIP metric more than once, we'll reconsider adding a
  narrow branch-protection rule (specifically: reject deletes of
  `wip/00NN-*.md` unless accompanied by a matching `active/`
  edit in the same PR — easier to scope than a full ship check,
  and complementary to option 1, not a replacement).

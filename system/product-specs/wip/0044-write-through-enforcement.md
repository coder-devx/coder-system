---
id: "0044"
title: Write-through enforcement on ship
type: spec
status: wip
owner: ro
created: 2026-04-17
updated: 2026-04-17
last_verified_at: 2026-04-17
served_by_designs: ["0044"]
related_specs: [knowledge-api, reviewer-worker, team-manager-worker, architect-worker, admin-panel, task-orchestration]
---

# Write-through enforcement on ship

## Problem

AGENTS.md rule 5 says: when a WIP spec or design ships, its content
is **merged into `active/`** by updating existing component files
and/or creating new ones, and the numbered WIP file is **deleted**.
History lives in git, not in filenames.

Today this is a human discipline, and humans miss it. The failure
mode is silent: the code ships, the PR merges, the WIP file lingers,
the `active/` component file still describes pre-ship behaviour. Two
weeks later the Architect worker plans against an active design that
omits the feature that just shipped, and the operator wonders why
the plan "doesn't make sense."

It looks like freshness rot (spec 0043), but the cause is distinct:
it's a skipped step at ship time, not ambient decay. Every skipped
merge makes the repo *actively* misleading rather than just *stale*.

Both the motivation and the fix belong inside the role contract.
The Reviewer gate — already the last checkpoint before ship — is the
right place to refuse a close-out that leaves `active/` lagging. The
Team Manager's cycle-close step is the backstop.

## Users / personas

- **Reviewer worker** — gains a new responsibility: attest that
  every acceptance criterion from the shipping WIP has a home in
  `active/` (edited or created) before approving the ship.
- **Team Manager worker** — refuses to mark a cycle complete while
  any of its WIPs remain un-merged into `active/`.
- **Architect worker** — drafts the wip-to-active merge patch as
  part of the ship task, so a reviewer has something concrete to
  attest against.
- **Operator** — trusts that `active/` reflects shipped reality,
  not "shipped minus last month's WIPs."

## Goals

- Shipping a WIP is an atomic, reviewable event: one commit that
  (a) creates or edits the relevant `active/` artifacts, (b) deletes
  the numbered WIP file, and (c) updates both folders' registries.
  No partial ship state is representable on disk.
- The Reviewer worker's output schema requires a
  `ship_attestation` block. For every AC on the shipping WIP, the
  attestation names an `active/` artifact and a section that now
  covers it, or explicitly marks the AC as dropped with a reason.
- Team Manager's close-cycle path refuses to close with WIPs whose
  underlying feature has shipped (developer task closed + PR merged)
  but whose spec is still in `wip/`. Structured error points to the
  offending WIP ids.
- A once-off back-fill identifies WIPs whose code has already
  shipped but that never merged into `active/`, and queues them for
  remediation.

## Non-goals

- Not automating the merge content. A human or the Architect worker
  decides *how* WIP content folds into `active/`; this spec
  enforces that the fold *happens*, atomically and attested.
- Not rewriting the AGENTS.md rule itself — this spec operationalises
  it. The rule stays authoritative.
- Not covering deprecations. An active artifact moving to
  `deprecated/` follows a separate path (see AGENTS.md rule 5, last
  bullet). No attestation required.
- Not blocking the PR merge in GitHub. The gate lives in the Coder
  pipeline's ship stage, not in GitHub branch protection. Keeps the
  concern in one system.

## Scope

**In:**

- Knowledge API: `POST /v1/projects/{id}/knowledge/ship` with body
  ```
  {
    "wip_id": "0043",
    "wip_type": "spec" | "design",
    "merges": [
      {"artifact_type": "spec" | "design",
       "artifact_id": "<slug>",
       "action": "create" | "edit",
       "patch": "<unified diff or full body>"},
      ...
    ],
    "attestation": {
      "reviewer": "<actor-slug>",
      "acs": [
        {"ac": "<text>", "merged_into": "<artifact_id>", "section": "<heading>"},
        {"ac": "<text>", "dropped": true, "reason": "<text>"}
      ]
    },
    "commit_message": "<required>"
  }
  ```
  Endpoint runs in a single GitHub Contents commit covering every
  touched file and both affected registries; on any failure, nothing
  is written.
- Reviewer worker output schema (under spec 0025's umbrella) gains
  a required `ship_attestation` field. Reviewer workers refuse to
  produce a ship verdict without one.
- Team Manager's `close_cycle` step calls a new Knowledge API
  helper `GET /v1/projects/{id}/knowledge/wips?shipped=true` that
  lists WIPs whose underlying developer task is closed but whose
  spec still sits in `wip/`. Non-empty result blocks close with a
  structured `wips_pending_merge` error.
- Admin panel: pipeline run view grows a "Ship" gate distinct from
  the PR merge gate. The gate renders the merges and the attestation
  side by side; the operator can approve or reject just the
  knowledge-side of a ship.
- Back-fill script `scripts/find_orphan_wips.py` that flags WIPs
  where the correlated developer task is `closed` + PR `merged` but
  the WIP file still exists. Runs once, opens a `needs-merge` audit
  entry per hit so they're cleaned up deliberately.
- Runbook `runbooks/ship-wip-into-active.md` describing the
  Architect-drafted, Reviewer-attested, TM-closed path end to end.

**Out:**

- Automating which active artifact to touch. The Architect worker
  proposes; a human can override before attestation.
- Multi-WIP ship transactions. One WIP per `/ship` call; one commit
  each. Keeps the atomicity story simple.
- Back-porting the attestation to specs and designs already shipped
  before this change. The orphan-WIP back-fill covers the gap, but
  shipped-and-merged history doesn't get retrofitted attestations.

## Acceptance criteria

- [ ] `POST /v1/projects/{id}/knowledge/ship` exists, validates the
      body, performs the composite write in a single commit, and
      returns the new commit SHA and the list of touched paths.
- [ ] Any failure (malformed diff, cross-link violation, missing
      attestation AC, reviewer not authorised) leaves the tree
      unchanged. Verified by a test that injects a mid-commit error.
- [ ] Reviewer worker output schema includes `ship_attestation`;
      the worker refuses to approve ship without it. Covered by a
      re-prompt under spec 0025's schema retry loop.
- [ ] `GET /v1/projects/{id}/knowledge/wips?shipped=true` returns
      WIPs whose developer task is closed + PR merged but whose
      file still exists in `wip/`.
- [ ] Team Manager's close-cycle step blocks with a
      `wips_pending_merge` error when the query above returns
      non-empty.
- [ ] Admin panel pipeline view shows the Ship gate with merges and
      attestation; approve/reject buttons call through to `/ship`
      (on approve) or to a structured rejection audit entry.
- [ ] `scripts/find_orphan_wips.py` prints a report and (behind a
      flag) opens audit entries; run once across all projects as
      part of rollout.
- [ ] Tests:
      - attested ship with a valid merge → registry and tree match,
        wip file gone, active artifact updated, commit message
        present.
      - missing attestation AC → 400 with the specific AC flagged.
      - cross-link in the merge points at a non-existent id → 400,
        nothing written.
      - concurrent second `/ship` for the same WIP → 409.
      - close-cycle with orphan WIPs → structured block.

## Metrics

- **Primary:** count of active artifacts whose "last touched"
  commit lags behind their matching WIP's ship date by more than
  48 h. Target: 0 after rollout, monitored weekly.
- **Ship-gate latency:** time from developer-PR-merge to
  `/ship` commit. Target p95 < 30 min so the gate doesn't become
  the bottleneck. If it does, the Architect's drafting step needs
  tightening.
- **Attestation dropout rate:** share of attestations with any
  `dropped: true` AC. Low is good. A spike means either the
  Reviewer is being lazy or the spec ACs are being written
  unrealistically — either way, worth investigating.
- **Orphan WIPs discovered:** the back-fill count. One-time number
  for rollout; after that the gate should keep it at zero.

## Open questions

- **Ship-gate rejection semantics.** If a reviewer rejects just
  the knowledge merge, does the PR stay merged and we loop until
  the merge is acceptable, or do we require a compensating follow-up
  commit? First is simpler; second is cleaner. Decide during design.
- **Architect drafting vs operator drafting.** The first cut has
  Architect draft the merges and a human attest. For low-risk WIPs
  the Architect could also attest, with the operator only sampling.
  Deliberately out of scope for v1 until we trust the pattern.
- **Template changes as a WIP class.** When the schema itself
  changes (the `template/` blueprint), that is a different kind of
  ship (see spec 0047 — template schema migration). This spec
  excludes template changes explicitly; 0047 covers them.
- **Correlation of WIPs to developer tasks.** Today the link is
  `spec_id → task_id` via `task_plans`. Robust enough? Probably yes,
  but the back-fill script will tell us where the mapping breaks.

## Links

- AGENTS.md: [rule 5 — Two lifecycles for specs and designs](../../../AGENTS.md#hard-rules-for-agents)
  is the canonical rule this spec enforces.
- Related specs: [knowledge-api](../active/knowledge-api.md),
  [reviewer-worker](../active/reviewer-worker.md),
  [team-manager-worker](../active/team-manager-worker.md),
  [architect-worker](../active/architect-worker.md),
  [admin-panel](../active/admin-panel.md),
  [task-orchestration](../active/task-orchestration.md).
- Related ADRs: [0001 — knowledge repo layout](../../adrs/0001-knowledge-repo-layout.md),
  [0012 — re-prompt-only worker output remediation](../../adrs/0012-re-prompt-only-worker-output-remediation.md).
- Roadmap: [ROADMAP.md](../ROADMAP.md) — Phase 8, item 0044.

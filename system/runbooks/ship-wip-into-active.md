---
id: ship-wip-into-active
title: Ship a WIP into active — Architect draft, Reviewer attest, TM close
type: runbook
status: active
owner: ro
created: 2026-04-17
updated: 2026-04-18
last_verified_at: 2026-04-18
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [github]
---

# Ship a WIP into active

Operational guide for the ship gate — the step that folds a shipping
WIP into `active/` atomically, attested by the Reviewer worker. The
ship endpoint lives in
[knowledge-api](../product-specs/active/knowledge-api.md) /
[knowledge-write-api](../designs/active/knowledge/knowledge-write-api.md); the
close-cycle backstop lives in
[team-manager-worker](../product-specs/active/team-manager-worker.md);
the admin ship-gate panel is described in
[admin-panel](../product-specs/active/admin-panel.md). ADR
[0015](../adrs/0015-ship-gate-in-coder-pipeline.md) records the
decision to keep the gate inside the Coder pipeline rather than
GitHub branch protection.

## When to run this

- The pipeline run view shows the **Ship** gate pending approval.
  Triggered automatically when a developer task closes and its PR
  merges while a matching WIP file still exists.
- A Team Manager close-cycle attempt returned
  `wips_pending_merge` — walk the linked WIPs through this runbook
  until close-cycle is unblocked.
- The weekly orphan-WIP report (from
  `scripts/find_orphan_wips.py`) lists a project with open orphans
  — walk each one through the runbook, oldest first.

## Who can run this

Reviewer worker is the attesting authority. An operator (human)
with admin JWT approves or rejects at the ship gate in the admin
panel. No other role can approve a ship.

The Architect worker produces the draft; the operator never hand-
drafts the merge at this stage (though they may hand-edit the
Architect's draft before attestation).

## Prerequisites

- Developer task for the WIP is `closed` with status `merged`.
- The PR's diff is visible in the admin panel.
- The WIP's `## Acceptance criteria` section is parseable. The ship
  validator recognises two bullet shapes:
  - `- [ ]` / `- [x]` — legacy checkbox.
  - `- **AC<N>.** ...` — canonical (architect template + standard
    PM drafts since 2026-05-06; preferred for new specs).
  If the AC list uses any other format (plain `- ` bullets, numbered
  lists, prose paragraphs), fix the WIP's markdown before the ship
  gate. The ship validator matches AC text exactly (normalised
  whitespace).

## The happy path

1. **Architect draft appears automatically.** The pipeline
   dispatches a `knowledge-ship-draft` task when the developer task
   closes. The Architect worker produces a `merges[]` array —
   `create` and `edit` actions against `active/` files. Wait for
   the task to show `done` (typically ~60 s).
2. **Review the draft at the ship gate.** Admin →
   `/projects/{project_id}/ship/{wip_id}`. Left column: per-file
   diff preview, including registry YAML edits and the WIP file's
   deletion. Right column: the Reviewer's `ship_attestation` with
   one entry per AC. Discovery: the project's detail page shows a
   "Pending ships" banner listing every WIP that's closed + merged
   but un-shipped; each row links straight to this gate.
3. **Sanity-check the AC coverage.** Every AC from the WIP must be
   either:
   - `merged_into: <artifact>` + `section: <heading>` — confirm the
     referenced section in the target file actually describes the
     AC's behaviour, not just mentions the area.
   - `dropped: true` + `reason: <text>` — rare; read the reason. If
     the AC was genuinely never shipped (scope change), drop is
     correct. If the AC shipped but the Reviewer couldn't find
     where it landed, that's a Reviewer bug — send back for rework.
4. **Click Approve.** Admin calls
   `POST /v1/projects/{id}/knowledge/ship` with the merges +
   attestation. On 201, the response includes the commit SHA and
   the list of touched paths.
5. **Confirm the commit landed.** Click through to GitHub via the
   returned SHA. You should see a single commit covering every
   touched file + both affected registries + the WIP delete.
6. **Team Manager close-cycle unblocks.** The pipeline's
   close-cycle backstop (in
   `coder_core.workers.pipeline_chain.on_all_dev_tasks_accepted`)
   stamps the run's `blocked_since` and emits a
   `pipeline_run.close_cycle_blocked` event when a shipped spec
   still has its numbered WIP in `wip/`. On Approve the ship
   endpoint fires `on_wip_shipped`, which re-runs the backstop;
   with the WIP gone the run advances to `pm_acceptance`
   automatically — no manual prod.

## Rejection paths

### R1 — AC coverage looks thin or wrong

The merge technically covers every AC but a section is superficial
("see `reviewer-worker.md`" with no substantive edit) or a
`dropped` reason is unconvincing.

- Click **Request changes** on the ship gate. Include a short
  comment naming the specific AC and what's missing.
- Pipeline re-dispatches the `knowledge-ship-draft` task to the
  Architect with the comment as context.
- Go back to step 2.

### R2 — Merges conflict with concurrent `active/` edits

A second WIP shipped before this one, or a freshness audit
committed to one of the target artifacts. GitHub returns 409 on
the ship commit.

- Admin surfaces the 409 inline. Click **Redraft against HEAD** —
  the Architect task re-runs with the current `active/` as input.
- Go back to step 2.

### R3 — Architect draft can't find a home for an AC

Some ACs describe behaviour whose logical home is a new `active/`
artifact that doesn't exist yet. Architect emits a `create` entry;
operator must sanity-check the new artifact's frontmatter.

- Confirm the new artifact's name matches the logical component —
  an `active/` slug is a stable identifier (AGENTS.md rule 6), so
  naming matters.
- If the name looks off, **Request changes** with a suggested slug.
- If the name is right, Approve as normal.

### R4 — Hand-editing the draft before attestation

Operator sees a small wording improvement in the draft they want
to apply directly (typo, clearer section title).

- Click the draft diff's **Edit** affordance. The inline editor
  mutates only the merge patch, not the WIP source.
- The edited patch is re-validated (frontmatter + cross-links) on
  Approve. If validation fails, the panel surfaces the error; fix
  and re-approve.
- Large rewrites should go back via R1 — use Edit for small wins
  only.

## Success condition

- Single commit on the default branch covering every touched file
  and both registry YAMLs, with the WIP file deleted in the same
  commit.
- `scripts/validate.py` passes against the new HEAD.
- Orphan-WIP query returns empty for this WIP.
- The pipeline run's ship stage shows `done`.
- `knowledge_freshness_score` for the touched `active/` artifact(s)
  shows a fresh `last_verified_at = today` (the ship itself is an
  attestation — 0043 integration).

## If something goes wrong

- **Ship commit partially applied.** Not possible via the happy
  path — the endpoint uses Git Trees for atomic writes. If the
  admin shows a half-state, a hand-merge bypassed the pipeline. Use
  `scripts/find_orphan_wips.py` to diagnose and either (a) retry
  the ship gate against HEAD, or (b) revert the bad commit and
  start over.
- **Close-cycle still blocked after Approve.** Check that the PR
  was actually merged (the query filters on PR merged, not just
  closed). If the PR was closed without merge, the WIP should have
  stayed in flight — the ship gate shouldn't have fired. File a
  bug against the pipeline's ship-gate dispatcher.
- **Reviewer keeps producing malformed attestations.** The 0025
  schema loop retries re-prompt on shape errors; if attestations
  fail the budget, the task lands `failure_kind="schema"`. Follow
  the [worker-schema-failure](./worker-schema-failure.md) runbook;
  the fix is usually in the ship-mode reviewer schema or prompt,
  not in this runbook.
- **WIP's AC list doesn't match the attestation's `acs[]`.** AC
  text changed after the developer task started. Either edit the
  WIP's ACs to match what actually shipped (and re-attest), or
  mark the mismatched ACs `dropped` with reasons. Do not
  retroactively rewrite ACs without a note — the audit trail
  matters for 0043's attestation-dropout metric.

## Related

- Specs: [knowledge-api](../product-specs/active/knowledge-api.md)
  (ship endpoint + orphan-WIP query),
  [reviewer-worker](../product-specs/active/reviewer-worker.md)
  (ship-mode schema + `ship_attestation`),
  [team-manager-worker](../product-specs/active/team-manager-worker.md)
  (close-cycle backstop),
  [architect-worker](../product-specs/active/architect-worker.md)
  (ship-draft mode),
  [admin-panel](../product-specs/active/admin-panel.md)
  (Ship gate panel).
- Designs: [knowledge-write-api](../designs/active/knowledge/knowledge-write-api.md)
  (atomic Git Trees commit path),
  [team-manager-worker](../designs/active/workers/team-manager-worker.md)
  (close-cycle mechanics),
  [architect-worker](../designs/active/workers/architect-worker.md)
  (ship-draft prompt-prefix detection).
- ADRs: [0015 — ship gate in the Coder pipeline](../adrs/0015-ship-gate-in-coder-pipeline.md),
  [0012 — re-prompt-only remediation](../adrs/0012-re-prompt-only-worker-output-remediation.md)
  (the Reviewer ship-mode schema plugs into this loop).
- Adjacent: [worker-schema-failure](./worker-schema-failure.md),
  [knowledge-freshness-audit](./knowledge-freshness-audit.md) —
  Outcome C's WIP eventually returns here to ship.
- AGENTS.md rule 5 — the canonical rule this runbook operationalises.

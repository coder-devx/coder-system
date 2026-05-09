---
id: ship-gate-remote-missing
title: Ship gate failed — remote_missing
type: runbook
subtype: failure-mode
status: active
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
failure_kind: ship_gate_remote_missing
signal: 'failure_detail =~ "ship gate failed: remote_missing"'
suggested_action: manual_only
owning_role: reviewer
related_runbooks:
  - branch-gc
  - dispatching-developer-tasks
---

# Ship gate failed — remote_missing

## What it is

The reviewer-worker's ship gate (spec 0044) checks that the WIP
artifact's `served_by_designs` / `implements_specs` cross-links
resolve to artifacts that exist in the registry. `remote_missing`
means the WIP cites a target that's not in the project's knowledge
repo — usually because a sibling WIP was deleted or because the
WIP id allocation went wrong.

By volume this is rare but persistent — 2 of 27 stuck tasks
observed in the 2026-05-09 walk of `coder` were this kind, with
the oldest sitting 4 days. Unlike the other two failure modes,
this one almost never auto-resolves on retry — the missing target
is missing because of a real divergence, not a transient.

## Why it happens

In rough order of frequency:

1. **Sibling artifact never landed.** A spec WIP was filed citing
   a design that was supposed to land in the same dispatch but
   never did (worker failed before producing the design, operator
   abandoned the dispatch, etc.).
2. **Artifact was deleted from main** between when the WIP was
   filed and when the reviewer ran. Less common, but possible
   during cleanup sweeps.
3. **Numeric id allocation drift.** Pre-ADR 0026 era — the spec
   referenced a numeric id that got remapped during ship; the
   stale numeric reference stays in the WIP body / frontmatter.
4. **Project misconfiguration.** Citing an artifact in another
   project's knowledge repo. Cross-project citations aren't
   resolvable through the per-project registry.

## How to detect

- Now: a row labeled "ship gate: remote_missing".
- TaskDetail: reviewer task ended red with structured failure
  detail showing the missing target id and which field cited it.
- The WIP file itself: open it and look at `served_by_designs` /
  `implements_specs` / `related_specs` — one of those entries is
  the offending id.

## Suggested action

This is `manual_only` — a routine retry doesn't help, since
nothing changes between attempts.

1. **Read the failure detail.** It names the missing target id
   and the citing field. Open the WIP file and locate that
   reference.
2. **Decide which side to fix.**
   - If the cited target *should* exist (someone forgot to land
     it): file the missing artifact via SpecCompose / a manual PR,
     then re-dispatch the reviewer once it's merged.
   - If the cited target *shouldn't* exist (typo, leftover
     reference): edit the WIP to remove the bad reference, then
     re-dispatch.
3. **For numeric-id drift**: cross-reference against the registry
   to find the new slug-based id; update the WIP citation;
   re-dispatch.
4. **For cross-project citations**: split the spec — one
   per-project — or move it to a fleet-wide artifact under a
   neutral path.

## When to escalate

- A WIP at this `failure_kind` for ≥7 days: the operator should
  decide to either land the missing artifact or delete the
  blocked WIP. Escalation routes to PM owner.
- ≥3 simultaneous `ship_gate_remote_missing` tasks on the same
  project: usually means a recent cleanup deleted active
  artifacts that WIPs cite. Walk the deletions and either revert
  or update the citing WIPs.

## Related runbooks

- [branch-gc](../branch-gc.md)
- [dispatching-developer-tasks](../dispatching-developer-tasks.md)

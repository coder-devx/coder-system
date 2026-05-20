---
id: '0093'
title: Architect broken_cross_link should surface the specific field/target instead of silent-dropping
type: spec
status: wip
owner: ro
created: '2026-05-13'
updated: '2026-05-13'
last_verified_at: '2026-05-13'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- architect-worker
- branch-protection
parent: pipeline-operations
---

# Architect broken_cross_link should surface the specific field/target instead of silent-dropping

**Phase:** wip
**Progress:** 0 / 3 acceptance criteria

## Problem

When an architect emits a design whose frontmatter references something the cross-link validator can't resolve, `_commit_artifact_with_registry` in `coder-core/src/coder_core/workers/dispatcher.py:1320` returns `"broken_cross_link"` and `_handle_architect_result` tags the task `failure_kind=broken_cross_link` with a generic `failure_detail` of the form:

```
"architect output references a slug (served_by_designs / related_specs / implements_specs / ...) that doesn't exist in its registry. See task log for the specific field/target_type/target_id; the architect body is preserved in task.result. Either include the missing target in the same write or fix the cross-link."
```

The operator gets *no* indication of which field, target_type, or target_id was the problem. Recovering means:

1. Pulling the worker's transcript from GCS or scrubbing Cloud Run logs for the `commit_artifact: %s/%s rejects broken cross-link` warning line.
2. Inspecting each frontmatter field in `task.result.design.frontmatter` and comparing each value against the corresponding registry in `coder-system`.
3. Finding the discrepancy by hand.

For the 2026-05-13 spec-0089 architect run, the discrepancy was `affects_repos: [coder-product-template]` against `system/repos/registry.yaml` (which had three repos, not four — the template was a Phase A close-out that never got the registry write). Recovery took ~20 minutes of manual debugging to track down; the fix itself was a one-line registry insert.

Two related-but-distinct gaps surface from this:

1. **The failure message is unstructured.** `failure_detail.kind / design_id / reason` are populated; the actual `field / target_type / target_id` triple — which is the actionable information — is buried in the worker's log line, not in the task row.
2. **The validator treats some "metadata" fields as hard cross-links.** `affects_repos` and `affects_services` are listed in `CROSS_LINK_FIELDS` (`coder-core/src/coder_core/knowledge/schema.py:100`). When a real repo exists on GitHub and is listed in `system/repos.yaml` (the dispatcher's workspace contract) but missing from `system/repos/registry.yaml` (the knowledge registry), the validation fails. The two registries are easy to drift; spec 0089's recovery cost was real evidence of that drift.

## Goals

- Surface the failing `field`, `target_type`, and `target_id` directly in the task row's `failure_detail` so the operator can fix the registry drift (or the architect's output) in one read.
- Decide whether `affects_repos` / `affects_services` should remain hard cross-links or move to a softer-validated "metadata" tier. Bias: keep the strict validation but auto-recover when the target exists in the matching workspace-contract file (`system/repos.yaml` for repos).
- Audit the four current `wip/` designs (0088, 0089, 0090, 0091) for similar drift before their TM plans get approved.

## Non-goals

- Removing cross-link validation entirely. The catch-bad-references behaviour is the right default for `implements_specs` / `related_designs` / `decided_by` etc.
- Auto-creating the missing registry entry from the architect's side. The architect doesn't have write access to repos/services registries by design; the operator does, with a one-line PR.
- Changing the GCS transcript or log line — they're already verbose enough for forensic debugging.

## Scope

Three surfaces:

1. **`failure_detail` structured fields.** In `_handle_architect_result` (path TBD during design), when `commit_artifact` returns `"broken_cross_link"`, capture the warning's `(field, target_type, target_id)` triple and serialize them into `failure_detail` as discrete keys. The admin UI's failure-detail render then shows them inline on the task card without round-tripping to GCS.

2. **Workspace-contract bridge.** In `_validate_cross_links` (or its dispatcher equivalent), when the target_type is `repos` and the target_id appears in `system/repos.yaml`, treat as resolved. Same pattern for `services` — though the bridge file there is less obvious; design must decide whether to define a `system/services.yaml` workspace contract or skip the bridge for services.

3. **Wip-design audit script.** A `scripts/audit_wip_design_cross_links.py` that walks `system/designs/wip/*.md`, parses frontmatter, and validates every `CROSS_LINK_FIELDS` reference against the current registries. Output: a structured report of broken links. Run on every PR touching `system/designs/wip/` as a CI check; run pre-flight by the architect worker as a soft warning before commit.

## Acceptance criteria

- **AC1.** A spec-0093-shaped repro (architect emits a design with `affects_repos: [unknown-repo]`) tags the task with `failure_kind=broken_cross_link` AND populates `failure_detail` with `{field: "affects_repos", target_type: "repos", target_id: "unknown-repo", design_id: ..., kind: "broken_cross_link", reason: <generic>}`. Confirmed by an integration test that inspects the persisted task row.

- **AC2.** When the architect emits a design with `affects_repos: [<repo-in-workspace-contract>]` and that repo is in `system/repos.yaml` but not `system/repos/registry.yaml`, the design lands successfully (no `broken_cross_link`). A regression-style admin-UI test confirms the task transitions to `accepted` and the registry remains unchanged.

- **AC3.** `scripts/audit_wip_design_cross_links.py` exists, exits 0 against current `coder-system/main`, and exits non-zero with a structured diff when any `system/designs/wip/*.md` has an unresolvable cross-link reference. A new ci.yml step runs it on every PR touching `system/designs/wip/`.

## Open questions

- For `services` cross-links: do we add a `system/services.yaml` workspace contract analogous to `system/repos.yaml`, or do we tighten `affects_services` to be "soft-validated" (warn instead of fail)? Bias: the services catalog changes much less than repos, so the strict path is fine; just keep service registration in the design-time checklist.
- Should the audit script be a one-off `scripts/` tool or a long-lived utility under `system/lint/`? The `lint/` path puts it in the operator's runbook. Bias: `system/lint/` because future cross-link surfaces (e.g., new fields in `CROSS_LINK_FIELDS`) want a stable home.
- Operator-recovery path for a stuck architect: today the operator has to (a) read GCS to identify the broken link, (b) fix the registry, (c) re-dispatch the architect, hoping for the same output. Spec 0086's `failure_kind` accumulator is the visibility layer; this spec is the actionability layer. Worth adding a "rebuild from preserved output" admin action that takes `task.result` and re-runs only the commit step — separate spec or fold here?

## Links

- [coder-system PR #128](https://github.com/coder-devx/coder-system/pull/128) — the spec 0089 hand-recovery that surfaced this gap.
- [coder-core src](https://github.com/coder-devx/coder-core/blob/main/src/coder_core/workers/dispatcher.py) — `_commit_artifact_with_registry` line 1320.
- [coder-core schema](https://github.com/coder-devx/coder-core/blob/main/src/coder_core/knowledge/schema.py) — `CROSS_LINK_FIELDS` at line 100.
- Spec 0086 — the architect ADR-collision visibility scope (same family).

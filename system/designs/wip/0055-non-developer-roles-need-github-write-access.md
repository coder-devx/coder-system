---
id: "0055"
title: Non-developer-role workers need GitHub write access
type: design
status: wip
owner: ro
created: 2026-04-27
updated: 2026-04-27
last_verified_at: 2026-04-27
implements_specs: ["0055"]
decided_by: []
related_designs:
  - worker-roles
  - worker-communication
affects_services:
  - coder-core
affects_repos:
  - coder-core
---

# 0055 — Non-developer-role workers need GitHub write access

## Context

See [spec 0055](../../product-specs/wip/0055-non-developer-roles-need-github-write-access.md)
for the problem framing. **This design is a stub** — pending
architect pickup. The spec is detailed enough to dispatch
implementation directly with a tight prompt; this stub exists to
keep cross-links resolvable per the AGENTS.md registry contract.

## Goals / non-goals

Match the spec one-for-one. No expansion.

## Design

The fix lives entirely inside `coder-core/src/coder_core/workers/`.
Decoupling `GH_TOKEN` injection from `task.workspace` is the load-
bearing change.

Realistic implementation shape (to be confirmed by architect or
the implementing developer task):

1. New helper `coder_core/workers/_github_env.py` with
   `apply_github_token_env(env, project_id, settings)` that resolves
   the per-project GitHub PAT (existing config; same source the
   workspace-prep code uses today) and sets `env["GH_TOKEN"]`.
2. Each role's worker module calls the helper before invoking
   `claude`. Developer worker is refactored to call the helper as
   well — no behaviour change since the same token gets set; the
   `task.workspace.github_token` access becomes a downstream concern
   of the workspace clone, not the env-var injection.
3. Dispatcher resolves the project's GitHub PAT at task-creation
   time (or as a `WorkerInput` field) so the credential is
   available even when `task.workspace is None`.

## Open questions

Inherited from spec — see [spec 0055 § Open questions](../../product-specs/wip/0055-non-developer-roles-need-github-write-access.md).

## Rollout

- **Stage 0 — code lands.** Helper module + per-role-worker call
  sites + dispatcher credential resolve. Tests confirm
  `GH_TOKEN` is set for architect/TM/PM/reviewer/developer.
- **Stage 1 — recovery test.** Re-dispatch the original architect
  prompt that failed (task `62e0c95e`). Confirm it now opens a
  PR against coder-system instead of writing to `/tmp`.

## Backout plan

Revert the helper module and call sites. Developer worker reverts
to its original `task.workspace.github_token` access. Non-developer
roles return to their pre-fix broken state.

## Links

- Spec: [0055](../../product-specs/wip/0055-non-developer-roles-need-github-write-access.md)
- Related designs: [worker-roles](../active/worker-roles.md), [worker-communication](../active/worker-communication.md)
- Realised pain: architect task `62e0c95e` (2026-04-27)

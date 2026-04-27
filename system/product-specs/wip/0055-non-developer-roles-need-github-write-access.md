---
id: "0055"
title: Non-developer-role workers need GitHub write access
type: spec
status: wip
owner: ro
created: 2026-04-27
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ["0055"]
related_specs:
  - architect-worker
  - team-manager-worker
  - pm-worker
  - reviewer-worker
  - task-orchestration
---

# 0055 — Non-developer-role workers need GitHub write access

## Problem

The developer worker gets `GH_TOKEN` injected into its subprocess
env so the embedded `claude` CLI can run `git push` + `gh pr
create`. The injection happens in
[`developer.py:351`](https://github.com/coder-devx/coder-core/blob/main/src/coder_core/workers/developer.py):

```python
env["GH_TOKEN"] = task.workspace.github_token
```

— gated on `task.workspace is not None`. Developer tasks always
have a workspace (they need a repo clone). **Non-developer-role
tasks (architect, TM, PM, reviewer) don't get a workspace
configured in the manual-dispatch path** — so `task.workspace` is
None, the env var stays unset, and the worker subprocess can't
authenticate to GitHub.

**Realised pain (2026-04-27, task `62e0c95e`):** the architect
worker for spec 0054 ran productively — read the spec, verified
line numbers in `coder-core/orchestrator.py`, found that
`GitHubClient.list_pulls` already exists, made a real ADR-worthy
decision about `user.type == "Bot"` vs login-match — wrote the
refined design + a new ADR to `/tmp/design-0054/` on the worker's
container. **Then exited with**:

> *"I can't open a GitHub PR because `gh` is unauthenticated and
> there's no `GH_TOKEN` in the environment."*

The work was lost when the container was reaped. The architect's
analytical contribution had to be manually transcribed from the
result-text summary back into a hand-edited refinement of the
existing design + an ADR.

This breaks the full pipeline-chain dogfood loop: PM/architect/TM
tasks can't ship their outputs through PRs, only through their
direct knowledge-API writes (which is what the chain-driven path
relies on, but doesn't help operator-driven manual chain
dispatches).

## Users

- **Operator running a manual chain** — wants to dispatch
  architect/TM/PM tasks directly and see them ship outputs
  through PRs the same way developer tasks do. Today they can't.
- **Architect / TM / PM workers** — their CLI's tool-use loop
  expects `gh pr create` to work when the role doc instructs
  them to open a PR. Today they exit with auth errors and the
  outputs don't land.
- **Pipeline-chain orchestrator** — when the chain hooks
  (`on_spec_approved` etc.) trigger architect tasks, the chain
  path may already wire workspace differently. This spec needs
  to verify whether chain-dispatched tasks have the same gap or
  a different code path that already works.

## Goals

- **All worker roles can authenticate to GitHub** when their
  task requires it. Specifically: `GH_TOKEN` (or equivalent
  credential) is set in the subprocess env for architect, TM,
  PM, and reviewer tasks the same way it is for developer
  tasks.
- **The dispatch path doesn't require a workspace clone for
  non-developer roles** — architect doesn't need to clone the
  project's code repo to write a design; the auth surface
  needs to be decoupled from the workspace config.
- **No regression for developer tasks.** Existing developer-task
  dispatches keep their current behaviour exactly.

## Non-goals

- **Granting write access beyond what the developer worker has
  today.** The same per-project GitHub PAT the developer worker
  uses is reused for non-developer roles. No new permissions
  surface.
- **Cross-project PR opening.** Each project's worker authenticates
  with that project's PAT; PRs land in that project's repo. No
  cross-project work in this spec.
- **Re-architecting how non-developer roles ship outputs.**
  Architect today writes to the knowledge repo via the existing
  knowledge-write API in some code paths and via direct git/PR
  flow in others. This spec just closes the auth gap; consolidating
  the two paths is a separate spec.

## Scope

### In scope

1. **Audit current state.** Walk each role's worker code path:
   does it set `GH_TOKEN` in the subprocess env? Does it depend
   on `task.workspace` being non-None? Confirm the gap surfaces
   in the manual-dispatch path (where workspace is null).
   Probable touch points: `developer.py:351` (current
   reference), `architect.py`, `team_manager.py`, `pm.py`,
   `reviewer.py` (or wherever each role's run-task function
   lives).
2. **Hoist GH_TOKEN injection into a shared helper** that
   doesn't require a workspace. The helper accepts the
   per-project GitHub credential (currently
   `task.workspace.github_token`) directly and sets the env
   var. Each role's worker calls the helper unconditionally.
3. **Resolve the per-project credential outside of workspace
   construction.** The dispatcher already knows the project
   from `task.project_id`; the GitHub PAT lookup that
   `prepare_workspace` does today should be lifted to the
   dispatch site so it's available for non-workspace tasks.
4. **Tests.** Each role's worker test gets a "GH_TOKEN is set
   even when workspace is None" assertion.

### Out of scope

- Architect's role doc updates to reflect that it can now open
  PRs (probably already says it can; just wasn't true).
- The reviewer's verdict-merging path (different concern;
  reviewer uses a separate flow for posting reviews).
- Workspace-less code-reading roles (architect needs to read
  coder-core's `orchestrator.py` to verify line numbers — that
  uses the `GitHubClient` directly, not a clone). Out of scope
  for this spec; covered by the existing GitHubClient setup.

## Acceptance criteria

- **AC1.** A new helper (e.g.
  `coder_core/workers/_github_env.py`'s `apply_github_token_env`)
  takes `(env, project_id)` and sets `env["GH_TOKEN"]` from the
  per-project credential. Independent of `task.workspace`.

- **AC2.** Each role's worker (architect, TM, PM, reviewer)
  invokes the helper unconditionally before spawning the
  `claude` subprocess. Developer worker also routes through
  the helper (refactor; no behaviour change).

- **AC3.** The per-project GitHub credential is resolved at
  dispatch time, not workspace-prep time, so the credential is
  available to tasks without a workspace.

- **AC4.** Test: dispatch an architect task with no workspace
  configured. Confirm via the worker's transcript / log that
  `GH_TOKEN` is set in the subprocess env.

- **AC5.** Test: dispatch a developer task as today. Confirm
  no behaviour change (`GH_TOKEN` still set; `git push`+`gh pr
  create` still work).

- **AC6.** Re-dispatch architect task `62e0c95e`'s prompt as a
  recovery test. Confirm the architect now successfully opens
  a PR against coder-system instead of writing to `/tmp` and
  exiting with the auth error.

## Metrics

- **Reproduction-then-fix verification.** Before this spec
  ships, `62e0c95e` reproduces the failure mode. After it
  ships, a clean re-dispatch of the same prompt succeeds.
- **Cross-role smoke test rate.** After ship: count of
  successful PR opens by architect/TM/PM/reviewer roles per
  week. Trends from 0 to non-zero confirm the loop now
  functions for upper roles.

## Decisions

To be resolved during architect dispatch (i.e. this spec is
genuinely WIP, not pre-decided):

- **Where does the credential live?** Today
  `task.workspace.github_token` is set during workspace prep.
  After this spec, it needs to be available even without a
  workspace. Options: (a) resolve at dispatch time and pass on
  `WorkerInput`; (b) keep it on `task.workspace` and make
  workspace creation cheap/no-op for non-developer roles;
  (c) read it directly from project config inside each role's
  worker.
- **Is `GH_TOKEN` the only relevant env var?** `gh` CLI also
  reads `GITHUB_TOKEN` as a fallback. Setting both might be
  more robust, but redundant. v1: stick with `GH_TOKEN` to
  match developer.py.
- **Per-role overrides?** Maybe architect/TM should run with a
  more limited token (write designs only, not arbitrary git
  push)? Probably out of scope for v1; same token as developer
  is the simplest move.

## Open questions

- **Does the chain-driven dispatch path already work?** The
  pipeline chain hooks (`on_spec_approved` etc.) create
  architect tasks via `_create_chained_task`. Need to confirm
  whether those tasks get a workspace (and thus GH_TOKEN) or
  whether the chain-driven path has been silently failing too.
  This spec's audit step (in scope #1) confirms.
- **Is there a knowledge-write-only auth that avoids the full
  PAT?** If architect only needs to write to coder-system (a
  specific repo via a specific surface), a narrower scope might
  be safer than reusing the developer's full PAT. v1 may
  proceed with the existing PAT for simplicity; a follow-up
  spec could narrow.
- **Reviewer's specific needs.** The reviewer worker posts PR
  reviews via `gh pr review`. Confirm that the same PAT scope
  works for the review-post action; if not, additional
  permissions may be needed.

## Links

- Designs: [0055](../../designs/wip/0055-non-developer-roles-need-github-write-access.md) (pending architect — chicken-and-egg until this spec ships)
- Related specs:
  [architect-worker](../active/architect-worker.md),
  [team-manager-worker](../active/team-manager-worker.md),
  [pm-worker](../active/pm-worker.md),
  [reviewer-worker](../active/reviewer-worker.md),
  [task-orchestration](../active/task-orchestration.md)
- Realised pain: architect task
  `62e0c95e-bdc9-4f42-a493-610ff5236065` (2026-04-27) — wrote
  refined design + ADR to `/tmp/design-0054/`, lost on container
  reap.

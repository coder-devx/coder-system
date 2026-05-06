---
id: "0016"
title: Worker-authored PR detection via user.type == "Bot"
type: adr
status: accepted
date: 2026-04-27
deciders: [ro]
relates_to_designs: ["orchestrator-github-state-reconciliation"]
---

# ADR 0016 — Worker-authored PR detection via `user.type == "Bot"`

## Context

[Spec 0054](../product-specs/wip/0054-orchestrator-github-state-reconciliation.md)
adds a GitHub-side reconciliation step in the orchestrator: when a
developer task is `succeeded|executing` with `pr_url=null`, query
GitHub for an open PR on the task's `branch_name` and reconcile if
one exists. The spec scopes reconciliation to **worker-authored
PRs only** — operator-opened PRs on the same branch are left alone
because they may have been opened for unrelated recovery reasons
and conflating them would silently associate operator work with the
wrong task row.

That requires the helper to identify "worker-authored" reliably.
GitHub's PR API returns a `user` object on each PR with
`{login, type, ...}`. There are two ways to recognise a
worker-authored PR:

- **By login.** Check `pr["user"]["login"] == <known bot login>`,
  e.g. `coder-devx[bot]`. The operator's PRs have a different
  login.
- **By type.** Check `pr["user"]["type"] == "Bot"`. Per the GitHub
  API contract, `user.type` is `"Bot"` for all PRs opened by a
  GitHub App installation and `"User"` for human-authored PRs.

Surfaced during architect task `62e0c95e` (2026-04-27) on spec 0054.

## Options considered

1. **Match against a known bot login.** Add a
   `coder_github_app_bot_login` field to `Settings`, read it at
   reconciliation time, compare with `pr["user"]["login"]`.
   - Pros: extremely specific. If five different bots ever open
     PRs on managed repos, login-match distinguishes them.
   - Cons: adds a config field that must be kept in sync with the
     GitHub App's actual bot identity. Misconfiguration silently
     breaks reconciliation (the PR would be reconciled-against
     no-one). The bot login is GitHub-side state that doesn't
     map cleanly to a config knob — if a fleet operator renames
     the App or deploys against a different App, the config
     breaks. **The misconfiguration shows up only when a task
     hits the `succeeded|executing|no pr_url` path** (the rare
     case 0054 was designed for), so the breakage is invisible
     until the very moment the safety net is supposed to fire.

2. **Match against `user.type == "Bot"`.** Treat any PR whose
   author is a Bot as worker-authored.
   - Pros: no config field needed. The GitHub API contract is
     stable: `user.type` has been `"Bot"` for App-authored PRs
     since GitHub Apps shipped, and changing it would be a
     breaking API change for the entire ecosystem.
   - Cons: if a fleet operator installs a *second* GitHub App on
     the same repo (e.g. dependabot, renovate) and that bot
     happens to open a PR on a `task/*` branch the worker also
     pushed to, we'd reconcile against the wrong PR. **In
     practice this is implausible:** dependabot/renovate open
     PRs against their own dedicated branches with naming patterns
     unrelated to `task/*`, and the reconciliation only fires on
     the success-with-no-PR path which already requires the worker
     to have pushed a branch.

3. **Combine: `user.type == "Bot"` AND login starts with a
   project-configurable prefix.** Best of both worlds in theory.
   - Pros: catches the dependabot edge case in option 2 if it ever
     materialises.
   - Cons: still adds the config-field surface from option 1, with
     all its misconfiguration risk; the edge case it guards
     against is implausible.

## Decision

**Use `pr["user"]["type"] == "Bot"`.** No new config field. No
login matching.

## Rationale

The misconfiguration risk in option 1 is the deciding factor.
0054's reconciliation is the safety net for a known failure class
(worker opens PR but skips printing the URL). A safety net whose
correct operation depends on a config field that almost no one
will look at until it breaks is not a safety net — it's a
silent-failure trap. `user.type == "Bot"` is a property of the
GitHub API itself, doesn't drift, doesn't need ops attention, and
can't be misconfigured.

The edge case in option 2 (a second installed App opens a PR on
the same `task/*` branch as the worker) requires:
1. A second GitHub App installed on the repo
2. That App opening a PR on a branch the worker also pushed
3. The worker's task being in the `succeeded|executing|no pr_url`
   path at the same time

The realistic failure mode is dependabot, which doesn't push to
`task/*` branches. If a future configuration ever does collide
here, the symptom is "task row's `pr_url` got populated with the
wrong PR's URL" — visible immediately because the next stage's
review would target the wrong PR. Recoverable; not silent.

Option 3's complexity tax outweighs the edge case it covers.

## Consequences

- **Positive:** zero config surface. Reconciliation Just Works
  for any project that's onboarded with a GitHub App. No ops
  knob to forget.
- **Positive:** the helper is portable to any future fleet
  using the same dispatch architecture. No project-level config
  to migrate.
- **Negative:** if a future need genuinely requires distinguishing
  multiple bots on the same repo, this ADR has to be revisited
  and a new ADR superseding it must add the login-match path.
  Tractable; not load-bearing for any current behaviour.
- **Follow-ups:** spec 0054's implementation prompt for the
  developer worker references this ADR by id; the test fixture
  for `test_human_authored_pr_returns_none` constructs a PR with
  `user.type == "User"` and the fixture for the worker-authored
  cases uses `user.type == "Bot"`.

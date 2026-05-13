---
id: '0089'
title: Branch-protection enforcement on coder-core/main blocks all direct pushes
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
- developer-worker
- continuous-deployment
- audit-log
parent: tenancy-and-access
---

# Branch-protection enforcement on coder-core/main blocks all direct pushes

**Phase:** wip
**Progress:** 0 / 4 acceptance criteria

## Problem

Commit `e6f7382 chore: apply preflight fixes` was pushed directly to `origin/main` of `coder-devx/coder-core` by `coder-coder@vibedevx.com` — the dev worker bot — without a PR. It added 342 lines (`src/coder_core/workers/developer.py` + `tests/workers/test_migration_gate.py`) for spec 0082's developer-worker changes, bypassing the operator's PR-review gate entirely. Observed during the 2026-05-12 prod-recovery push when the next pre-push hook on a hotfix branch failed an unrelated I001 lint check on a file that was direct-committed without a CI cycle.

The operator memory's documented policy is explicit: **"Don't push to coder-core main directly — always through PR (even doc PRs)."** Branch protection on `coder-core/main` is supposed to enforce this. It currently does not — either the protection rules are too permissive (no "require PR" toggle), there's a bypass list that includes the worker bot, or the worker's token has classic-PAT level access that bypasses branch protection by design.

Phase B's autopilot depends on the PR review gate being load-bearing. If the worker's token can write to `main` directly, every "preflight fix" or "auto-format" pass is one bug away from landing un-reviewed code in production. The 2026-05-12 incident also exposed the related Spec 0088 path: a worker that bypasses PR can also bypass the deploy-gate's migrate step and apply schema changes silently.

## Users / personas

- **Operators relying on PR review as the only path to main.** Today the path is not exclusive; the policy is unenforced.
- **Reviewer worker.** Cannot review code that lands without a PR. Its audit surface skips the direct-pushed commits.
- **The continuous-deployment pipeline.** Cannot apply its pre-deploy checks (CI green, traffic shift) on a commit that bypassed PR — the PR-bound `check` job never ran for `e6f7382`.

## Goals

- Every push to `coder-core/main` requires a PR with at least one approving review. No exceptions, no bypass list.
- The dev worker's token surface cannot push direct to main even if it tried. Verified by a regression test that attempts the push and expects 403.
- Branch protection settings are version-controlled (`gh api repos/coder-devx/coder-core/branches/main/protection --method PUT` driven from a YAML in this repo) so the protection state cannot drift silently.
- Same enforcement extends to `coder-admin/main` and `coder-system/main` — all three repos that the orchestrator can write to.

## Non-goals

- Restricting non-`main` branch writes. Workers still push to `task/*` branches freely; only `main` is protected.
- Cutting the worker's GitHub token scope below what PR creation requires. Workers still need `contents: write` on `task/*` and `pull-requests: write` for opening the PR. This spec just bars the **direct-to-protected-branch** path.
- Replacing the existing operator-merge surface (`gh pr merge --squash`). The operator's own access stays unchanged.
- Auditing every historical direct-push commit. One-off audit is operator-side cleanup; this spec scopes to going-forward enforcement.

## Scope

Three surfaces:

1. **GitHub branch-protection rules** on the three orchestrator-managed repos (`coder-core`, `coder-admin`, `coder-system`). Enable: "Require a pull request before merging" with at least 1 approving review, "Restrict who can push to matching branches" (empty allowed list — no one direct-pushes), "Do not allow bypassing the above settings" (admin-bypass off). Apply to `main` only.

2. **Worker GitHub token scope review** (`coder-core` `coder_core/integrations/github.py` and Secret Manager). The current `coder-coder-github-pat` token (used by `coder-coder@vibedevx.com`) likely has classic-PAT broad scope or fine-grained scope with `contents: write` on main without a "must use PR" qualifier. Migrate to a fine-grained PAT or GitHub App installation token scoped to: `task/*` branches: write, `main` branch: read-only, `pull-requests`: write. Document in a runbook.

3. **Configuration-as-code** (`coder-system` new file `system/runbooks/github-branch-protection.md` + a YAML config in `coder-core/.github/branch-protection.yml` applied by a GitHub Action). Operator can regenerate protection settings from version control without clicking around the GitHub UI.

## Acceptance criteria

- **AC1.** Branch-protection rules on `coder-core/main`, `coder-admin/main`, `coder-system/main` all show: "Require pull request before merging: ON, 1 approving review", "Do not allow bypassing the above settings: ON". Verified via `gh api repos/{owner}/{repo}/branches/main/protection`.
- **AC2.** Regression test: a CI job runs in each repo's pipeline that attempts `git push origin main` using the worker bot's token. The push must return 403 (or equivalent). Test runs on every PR; failure blocks merge.
- **AC3.** The worker bot (`coder-coder@vibedevx.com`) is **not** on any branch-protection bypass list for any of the three repos. Verified by inspection of the bypass-actors API field.
- **AC4.** Version-controlled config: `coder-core/.github/branch-protection.yml` (or equivalent) exists and is applied by a GitHub Action on push to `main`. Drift between the YAML and the live state surfaces as a CI warning.

## Open questions

- Should the regression test (AC2) be on every PR or only on a nightly cron? Per-PR is safer but adds CI cost (~10s for the git push attempt). Lean per-PR.
- The fine-grained PAT migration (Scope 2) might require an admin OAuth dance that's operator-only. Should the spec carve out "operator provisions; design carries the runbook" or attempt to automate the rotation? Operator-provision is simpler; punt automation to a follow-up spec.
- Same enforcement on `coder-product-template`? Probably yes — it's an orchestrator-write repo. Add to the AC list once verified.
- Audit trail for direct-push attempts: GitHub's `audit_log` API records them, but we don't currently pipe that into the orchestrator's audit. Worth a follow-up spec on cross-system audit consolidation.

## Links

- Operator memory: "Don't push to coder-core main directly — always through PR (even doc PRs)" — the documented policy this spec enforces.
- The 2026-05-12 incident: `e6f7382 chore: apply preflight fixes` pushed direct to `coder-core/main` by `coder-coder@vibedevx.com`. Surfaced during the prod-wedge recovery push; the pre-push hook on a hotfix branch tripped on an I001 lint failure from that commit.
- Related spec: [0088 — worker prod-creds isolation](https://github.com/coder-devx/coder-system/pull/123) — the worker-side companion. 0088 closes the DB-credentials leak; this spec closes the git-credentials leak. Together they re-establish the PR review + CI deploy gates as the only path to prod schema and code changes.
- Related spec: `audit-log` (active) — the audit surface for review-bypass attempts. The AC4 drift-detection event lives in this audit surface.

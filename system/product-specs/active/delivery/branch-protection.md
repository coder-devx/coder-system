---
id: branch-protection
title: Branch protection enforcement
type: spec
status: active
owner: ro
created: 2026-05-20
updated: 2026-05-20
last_verified_at: 2026-05-20
summary: Enforces PR-only writes to main across orchestrator-managed repos via GitHub branch protection, version-controlled config, and a CI regression test.
served_by_designs: []
related_specs: [continuous-deployment, developer-worker, audit-log, service-accounts]
parent: delivery-and-infra
---

# Branch protection enforcement

## What it is

Governance layer that makes the PR review gate the only enforced path to
`main` across the three orchestrator-managed repos (`coder-core`,
`coder-admin`, `coder-system`). GitHub branch protection rules requiring
at least one approving review are enabled, version-controlled in each
repo, and applied by a GitHub Action; admin bypass is off; the worker
bot is absent from all bypass-actor lists. A CI regression test on
every PR validates that a direct push using the worker bot's token
returns HTTP 403. Closes the gap exposed by the 2026-05-12 incident in
which the developer worker pushed `e6f7382` directly to
`coder-core/main`, bypassing PR review and CI entirely.

## Capabilities

- **Branch protection rules** on `coder-core/main`, `coder-admin/main`,
  and `coder-system/main`: "Require a pull request before merging" (1
  approving review), "Do not allow bypassing the above settings" (admin
  bypass off), and "Restrict who can push to matching branches" (empty
  allowed list — no direct pushes by any actor). Verified via
  `gh api repos/{owner}/{repo}/branches/main/protection`.
- **No-bypass guarantee.** The worker bot (`coder-coder@vibedevx.com`)
  does not appear on any `bypass_pull_request_allowances` actor list for
  any of the three repos. Verified by API inspection on every drift check.
- **CI regression test.** A step in each repo's `ci.yml` workflow
  attempts `git push origin main` using the worker bot's token and
  asserts an HTTP 403 rejection. Runs on every PR; failure blocks merge.
- **Configuration-as-code.** `.github/branch-protection.yml` in each
  of the three repos declares the desired protection state. A dedicated
  GitHub Actions workflow (`branch-protection-sync.yml`) applies this
  config on push to `main` and surfaces any drift between the YAML
  and the live GitHub API state as a CI warning.

## Interfaces

- GitHub branch protection API:
  `PUT /repos/{owner}/{repo}/branches/main/protection` — applied by the
  sync workflow on every main push.
- GitHub Actions workflow: `.github/workflows/branch-protection-sync.yml`
  in each of the three repos (applies config, drift-checks live state).
- CI regression step: added to `.github/workflows/ci.yml` in each repo;
  uses the worker bot token to attempt a direct push and expects 403.
- Version-controlled config: `.github/branch-protection.yml` in each repo.

## Dependencies

- GitHub App / PAT: worker bot token needs `administration: read` to
  verify bypass-actor lists; the sync workflow needs
  `administration: write` to apply protection rules.
- [continuous-deployment](./continuous-deployment.md) — the PR + CI gate
  this enforcement protects is a prerequisite for CD's canary deploy path.
- [audit-log](../tenancy/audit-log.md) — drift-detection events and
  blocked bypass attempts are recorded in the audit surface.
- [service-accounts](../tenancy/service-accounts.md) — worker bot GitHub
  token scope is the credential surface being constrained.

## Evolution

- 0089 — Initial enforcement across all three orchestrator-managed repos:
  branch protection rules, no-bypass-actor list, CI regression test,
  config-as-code drift detection (2026-05-20). Responds to the
  2026-05-12 incident (`e6f7382` direct-pushed to `coder-core/main`
  by the developer worker bot, bypassing PR review and CI).

## Links

- Related components: [continuous-deployment](./continuous-deployment.md),
  [audit-log](../tenancy/audit-log.md),
  [service-accounts](../tenancy/service-accounts.md),
  [developer-worker](../workers/developer-worker.md)

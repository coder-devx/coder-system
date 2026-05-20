---
id: '0036'
title: Renovate-style automated PRs for template sync over git subtree or manual versioning
type: adr
status: proposed
date: '2026-05-10'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- coder-product-template
---

# ADR 0036 — Renovate-style automated PRs for template sync over git subtree or manual versioning

## Context

`coder-product-template` is instantiated once per product. When the template receives security patches, dependency bumps, or page-contract additions, already-instantiated product repos need those changes without manual operator SSH or developer trigger. The fleet must remain autonomous.

## Options considered

**Option A — Git subtree.** Each product repo embeds the template via `git subtree add`; updates require `git subtree pull` triggered per product per template release. Keeps deltas reviewable but requires an explicit per-product trigger, which defeats autonomous operation.

**Option B — Renovate-style automated PRs.** A coder-core daily job watches `coder-product-template` for `TEMPLATE_VERSION` bumps in `package.json`. On a new version it opens a sync PR to each live `b2c_product` repo; the existing Developer/Reviewer pipeline merges it. No operator trigger needed.

**Option C — Manual pinning.** Product repos pin to a specific template commit; operators manually initiate upgrades. Acceptable for a very small fleet; incompatible with autonomous operation as the portfolio grows.

## Decision

Option B: Renovate-style automated PRs via a `coder-core-template-sync-tick` Cloud Scheduler job (daily).

## Rationale

The Coder fleet already opens and merges PRs autonomously via the Developer/Reviewer pipeline — template-sync PRs fit this pattern without introducing a new primitive. Git subtree embeds the full template history into each product repo (noise) and still requires a per-product trigger. Manual pinning is incompatible with the autonomous fleet model. The sync job is a small coder-core extension consistent with ADR 0032 (extend coder-core, not a new service).

## Consequences

- `coder-product-template/package.json` carries a `TEMPLATE_VERSION` semver field; Developer bumps it on meaningful changes.
- `coder-core-template-sync-tick` (Cloud Scheduler, daily) reads the latest version and opens PRs to out-of-date live product repos targeting a `chore/template-sync-{version}` branch.
- Breaking changes to `theme.config.ts` schema bump the major version; the PR body includes a migration note flagged for operator review before merge.
- Sync PRs are merged by the standard Reviewer pipeline; no new approval gate is introduced.

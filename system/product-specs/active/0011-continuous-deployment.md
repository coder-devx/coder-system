---
id: "0011"
title: Continuous deployment
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-11
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0008"]
---

# Continuous deployment

**Phase:** Shipped
**Progress:** 6 / 6 acceptance criteria ✅

## Problem

Deploying `coder-core` and `coder-admin` is a manual process. Merges
to `main` don't automatically ship; a human must run deploy scripts,
run migrations, and watch for failures. This slows the dev loop and
introduces human error in the deploy sequence.

## Users / personas

- **Human operator** — wants push-to-main to mean deployed-to-prod
  without running any commands.
- **Developer worker** — its merged PRs should reach production
  automatically to close the feedback loop.

## Goals

- Automated deploy on every merge to `main` for both repos.
- Canary pattern: deploy without traffic first, health-check, then
  shift traffic only on success.
- Automated database migrations before traffic shift.
- Slack notification on success or failure.

## Non-goals

- Multi-region canary or gradual traffic shifting (100% cut-over).
- Rollback automation (manual runbook for now).
- Staging environment (prod-only pipeline).

## Scope

- GitHub Actions workflow in each repo triggered on push to `main`.
- Cloud Run deploy with `--no-traffic --tag=canary`.
- Health-check the canary URL before shifting traffic.
- `coder-core-migrate` Cloud Run Job for Alembic migrations, run
  before traffic shift.
- `gcloud run services update-traffic` to shift 100% on success.
- Slack webhook notification (success + failure); graceful degradation
  if webhook not configured.
- Runbooks updated for both services.

## Acceptance criteria

- [x] AC1: Merging to `main` in `coder-core` triggers an automated
  deploy with no manual steps.
- [x] AC2: Merging to `main` in `coder-admin` triggers an automated
  deploy with no manual steps.
- [x] AC3: The deploy uses a canary pattern — traffic shifts only after
  the canary health-check passes.
- [x] AC4: Alembic migrations run automatically before traffic shifts
  in `coder-core` deploys.
- [x] AC5: A Slack notification is sent on deploy success and failure
  (graceful degradation if webhook is not configured).
- [x] AC6: Runbooks for both services are updated to reflect the
  automated deploy flow.

## What shipped

Canary deploy pattern for both repos: deploy with `--no-traffic
--tag=canary`, health-check the canary URL, shift traffic only on
success. `coder-core-migrate` Cloud Run Job runs Alembic migrations
before traffic shift. Slack webhook notifications on success/failure
(graceful degradation if not configured). Runbooks updated for both
services.

## Links

- Related specs: [`0008`](./0008-onboard-first-two-projects.md)

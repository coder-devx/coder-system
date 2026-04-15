---
id: continuous-deployment
title: Continuous deployment
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-15
served_by_designs: [system-overview]
related_specs: []
---

# Continuous deployment

## What it is

Push-to-main auto-deploys both `coder-core` and `coder-admin` to
Cloud Run using a canary pattern: deploy with no traffic, health-check
the canary URL, then shift 100% of traffic. For `coder-core`, Alembic
migrations run as a Cloud Run Job before the traffic shift. A Slack
webhook announces success and failure; absence of the webhook is a
graceful degrade, not a failure. Operators no longer run deploy
commands by hand.

## Capabilities

- GitHub Actions workflow on push to `main` in each repo triggers a
  full deploy with no manual steps.
- Canary-first deploys: `gcloud run deploy --no-traffic --tag=canary`,
  health-check the `canary` URL, then
  `gcloud run services update-traffic` to 100%.
- `coder-core-migrate` Cloud Run Job runs Alembic migrations before
  traffic shifts on `coder-core` deploys.
- Slack notifications on success and failure; missing webhook config
  skips the notification without failing the job.
- Per-service runbooks document the automated flow and the manual
  rollback fallback.

## Interfaces

- GitHub Actions: `.github/workflows/deploy.yml` in both `coder-core`
  and `coder-admin` repos.
- Cloud Run services: `coder-core`, `coder-admin`.
- Cloud Run Job: `coder-core-migrate`.
- Slack: incoming webhook URL configured via repo secret.
- Runbooks: per-service deploy runbooks in each repo.

## Dependencies

- Cloud Run + `gcloud` CLI for deploy and traffic commands.
- Alembic migration chain in `coder-core`.
- GitHub Actions runners with deploy-time GCP credentials.
- Slack webhook (optional).
- Onboarded projects model — deploys are global, projects are tenants.

## Evolution

- `0011-continuous-deployment` — canary pattern, migrations job,
  Slack notifications, and runbooks for both services (2026-04-11).

## Links

- Designs: …
- Related components: …

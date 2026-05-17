---
id: continuous-deployment
title: Continuous deployment
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-13
last_verified_at: 2026-05-13
summary: Push-to-main CD with health checks.
served_by_designs: [system-overview]
related_specs: [escalations]
parent: delivery-and-infra
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
- **Alembic heads CI check.** The `check` workflow adds a conditional
  step: when a PR diff touches `migrations/versions/`, runs
  `uv run alembic heads | wc -l` and fails the job if the count
  exceeds one. PRs with no migration changes skip the step entirely
  (no Alembic init overhead on unrelated runs). Catches dual-head
  conflicts that bypass or pre-date the developer-worker gate.
- **Deploy-step migrate failure paging.** When the `coder-core-migrate`
  Cloud Run Job step exits non-zero, the deploy workflow fires the
  [escalations](../pipeline/escalations.md) surface with trigger kind
  `migrate_failure`, severity `high`, and a structured payload carrying
  the Cloud Run Job execution name and the Alembic error output. The
  existing Slack failure notification still fires; paging is additive.
  Distinguishes migrate failures from generic deploy failures so
  on-call knows to expect stuck-prod state.

## Interfaces

- GitHub Actions: `.github/workflows/deploy.yml` in both `coder-core`
  and `coder-admin` repos.
- GitHub Actions: `.github/workflows/ci.yml` in `coder-core`
  (alembic-heads check step).
- Cloud Run services: `coder-core`, `coder-admin`.
- Cloud Run Job: `coder-core-migrate`.
- Slack: incoming webhook URL configured via repo secret.
- Escalations API: `open_escalation` called with
  `trigger_kind='migrate_failure'` on migrate-step failure.
- Runbooks: per-service deploy runbooks in each repo.

## Dependencies

- Cloud Run + `gcloud` CLI for deploy and traffic commands.
- Alembic migration chain in `coder-core`.
- GitHub Actions runners with deploy-time GCP credentials.
- Slack webhook (optional).
- Onboarded projects model — deploys are global, projects are tenants.
- [escalations](../pipeline/escalations.md) — migrate-failure paging uses the
  `migrate_failure` trigger kind on the escalation surface.

## Evolution

- `0011-continuous-deployment` — canary pattern, migrations job,
  Slack notifications, and runbooks for both services (2026-04-11).
- **0082** — Alembic heads CI check (fails `check` job when a PR
  introduces >1 head under `migrations/versions/`; skips step when diff
  has no migration changes) and deploy-step migrate failure paging
  (fires `migrate_failure` escalation with severity `high` when
  `coder-core-migrate` exits non-zero; additive to existing Slack
  notification). Responds to the 2026-05-10 incident where 17 deploys
  failed silently at the migrate step.

## Links

- Designs: [system-overview](../../designs/active/system-overview.md)
- Related components: [observability](../pipeline/observability.md),
  [audit-log](../tenancy/audit-log.md), [onboarding](../knowledge/onboarding.md),
  [escalations](../pipeline/escalations.md)

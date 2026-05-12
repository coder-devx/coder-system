---
id: '0037'
title: Deploy-migrate failure paging via coder-core webhook over direct CI PagerDuty
  call
type: adr
status: proposed
date: '2026-05-12'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- 0082
---

# ADR 0037 — Deploy-migrate failure paging via coder-core webhook over direct CI PagerDuty call

## Context

Spec 0082 requires an immediate PagerDuty page when `alembic upgrade head` fails in the CI deploy job. The existing `Notify deploy failure` Slack step is insufficiently visible for a high-severity stuck-prod situation. Three routing options exist.

## Options considered

**Option A — Direct PagerDuty Events API v2 call from CI.** Add `PAGERDUTY_ROUTING_KEY` as a GitHub repo secret; curl Events API v2 from the deploy job. Simple, no coder-core change needed. Rejected: duplicates `projects.pagerduty_routing_key` (already stored in DB, migration 0048) outside the project's secret store; drift risk if the key rotates. No dedup, no audit events, no admin-panel visibility.

**Option B — Webhook to coder-core** (chosen). New `POST /v1/_hooks/github/migrate-failure`; CI POSTs on migrate failure; coder-core opens an escalation row via `escalations.open_escalation` and dispatches through the existing `dispatch_pagerduty` function.

**Option C — Extend escalation watcher to poll Cloud Run Job executions.** Watcher queries Cloud Run Jobs API for failed `coder-core-migrate` executions; no CI change. Rejected: up to 1-minute polling latency on a high-severity incident is unacceptable; requires `roles/run.viewer` on the watcher SA, broadening its IAM blast radius.

## Decision

Option B (webhook into coder-core).

## Rationale

Routing through `escalations.open_escalation` means the `pagerduty_routing_key` is read from the DB (no secret duplication), dedup is free via the existing partial unique index on `(project_id, trigger_kind) WHERE status='open'`, and `escalation.opened` / `escalation.rung_fired` events land in `audit_events`. The `dispatch_pagerduty` dispatcher and its `DispatchOutcome` error handling are already tested. The cost is one new webhook endpoint and one additional Secret Manager entry.

## Consequences

- New `deploy_migrate_failure` member added to the `trigger_kind` enum in `escalations`; requires a migration.
- New `direct_l2` policy in `config/escalation_policies.yaml`: single rung, PagerDuty immediately at `severity=high`. No L0/L1 dwell — migrate failures are high-severity by definition.
- `CODER_GITHUB_DEPLOY_WEBHOOK_SECRET` added to Secret Manager; `DEPLOY_WEBHOOK_SECRET` and `DEPLOY_WEBHOOK_URL` added as GitHub repo secrets/vars. Missing either → CI step skipped silently; Slack notification still fires.
- If coder-core is itself down when the migrate failure fires, the webhook call fails; Slack notification is the fallback signal. Acceptable: a coder-core outage is a higher-priority incident than the migrate failure itself.

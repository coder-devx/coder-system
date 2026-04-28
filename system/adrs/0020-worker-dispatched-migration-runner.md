---
id: "0020"
title: Migration runner is a worker-dispatched Cloud Run Job, not a sync API endpoint
type: adr
status: proposed
date: 2026-04-28
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: ["0047"]
---

# ADR 0020 — Migration runner is a worker-dispatched Cloud Run Job, not a sync API endpoint

## Context

Spec 0047 requires a mechanism that, given a migration file and a set of
managed projects, opens one reviewed PR per project per migration. Three
execution models were considered:

1. **Sync API endpoint** — `POST /v1/_admin/template/migrate` runs the
   migrations inline, within the API request handler, and returns once all
   PRs are opened (or errors out).
2. **Managed-workflow run** — a GitHub Actions workflow in `coder-system`
   drives the migration by calling the GitHub API directly, with per-project
   jobs dispatched as matrix entries.
3. **Worker-dispatched Cloud Run Job** — `POST /v1/_admin/template/migrate`
   dispatches a Cloud Run Job (`coder-core-template-migrate`) and returns a
   `run_id` immediately. The job runs asynchronously, writing state to the
   `template_migrations` table.

## Options considered

**Option A — Sync API endpoint**

- Simple: no additional infrastructure; the API handler opens PRs and returns.
- Risk: migrations touching 50 files × N projects involve dozens of sequential
  GitHub API calls. A 30-second API gateway timeout cuts the run mid-flight,
  leaving some rows in `status='pending'` with no PR opened and no clear
  recovery path for the half-done state.
- Risk: a panic or OOM in the migration code kills the API worker process,
  affecting all other in-flight requests. No isolation.
- Risk: `run_with_transient_retry` (ADR 0013) is designed for short-lived
  worker calls, not long-running batch operations. Retrying a half-completed
  migration sync inline is non-trivial.

**Option B — Managed-workflow run (GitHub Actions matrix)**

- Leverages existing GitHub Actions infrastructure; no Cloud Run Job to
  manage.
- Risk: GitHub Actions has a matrix limit (256 jobs) and per-job latency
  overhead. A fleet of 20+ projects × 5+ pending migrations = 100+ jobs;
  manageable today but fragile to scale.
- Risk: the migration code runs in the GitHub Actions runner environment, not
  in `coder_core`. Accessing Postgres (`template_migrations` table) requires
  exposing DB credentials to Actions runners, which broadens the secret scope.
- Risk: GitHub Actions logs are not in the same observability stack as
  `coder_core`; debugging a failed migration requires navigating to GitHub
  Actions rather than the admin panel.

**Option C — Worker-dispatched Cloud Run Job (this ADR)**

- `POST /v1/_admin/template/migrate` dispatches the Cloud Run Job with the
  requested filter args and returns `{run_id}` immediately.
- The job runs in the same VPC as `coder_core`, with full Postgres access,
  isolated from the API server's request handling.
- Long-running (seconds to minutes) without timeout risk.
- `run_with_transient_retry` applies to individual GitHub API calls within the
  job.
- Observability: job stdout/stderr → Cloud Logging; Prometheus metrics emitted
  at job end; audit events written to Postgres — all in the same stack as
  `coder_core`.
- Cloud Scheduler fires the same endpoint weekly with no filters, providing
  a catch-all tick for newly-landed migrations.

## Decision

Adopt **Option C**: migration execution is a worker-dispatched Cloud Run Job.

`POST /v1/_admin/template/migrate` accepts `{migration_numbers?, projects?,
dry_run?}`, dispatches `coder-core-template-migrate` with those args, and
returns `{run_id, scheduled_jobs: N}` immediately. The admin panel polls
`GET /v1/_admin/template/migrations` to show status; it does not need a
websocket or long-poll — status is read from the `template_migrations` table.

## Rationale

**Timeout safety is non-negotiable.** A migration that opens 10 PRs across 5
projects × 3 migrations involves 150+ GitHub API calls. No sync request
handler should run for that long against a shared API server.

**Isolation matters for correctness.** A Python exception in migration code
that kills the Cloud Run Job does not affect the API server's other request
handling. The failure is visible in Cloud Logging and the `template_migrations`
table; the API continues serving.

**The existing Cloud Run Job pattern is proven.** `coder-core` already uses
Cloud Run Jobs for the cold-start ingestion pipeline (spec 0045) and other
batch operations. The operational overhead (IAM role, job spec, monitoring) is
amortised across all jobs, not per-feature.

## Consequences

- **Positive.** No API timeout risk; migrations run to completion.
- **Positive.** Failure isolation; a bad migration code path doesn't affect
  the API server.
- **Positive.** Cloud Scheduler covers the weekly no-operator-needed cadence;
  manual trigger available via the admin endpoint.
- **Negative.** Run status is asynchronous — the admin must poll the fleet
  matrix to see results. Acceptable given that migrations are background
  operations, not interactive ones.
- **Follow-up.** If operators want real-time job output, Cloud Logging tail can
  be surfaced in the admin panel via a log-viewer embed; not in scope for v1.

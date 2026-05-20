---
id: '0035'
title: Founder as a recurring job over a normal dispatcher task
type: adr
status: proposed
date: '2026-05-10'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- coder-studio-founder
- studio-b2c-portfolio
---

# ADR 0035 — Founder as a recurring job over a normal dispatcher task

## Context

The Founder role surveys idea sources on a schedule, scores candidates, emits tasks into the dispatcher, and produces a weekly portfolio review. We had to decide how to trigger its execution and where it sits in the task model.

## Options considered

1. **Recurring job (Cloud Scheduler → Cloud Run Job)** — Founder runs as `coder-core-founder-tick`, parallel to `auto-approve-tick` and `self-heal-tick`. It reads fleet-wide portfolio state from Postgres, performs its analysis, and writes results plus any new tasks back. It is a task producer, not a task consumer.
2. **Normal dispatcher task, externally triggered** — a cron or webhook fires `POST /v1/projects/{id}/tasks` to create a Founder task. The Founder runs inside the standard task lifecycle (queued → running → succeeded/failed). Operator retries via the existing task-retry UI.
3. **Long-running Founder service** — a persistent Python process waking on a timer, independent of the Cloud Run Job model.

## Decision

Recurring job (option 1).

## Rationale

The Founder's scope is the entire fleet, not one project. Wrapping it as a dispatcher task (option 2) requires assigning it to a specific `project_id`, which violates the spirit of ADR 0005's `project_id` invariant — the Founder is deliberately cross-project. A synthetic trigger project obscures this in the audit log and creates a permanent conceptual exception. Option 3 is a persistent service for a role that runs for minutes per week; operational overhead is disproportionate. The recurring-job machinery already exists; Founder is a third instance of the pattern. Two modes (`idea-scan` and `weekly-review`) are separate Cloud Scheduler triggers pointing at the same Job binary with different `MODE` env vars, matching the existing pattern in `self-heal-tick`.

## Consequences

- Positive: no `project_id` ambiguity; Founder is explicitly fleet-level, surfaced at `GET /v1/admin/founder-job/runs`.
- Positive: operator pause via `POST /v1/admin/founder-job/pause` emits an audit event, consistent with other admin-job controls.
- Positive: Cloud Run Job retry policy (max-retries = 3, exponential backoff) handles transient failures without custom retry code.
- Negative: Founder results (candidate scores, weekly report body) must be written to Postgres for the admin panel to surface them, not to task messages. Mitigation: `founder_job_runs` table stores the report body; studio dashboard queries it directly.
- Negative: two Cloud Scheduler entries (`idea-scan`, `weekly-review`) must stay in sync with the coder-core deploy. Mitigation: Terraform manages both triggers referencing the deployed image tag.
- Follow-up: add `founder_job_runs` and `idea_queue` tables in the same migration batch as `project_kind`.

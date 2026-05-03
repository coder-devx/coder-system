---
id: '0063'
title: Compliance Gate Retry Visibility
type: spec
status: wip
owner: ro
created: '2026-05-03'
updated: '2026-05-03'
last_verified_at: '2026-05-03'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- observability
- admin-panel
parent: pipeline-operations
---

# Compliance Gate Retry Visibility

**Phase:** wip
**Progress:** 0 / 6 acceptance criteria

## Problem

The compliance gate re-prompts workers when their structured output
fails the strict-JSON contract (prose preamble, stray fence, bad
shape). Each retry is logged as `worker_output_compliance.retry` in
Cloud Logging, but that signal is buried — operators must know the
log name and write a manual query to see it. Prompt-quality
regressions surface weeks late, noticed only after elevated task
costs or a spike in outright failures forces an investigation.

Goal: make compliance retry rate per role per day as scannable as
daily cost — an operator opens the admin panel and spots a
regression within one calendar day of it starting.

## Users / personas

- **Operators** monitoring pipeline health via the admin panel
  (`/projects/{id}/metrics`) who currently have no visibility into
  compliance gate activity without Cloud Logging access.

## Goals

- Per-role-per-day retry counts and dominant `error_kind` visible in
  the admin panel; no Cloud Logging query required.
- A role-day with non-zero retries stands out visually in an
  otherwise clean table.
- Period selector (7d / 30d) consistent with the existing metrics page.

## Non-goals

- Slack alerts or automated escalation for retry-rate spikes (separate spec).
- Changing compliance gate behavior or retry limits.
- Fleet-level (cross-project) retry rollup — per-project view only.
- Breakdown by individual task or raw prompt text.

## Scope

- **Backend:** capture `retry_count` and `error_kind` per task
  completion into a `compliance_retry_events` table (or a lightweight
  daily rollup); expose via
  `GET /v1/projects/{id}/compliance-metrics?period=` returning
  per-role-per-day `{role, date, retry_count, dominant_error_kind}`
  rows.
- **Admin panel (`coder-admin`):** a new Compliance tab on the
  existing `/projects/{id}/metrics` page (or a parallel
  `/projects/{id}/compliance` route) with a period selector and a
  role × day table matching the existing metrics page layout. Behind
  `VITE_COMPLIANCE_METRICS_ENABLED` (default on).

## Acceptance criteria

- [ ] AC1: `GET /v1/projects/{id}/compliance-metrics?period=7d` returns
  per-role-per-day rows with `retry_count` and `dominant_error_kind`;
  days with zero retries for all roles are omitted from the response.
- [ ] AC2: The admin panel renders a Compliance tab (or route) reachable
  from `/projects/{id}/metrics` with a 7d / 30d period selector and a
  role × day table showing retry count and dominant error_kind per cell.
- [ ] AC3: Any cell where `retry_count > 0` is visually distinguished
  (non-zero count highlighted or colored) so regressions do not require
  scanning an all-zeros table.
- [ ] AC4: Injecting a synthetic compliance retry in a test-env task
  causes the corresponding role-day cell to reflect the increment on
  the next admin panel page load — no manual Cloud Logging query needed.
- [ ] AC5: The page renders an explicit empty-state message
  ("No compliance retries in this period") when the selected window
  contains no retries, rather than a blank or missing table.
- [ ] AC6: Setting `VITE_COMPLIANCE_METRICS_ENABLED=false` hides the
  tab / route entirely without breaking other admin panel views.

## Open questions

- Write retry events directly to Postgres at gate time (simpler, no
  migration lag) or re-parse the existing Cloud Logging sink (avoids
  a schema change but adds latency and coupling to log format)?

## Links

- Related specs: observability, admin-panel
- Designs: none yet

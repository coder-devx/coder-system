---
id: "0071"
title: Failure-mode grouping and operator runbooks
type: spec
status: wip
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
summary: ~
served_by_designs: ["0071"]
related_specs:
  - self-healing
  - escalations
  - observability
parent: ~
---

# Failure-mode grouping and operator runbooks

## Problem

The same Inbox walk on 2026-05-09 found 27 stuck developer tasks
across one project, with the same four failure modes repeating:

- `claude exited with code 1` × 6 (oldest 15d)
- `coder task deadline exceeded after 2400s` × 3 (oldest 12d)
- `ship gate failed: remote_missing` × 2 (oldest 4d)
- `executing stage reported success but produced no PR (pr_url is null)` × 1

Today every row is its own decision the operator has to research and
action. The same diagnostic question gets asked repeatedly. There is
no persistent record of "when X happens, do Y" — the knowledge lives
in heads and Slack threads.

In parallel, **zero of those 27 tasks have triggered an escalation**.
The escalation watchdog (WIP 0041) either does not classify
dev-task stalls as escalation-worthy or is mis-rated; either way the
human-in-the-loop machinery promised by the design doc is silently
absent for the most common failure shape we have.

## Users / personas

- **Operator triaging Now.** Today: opens 6 task pages with the same
  symptom, makes 6 retry decisions. After: one row, one decision,
  one bulk action. Optionally one click to apply the matched
  runbook to the whole group.
- **System Admin worker / human admin.** Today: keeps a private
  list of "if you see X, try Y". After: writes that list as a
  runbook artifact under `system/runbooks/failure-modes/{slug}.md`.
- **PM worker / Architect worker auditing failures.** Today: queries
  the database. After: reads the runbook list to see which failure
  modes have a documented response and which don't.

## Goals

When this ships:

- Now (WIP 0070) groups stuck tasks by `failure_kind` per project.
  Six identical "claude exited code 1" rows become one
  `stuck-group` row with count, age range, and bulk-action buttons.
- Each known `failure_kind` resolves to a runbook artifact, queried
  through the Knowledge API. Runbooks are markdown under
  `system/runbooks/failure-modes/{slug}.md` with typed frontmatter
  (`failure_kind`, `detection_signal`, `suggested_action`,
  `owning_role`).
- The escalation watchdog (WIP 0041) is reviewed and updated so that
  ≥1 of the four observed failure modes triggers an escalation under
  documented thresholds.
- Bulk-action endpoints accept a `failure_kind` filter and operate
  on every matching open task in scope, with one `audit_event` per
  affected task and one `correlation_id` shared across the batch.

## Non-goals

- Auto-applying runbook actions without operator confirmation. This
  spec wires the tooling; auto-apply is a follow-on under the
  self-healing umbrella, not here.
- Defining a new escalation taxonomy. We use the existing one; we
  audit and tune the rules to cover the observed gap.
- Replacing the runbook surface that already exists for
  `pipeline-run-blocked` etc. — we extend the same pattern to a
  new sub-folder, not a new schema.

## Scope

In:

- New knowledge artifact subtype `failure-mode runbook` under
  `system/runbooks/failure-modes/`. Frontmatter: `id`, `title`,
  `failure_kind` (matches `tasks.failure_kind` enum), `signal`
  (regex/predicate over `failure_detail` text),
  `suggested_action` (one of: `retry`, `retry_with_edit`,
  `escalate`, `manual_only`), `owning_role`, `last_verified_at`.
- Knowledge API extension: `GET /v1/knowledge/runbooks/by-failure?kind=…`
  returning the matched runbook for that `failure_kind` if one
  exists.
- Aggregation API: extend the Now / inbox aggregator (WIP 0070) to
  group open `stuck` tasks by `(project_id, failure_kind)`. A group
  becomes a single `stuck-group` row when it contains ≥ 3 tasks; <3
  remain individual `stuck-task` rows.
- Bulk action endpoints: `POST /v1/projects/{id}/tasks:bulk-retry`
  with body `{failure_kind, max_age_seconds}` and the equivalent
  for `:bulk-cancel`. Each call writes per-task audit events
  sharing one `correlation_id`.
- A `/runbooks/{slug}` admin route rendering the markdown body, the
  matched runbook frontmatter, and the count of currently-matching
  open tasks with a `[run on N matched]` button (which calls the
  bulk endpoint).
- The grouped row's runbook panel (per WIP 0070 design) embeds the
  same runbook content as a collapsible card.
- Escalation watchdog audit + rule update: at least one of `claude
  exited code 1`, `task deadline exceeded`, `ship gate failed:
  remote_missing` triggers an escalation under explicit thresholds
  (e.g. "≥3 of the same failure_kind in 24h" or "any single task
  stuck > 48h").

Out:

- Auto-applying suggested actions.
- A new escalation channel (Slack / PagerDuty config). We use what
  exists.
- Runbook authoring UI in the panel — runbooks are authored via
  PR like every other knowledge artifact.

## Acceptance criteria

- **AC1.** Now (WIP 0070) renders `stuck-group` rows when ≥ 3 open
  tasks in the same project share a `failure_kind`. The group row
  shows `{count} tasks · oldest {age}` and exposes
  `[retry all] [run runbook] [open all]` inline actions.
- **AC2.** At least three failure-mode runbooks exist under
  `system/runbooks/failure-modes/`: `claude-exit-1.md`,
  `coder-task-deadline-exceeded.md`, `ship-gate-remote-missing.md`.
  Each has the required frontmatter and a body covering detection
  signal, why-it-happens, suggested-action, owning-role.
- **AC3.** `GET /v1/knowledge/runbooks/by-failure?kind=claude_exit_1`
  returns the matched runbook frontmatter + rendered markdown
  within 200ms p95; an unmatched `kind` returns `404` with a
  `next-action: write-runbook` hint pointing at a stub creation
  flow.
- **AC4.** Bulk-retry called with `{failure_kind, max_age_seconds}`
  re-enqueues every matching open task and writes one
  `audit_event` per task; all events share one `correlation_id`
  recoverable from the response.
- **AC5.** Escalation watchdog rule audit ships as a documented
  diff in the escalation rules: at least one rule covers
  `failure_kind=claude_exit_1` with a stated threshold; existing
  alerts are not regressed.
- **AC6.** A `/runbooks/{slug}` admin route exists, renders the
  matching runbook, and shows the live count of matching open
  tasks with an inline `[run on N matched]` action.
- **AC7.** A "missing runbook" CTA appears on a `stuck-group` row
  whose `failure_kind` has no runbook; clicking it opens a
  pre-filled markdown stub in the runbook author flow (PR or
  in-panel knowledge editor — whichever exists).

## Metrics

- Number of distinct rows on Now for the same `failure_kind` per
  project: collapses from current N (up to 6) to 1.
- Time-to-resolve a failure-mode group (first stuck task → all
  resolved): drops from days to minutes for runbook-covered modes.
- Escalation count for repeated dev-task stalls: rises from 0
  (today) to ≥1 per 7d when the threshold rule fires; not a metric
  to optimise, a metric to confirm the watchdog is alive.

## Open questions

- Threshold for the auto-collapse to `stuck-group`. 3 feels right
  for the observed shape; revisit on first 30d soak.
- Whether the runbook author flow uses the existing knowledge editor
  (WIP 0035) or a stripped-down inline form. Defer to design.

## Links

- ADR: [0031](../../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- Design: [0071](../../designs/wip/0071-failure-mode-grouping-and-runbooks.md)
- Depends on: [0069](./0069-canonical-project-state.md), [0070](./0070-now-landing-surface.md)
- Related: [self-healing](../active/pipeline/self-healing.md), [escalations](../active/pipeline/escalations.md), [observability](../active/pipeline/observability.md)

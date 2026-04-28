---
id: "0019"
title: Alias-tolerance window closes on fleet completion, not a fixed deadline
type: adr
status: proposed
date: 2026-04-28
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: ["0047"]
---

# ADR 0019 — Alias-tolerance window closes on fleet completion, not a fixed deadline

## Context

When a rename migration lands in `coder-system` (e.g., `affects_services` →
`relates_to_services`), the CI validator (ADR 0008) must accept both the old
and new field names until every managed project has merged the migration PR.
If the validator stops accepting the old name before a project migrates, any
PR opened on that project's knowledge repo will fail CI — even if that PR has
nothing to do with the rename.

The alias is registered via `VALIDATOR_ALIASES` in the migration file, which
the `coder-system` registration CI extracts into
`system/migrations/validator-aliases.yaml`. The alias entry has a `retired_at`
field. Two strategies were considered for setting `retired_at`:

1. **Fixed calendar deadline** — the alias expires N days after the migration
   merged to `coder-system` (e.g., 30 days). After that, the validator
   rejects the old name regardless of project migration status.
2. **Fleet-completion gate** — the alias expires when the fleet matrix shows
   100% adoption (all managed projects have `template_version >=
   migration.TARGET_VERSION`). The runner opens a `coder-system` PR to retire
   the alias once it confirms full adoption.

## Options considered

**Option A — Fixed calendar deadline (30 days)**

- Simple: a cron job or operator reminder can retire aliases on a schedule.
- Predictable: schema authors know exactly when old names become invalid.
- Risk: a project with low PR activity (e.g., only 1–2 merges a month) may not
  have merged the migration PR before the deadline. Their CI breaks on any
  unrelated PR. The operator must either extend the deadline or force-close the
  migration PR without a proper review.
- Risk: the deadline is arbitrary. 30 days is too short for a fleet that moves
  slowly; 90 days lets old names linger longer than useful. Any fixed value is
  wrong for some fleet cadence.

**Option B — Fleet-completion gate (this ADR)**

- The alias window is tied to an observable fact: every project has adopted the
  rename. The alias cannot be retired prematurely.
- Risk: if a project permanently stalls (abandoned migration PR, project
  frozen), the alias never retires. The validator carries a growing alias list.
- Mitigation: the admin matrix flags PRs open > 14 days; the operator can
  force-close an abandoned PR, mark the row `abandoned`, and the migration is
  re-issued with a new number. Alias retirement can be triggered manually once
  the operator confirms all active projects have adopted the rename.

## Decision

Adopt **Option B**: the alias-tolerance window is fleet-completion-gated.
`retired_at` in `validator-aliases.yaml` is set by a `coder-system` PR
opened by the runner (or manually by the operator) once the fleet matrix shows
100% adoption.

A migration with a permanently stalled project is handled by marking that
project's row `abandoned` and re-issuing the migration; the alias retires once
the new migration number reaches 100% adoption.

## Rationale

**The purpose of the alias is to protect mid-migration projects.** A deadline
that expires while a project is still migrating is a violation of the
alias's own purpose. The fleet-completion gate is the only design that
guarantees the invariant "no project's CI is broken by an alias retirement."

**Fleet cadence is not predictable.** The system today has 2–3 managed
projects. In a year it may have 10. The merge cadence of each project varies.
A fixed 30-day window that works today may be inadequate at 10 projects; a
90-day window that works at 10 projects is unnecessarily long today. The
fleet-completion gate is automatically correct for any fleet size.

**Alias lists stay small in practice.** A rename migration is a high-friction
operation (requires alias-tolerance pre-work). The fleet will not accumulate
dozens of live aliases; each one resolves within days to weeks of the migration
shipping.

## Consequences

- **Positive.** No project's CI is broken by a premature alias retirement.
- **Positive.** Alias retirement is automatic once fleet-sealed, not a
  calendar reminder.
- **Negative.** A permanently stalled project blocks alias retirement
  indefinitely. Operator must intervene (close + re-issue). The admin matrix
  makes stall visible at > 14 days.
- **Follow-up.** The runner's post-migration sweep (checking for 100% adoption)
  runs on every weekly tick; once all rows for a migration reach `merged`, it
  opens the `coder-system` alias-retirement PR automatically.

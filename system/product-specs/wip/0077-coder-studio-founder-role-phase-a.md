---
id: '0077'
title: Coder Studio — Founder role Phase A
type: spec
status: wip
owner: ro
created: '2026-05-10'
updated: '2026-05-10'
last_verified_at: '2026-05-10'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- '0075'
parent: knowledge-and-admin
---

# Coder Studio — Founder Role Phase A

**Phase:** A — Foundations and Founder
**Progress:** 0 / 8 acceptance criteria

## Problem

Spec 0075 commits to a Founder recurring job but defines it alongside a larger Studio surface. Phase A's end-condition — the Founder's idea selection has earned the operator's trust — requires a focused spec that names exactly what ships before any other Studio role exists. Without it, the Developer has no contract and the PM has no ACs to close Phase A against.

## Users / personas

**Portfolio operator.** Reviews the Founder's idea pipeline, approves bets, and reads live-product status roughly one day per week. The Studio admin panel is their entire Founder interface.

## Goals

When this spec ships the operator can:
- See the last idea cycle timestamp, next scheduled run, and trigger a cycle on demand.
- Read the weekly portfolio review as a required-review Now item within 15 minutes of completion.
- Act on Idea Queue rows that link to the cycle that produced them; approve an idea and see a PM draft task emitted with a repo placeholder.
- Pause and resume the Founder from the sidebar, with a visible banner and audit trail.
- Track calibration progress (N of 12 cycles, top-pick match rate) and mark Phase A complete after cycle 12.

## Non-goals

- Idea-source plugin architecture — Phase B+; Phase A hardcodes the source list.
- Scoring algorithm — the Founder prompt's concern, not this spec.
- `coder-product-template` instantiation — a separate Phase A spec covers repo scaffolding.
- Designer, Marketer, Analyst, Researcher roles — later phases.
- Terraform for production deployment of the Founder Cloud Run Job.

## Scope

The Founder runs as Cloud Run Job `coder-core-founder` (reusing the coder-core image, entry module `coder_core.workers.founder`). Two Cloud Scheduler triggers: `coder-founder-idea-tick` (daily) and `coder-founder-review-tick` (weekly, Sunday 18:00 UTC). Job concurrency=1, max-retries=0. Idempotency via `UNIQUE(project_id, idea_hash)` on the idea queue. `projects.founder_paused` is checked at Job entry; all side effects flow through `record_audit_event`.

**Idea cycle surface.** Studio sidebar header: `Last idea cycle` (ISO, human-relative), `Next scheduled`, `[Run idea cycle now]` (calls `POST /v1/projects/{id}/founder/run?mode=idea_cycle`). A **Founder activity** panel below the queue renders the last 10 `founder_cycles` rows of `cycle_type=idea_cycle`: timestamp, outcome (`emitted` / `no_candidate` / `paused` / `failed`), ideas-scored count, one-line reason for `failed` rows.

**Portfolio review.** Weekly Job run produces a Markdown report card — one `##` section per live `b2c_product` project: MRR, month-to-date cost, PostHog funnel snapshot (visitors → signups → activations → paying), kill-criteria status per charter criterion. A `FOUNDER_REVIEW` Now item is created within 15 minutes of Job completion. Acknowledging sets `founder_cycles.outcome = 'reviewed'` and clears the required-review badge.

**Idea queue affordances.** Each row carries a clickable `cycle` chip (short `founder_cycles.id`) linking to its activity row. `[approve]` emits a PM draft task with `repo = studio-{slugified-title}` (placeholder; actual scaffolding is out of scope for Phase A) and writes an `idea_approved` audit event correlated by cycle id.

**Pause / resume.** `POST /v1/projects/{id}/founder/pause` sets `projects.founder_paused = TRUE` and writes a `founder_paused` audit event (actor from admin JWT). Yellow banner across Studio mode: Founder paused since {timestamp} by {actor}. `POST /v1/projects/{id}/founder/resume` clears the flag, writes `founder_resumed`, removes the banner.

**Calibration dogfood.** Runs against the Coder project. Sidebar header calibration card: `Cycle N of 12 · Top pick matched operator: K of N`. After cycle 12, a `FOUNDER_CALIBRATION_COMPLETE` required-review Now item appears; acknowledging marks Phase A complete.

## Acceptance criteria

- **AC1.** The Studio sidebar header shows `Last idea cycle` (human-relative), `Next scheduled`, and `[Run idea cycle now]`. The Founder activity panel shows the last 10 idea-cycle rows: timestamp, outcome, ideas-scored count; `failed` rows include a one-line reason.
- **AC2.** The weekly portfolio review appears in the Now feed as a required-review `FOUNDER_REVIEW` item within 15 minutes of Job completion, with one `##` section per live `b2c_product` project. Acknowledging sets `founder_cycles.outcome = 'reviewed'` and clears the required-review badge.
- **AC3.** Each Idea Queue row carries a clickable `cycle` chip (short `founder_cycles.id`). `[approve]` emits a PM draft task with `repo = studio-{slugified-title}` (placeholder) and writes an `idea_approved` audit event recoverable by cycle id from the audit log page.
- **AC4.** The `[Pause Founder]` / `[Resume Founder]` toggle calls the pause/resume endpoints. While paused, a yellow banner displays: Founder paused since {timestamp} by {actor}. Both actions produce `founder_paused` / `founder_resumed` audit events with actor visible on the audit log page.
- **AC5.** The calibration card in the Studio sidebar header shows `Cycle N of 12 · Top pick matched operator: K of N` after each idea cycle against the Coder dogfood context. After cycle 12, a `FOUNDER_CALIBRATION_COMPLETE` required-review Now item appears; acknowledging marks Phase A complete.
- **AC6.** After `coder-core-founder` is added, the `coder-core-self-heal-tick` and `coder-core-auto-approve-tick` Cloud Scheduler jobs continue to execute on their existing schedules and produce `succeeded` outcomes without changes to their invocation targets, schedules, or retry policies.
- **AC7.** If Cloud Scheduler retries the same `idea-tick` execution after a transient failure, the Idea Queue entry count does not increase. The `UNIQUE(project_id, idea_hash)` constraint absorbs the duplicate; the retry's `founder_cycles` row records `no_candidate`.
- **AC8.** When `projects.founder_paused = TRUE`, the next scheduled `idea-tick` and `review-tick` each write a `founder_cycles` row with `outcome = 'paused'` and exit without scoring sources or emitting PM draft tasks.

## Open questions

- Calibration feedback storage: a JSON field on `founder_cycles` vs. a child `founder_cycle_feedback` table. Defer to Architect design.
- `POST /v1/projects/{id}/founder/run` — Cloud Run Job invocation vs. in-process async. Architect design owns this.
- 15-minute `FOUNDER_REVIEW` SLA assumes dogfood scale; verify against p99 Job runtime before committing for production.

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`
- Parent spec: [0075 — Coder Studio B2C product portfolio operator contract](../wip/0075-coder-studio-b2c-product-portfolio-operator-contract.md)
- ADR 0027 (role folder shape), ADR 0011 (recurring-job lifecycle)

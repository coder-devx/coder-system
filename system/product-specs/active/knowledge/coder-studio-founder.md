---
id: coder-studio-founder
title: Coder Studio — Founder Role Phase A
type: spec
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-15
last_verified_at: 2026-05-15
summary: Founder Cloud Run Job — idea cycles, portfolio reviews, pause/resume, and Phase A calibration dogfood.
served_by_designs: []
related_specs:
  - admin-panel
  - self-healing
  - task-orchestration
  - audit-log
parent: knowledge-and-admin
---

# Coder Studio — Founder Role Phase A

## Problem

The Studio needs a Founder agent that selects ideas, reviews live products, and earns operator trust before any other Studio role ships. Without a focused spec naming exactly what ships in Phase A, the Developer has no contract and the PM has no ACs to close Phase A against.

## Users

**Portfolio operator.** Reviews the Founder's idea pipeline, approves bets, and reads live-product status roughly one day per week. The Studio admin panel is their entire Founder interface.

## Goals

- See the last idea cycle timestamp, next scheduled run, and trigger a cycle on demand.
- Read the weekly portfolio review as a required-review Now item within 15 minutes of completion.
- Act on Idea Queue rows that link to the cycle that produced them; approve an idea and see a PM draft task emitted with a repo placeholder.
- Pause and resume the Founder from the sidebar, with a visible banner and audit trail.
- Track calibration progress (N of 12 cycles, top-pick match rate) and mark Phase A complete after cycle 12.

## Non-goals

- Idea-source plugin architecture (Phase B+; Phase A hardcodes the source list).
- Scoring algorithm (Founder prompt's concern, not this spec).
- `coder-product-template` instantiation (separate Phase A spec covers repo scaffolding).
- Designer, Marketer, Analyst, Researcher roles (later phases).
- Terraform for production deployment of the Founder Cloud Run Job.

## Scope

**Job infrastructure.** Cloud Run Job `coder-core-founder` (reuses coder-core image, entry module `coder_core.workers.founder`). Two Cloud Scheduler triggers: `coder-founder-idea-tick` (daily) and `coder-founder-review-tick` (weekly, Sunday 18:00 UTC). Job concurrency=1, max-retries=0. Idempotency via `UNIQUE(project_id, idea_hash)` on the idea queue. `projects.founder_paused` checked at Job entry; all side effects flow through `record_audit_event`.

**Idea cycle surface.** Studio sidebar header: `Last idea cycle` (ISO, human-relative), `Next scheduled`, `[Run idea cycle now]` (calls `POST /v1/projects/{id}/founder/run?mode=idea_cycle`). A **Founder activity** panel renders the last 10 `founder_cycles` rows of `cycle_type=idea_cycle`: timestamp, outcome (`emitted` / `no_candidate` / `paused` / `failed`), ideas-scored count, one-line reason for `failed` rows.

**Portfolio review.** Weekly Job run produces a Markdown report card — one `##` section per live `b2c_product` project: MRR, month-to-date cost, PostHog funnel snapshot (visitors → signups → activations → paying), kill-criteria status. A `FOUNDER_REVIEW` Now item appears within 15 minutes of Job completion. Acknowledging sets `founder_cycles.outcome = 'reviewed'` and clears the required-review badge.

**Idea queue affordances.** Each row carries a clickable `cycle` chip (short `founder_cycles.id`) linking to its activity row. `[approve]` emits a PM draft task with `repo = studio-{slugified-title}` (placeholder) and writes an `idea_approved` audit event correlated by cycle id.

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

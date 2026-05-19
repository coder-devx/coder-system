---
id: coder-studio-founder
title: Coder Studio — Founder Role Phase A
type: spec
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-19
last_verified_at: 2026-05-19
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

## What it is

The Founder is the first Studio role: a Cloud Run Job that selects and
ranks product ideas, reviews live products against the charter on a
weekly cadence, and earns operator trust before any other Studio role
ships. The Studio admin panel is the operator's entire Founder
interface — there is no separate Founder CLI or surface. Phase A
hardcodes the idea-source list and ships the operator-visible loop end
to end; later phases will plug in additional sources, designer /
marketer / analyst / researcher roles, and a production deployment
path.

## Capabilities

- **Idea cycle.** A Cloud Scheduler trigger (`coder-founder-idea-tick`,
  daily) invokes the `coder-core-founder` Cloud Run Job in
  `mode=idea_cycle`. The Job scores candidates against charter category
  constraints and appends ranked ideas to the Idea Queue. Idempotent
  via `UNIQUE(project_id, idea_hash)` — duplicate retries record the
  `founder_cycles` row as `no_candidate` without inflating the queue.
- **Weekly portfolio review.** A second Cloud Scheduler trigger
  (`coder-founder-review-tick`, Sunday 18:00 UTC) runs the Job in
  `mode=review`. It produces a Markdown report card — one `##` section
  per live `b2c_product` project, with MRR, month-to-date cost,
  PostHog funnel snapshot, and kill-criteria status — and surfaces it
  in the operator's Now feed as a `FOUNDER_REVIEW` required-review
  item within 15 minutes of completion. Acknowledging the Now item
  sets `founder_cycles.outcome = 'reviewed'` and clears the badge.
- **Studio sidebar header surface.** Shows `Last idea cycle` (ISO,
  human-relative), `Next scheduled`, and `[Run idea cycle now]` (calls
  the on-demand run endpoint). A **Founder activity** panel renders
  the last 10 `founder_cycles` rows of `cycle_type=idea_cycle`:
  timestamp, outcome (`emitted` / `no_candidate` / `paused` / `failed`
  / `reviewed`), ideas-scored count, and a one-line reason for
  `failed` rows.
- **Idea Queue affordances.** Each row carries a clickable `cycle`
  chip (short `founder_cycles.id`) linking to its activity row.
  `[approve]` emits a PM draft task with
  `repo = studio-{slugified-title}` (placeholder) and writes an
  `idea_approved` audit event correlated by cycle id.
- **Pause / resume.** Operator-controlled. While paused, a yellow
  banner across Studio mode shows "Founder paused since {timestamp} by
  {actor}". Scheduled `idea-tick` and `review-tick` runs during a
  paused window write a `founder_cycles` row with `outcome = 'paused'`
  and exit without scoring or dispatching.
- **Calibration dogfood.** Phase A runs against the Coder project
  itself as test bed. A sidebar header calibration card shows
  `Cycle N of 12 · Top pick matched operator: K of N`. After cycle 12
  a `FOUNDER_CALIBRATION_COMPLETE` required-review Now item appears;
  acknowledging it marks Phase A complete.
- **Audit attribution.** All Founder side effects (cycle outcomes,
  idea approve, pause / resume) flow through `record_audit_event` —
  every operator-visible mutation has a row recoverable from the audit
  log page.

## Interfaces

- **Cloud Run Job:** `coder-core-founder` (reuses the coder-core
  image; entry module `coder_core.workers.founder`; concurrency=1,
  max-retries=0).
- **Cloud Scheduler triggers:** `coder-founder-idea-tick` (daily),
  `coder-founder-review-tick` (weekly, Sunday 18:00 UTC). The existing
  `coder-core-self-heal-tick` and `coder-core-auto-approve-tick` jobs
  continue on their existing schedules unchanged.
- **On-demand run:** `POST /v1/projects/{id}/founder/run?mode=idea_cycle`.
- **Pause / resume:** `POST /v1/projects/{id}/founder/pause` and
  `POST /v1/projects/{id}/founder/resume`. Pause sets
  `projects.founder_paused = TRUE` and writes a `founder_paused` audit
  event (actor from admin JWT); resume clears the flag and writes
  `founder_resumed`.
- **Now feed:** `FOUNDER_REVIEW` and `FOUNDER_CALIBRATION_COMPLETE`
  required-review items.

## Dependencies

- [admin-panel](./admin-panel.md) — Studio sidebar header, Founder
  activity panel, Idea Queue, calibration card, pause / resume toggle,
  and Now feed rendering all live in the admin SPA.
- [self-healing](./self-healing.md) — reuses the Cloud Run Job +
  Scheduler tick pattern (`coder-core-self-heal-tick`).
- [task-orchestration](../pipeline-operations.md) — `[approve]`
  dispatches a PM draft task through the standard pipeline.
- [audit-log](../tenancy-and-access.md) — every Founder side effect
  emits an `audit_event` recoverable from the audit log page.
- `projects.founder_paused` column — checked at Job entry.

## Evolution

- 2026-05-15 — Phase A ship (spec 0077): Cloud Run Job, daily idea
  tick + weekly review tick, sidebar header + activity panel, Idea
  Queue cycle chip + approve audit event, pause / resume with banner,
  twelve-cycle calibration dogfood against the Coder project.

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Portfolio contract: [studio-b2c-portfolio](../studio-b2c-portfolio.md)
- Studio index: [studio](./studio.md)
- Related: [admin-panel](./admin-panel.md),
  [self-healing](./self-healing.md)

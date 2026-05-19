---
id: studio-b2c-portfolio
title: Studio — B2C product portfolio operator contract
type: spec
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-15
last_verified_at: 2026-05-15
summary: "B2C product portfolio: project kind, Studio sidebar, Founder job, kill workflow, scaffold, and Stripe/PostHog wiring."
served_by_designs: []
related_specs: [studio, admin-panel, worker-roles, task-orchestration, self-healing]
parent: studio
---

# Studio — B2C product portfolio operator contract

**Phase:** A — Foundations and Founder

## Problem

Coder today builds and operates internal tooling only. Every project
the fleet has shipped sits behind a login, solving a problem its
operator already knew about. Operators who want to demonstrate Coder's
capability to a skeptical external audience have no live evidence to
point at.

The Studio closes this gap: a portfolio of B2C products built and
operated autonomously by the Coder fleet, live on the public internet,
used by real strangers. The portfolio is the demonstration and the
marketing artifact simultaneously. Quality, transparency, and
build-in-public posture (defined in `system/STUDIO_CHARTER.md`) are
operator-visible constraints enforced in the admin panel, not
aspirations in a README.

## Users

- **Portfolio operator.** Reviews the Founder's idea pipeline, approves
  the next bet, reviews live-product metrics, and makes kill or invest
  decisions. The admin panel is their entire Studio interface.

## Goals

When Phase A ships:

- `project_kind = b2c_product` is a first-class type in the project
  list and switcher, visually distinct from `internal_tool` projects.
- A Studio sidebar section appears in the admin panel with an Idea
  Queue and Portfolio table.
- The Founder recurring job runs weekly, surfaces ranked ideas for
  operator approval, and emits a per-product review report in the
  operator's Now feed.
- Stripe Connect and PostHog are wired per-product; connection state
  and funnel data appear on each product-detail view.
- The `coder-product-template` scaffold deploys a Cloud Run service to
  a Cloudflare-managed domain inside a single pipeline run, no operator
  SSH or manual provisioning required.

## Non-goals

- Native mobile — App Store cycle incompatible with the autonomous
  deploy loop; charter-excluded in v1.
- Specific product categories — the Founder agent selects candidates;
  this spec defines the system contract, not the content.
- The polymorphic `project_kind` vs. separate product entity ADR —
  Architect owns that decision.
- Paid acquisition strategy — off by default; campaigns over $500 are
  explicit out-of-band operator decisions.
- Social platform presence — charter excludes any surface requiring an
  agent to operate as a person.
- Phase B–D roles (Designer, Marketer, Analyst, Researcher) — deferred;
  permission table exists in WIP 0075 for Architect reference.

## Acceptance criteria

- **AC1.** The admin panel renders a `b2c_product` type badge on all
  Studio projects in the project list and project switcher. A
  `b2c_product` project-detail view shows: Stripe connected-account
  state chip, monthly cost meter with $100 and $300 threshold lines,
  PostHog funnel snapshot (visitors → signups → activations → paying),
  and a kill-criteria tracker showing each charter criterion, its
  current status, and elapsed time when violated.
- **AC2.** The Studio sidebar section appears when at least one
  `b2c_product` project exists. It contains Idea Queue, Portfolio
  table, and per-product detail with the actions described in Scope.
  The Idea Queue is empty until the Founder's first run; the Portfolio
  table renders a row for each `b2c_product` project immediately on
  project creation.
- **AC3.** The Founder recurring job runs on a configurable schedule
  (default: Monday 09:00 UTC). Its weekly-review output appears in the
  operator's Now feed as a required-review item within 15 minutes of
  job completion. The idea cycle appends at least one ranked candidate
  to the Idea Queue on each run.
- **AC4.** `[approve]` on an Idea Queue row triggers a PM draft task
  for the idea and removes the row from the queue. `[reject]` applies
  a decay factor and re-ranks. Both actions write `audit_event` rows
  recoverable from the audit log page with the idea's queue entry id as
  correlation.
- **AC5.** A `b2c_product` project is scaffolded from
  `coder-product-template` (Next.js + Stripe + PostHog + Resend +
  legal pages pre-wired). The resulting Cloud Run service is reachable
  at a Cloudflare-managed domain within the same pipeline run that
  creates the project — no operator SSH, no manual DNS configuration.
- **AC6.** Stripe Connect and PostHog are wired: the Stripe state chip
  reflects the real OAuth connection state; the PostHog funnel snapshot
  populates from the project's PostHog project within 24 hours of the
  first event emitted by the deployed product.
- **AC7.** After at least twelve Founder idea-cycle runs against a
  dogfood context (the Coder project itself as test bed), the operator
  can confirm that the Founder's top-ranked candidate matched the
  operator's own top pick in at least 7 of 12 cycles. This criterion is
  met when the operator marks the Founder-calibration checklist
  complete on the Studio admin page; the checklist is surfaced as a
  required Now item after the twelfth cycle.

## Scope

### project_kind: b2c_product

The project list and switcher each gain a type badge: `internal_tool`
(existing, retroactively badged) and `b2c_product` (Studio). A
`b2c_product` project-detail view replaces the standard pipeline tab
with a Studio-flavoured view: Stripe connected-account state chip,
monthly cost meter ($100 and $300 threshold lines), PostHog funnel
snapshot (visitors → signups → activations → paying), and
kill-criteria tracker (five charter criteria with status and elapsed
time when violated).

### Studio sidebar

When at least one `b2c_product` project exists the sidebar gains a
**Studio** section with three entries:

- **Idea Queue** — ranked candidates from the Founder awaiting operator
  action. Each row: title, one-line pitch, category, estimated monthly
  cost, Founder confidence score (0–100). Actions: `[approve]` (emits
  PM draft task, removes from queue, writes `audit_event`); `[reject]`
  (applies decay factor, re-ranks, writes `audit_event`); `[ask
  Founder]` (opens `/drive/{project}/founder`; requires WIP 0073 drive
  mode — button grayed with tooltip if unavailable).
- **Portfolio** — table of all Studio products: name, launch date,
  current MRR (or $0), monthly spend, status (live /
  in-remediation / archived). Row click navigates to product-detail.
- **Per-product detail** — operator actions: `[flag for sunset]`,
  `[pause Founder reviews]`, `[view build artifacts]`.

### Founder recurring job

The Founder runs as a scheduled recurring job — same Cloud Run Job
machinery as `self-heal-tick` — not as a dispatcher task. Two modes:

- **Weekly review** (default: Monday 09:00 UTC; operator-triggered
  re-run available from the Studio sidebar header). Reads all live
  products' PostHog aggregates, Stripe MRR, and cost data; emits a
  Markdown report card per product; flags products meeting any kill
  criterion. Report appears in the operator's Now feed as a
  required-review item within 15 minutes of job completion.
- **Idea cycle** (runs after every weekly review). Surveys approved
  idea sources, scores candidates against charter category constraints,
  appends ranked ideas to the Idea Queue.

On-demand run: `POST /v1/projects/{id}/studio/founder/run?mode=idea_cycle`
(design decision deferred to Architect).

### Kill workflow

The operator flags a product via `[flag for sunset]` on the
product-detail card. A confirmation dialog shows: which kill criteria
are met and since when, revenue-to-date (for refund scoping), and the
downstream cascade — Stripe revoke, source-repo archive, DNS redirect
to a "no longer maintained" notice, Resend notification to paying
customers with refund details. On `[confirm sunset]` coder-core
dispatches a `kill_pipeline` task with a live status stream per step.
The product moves to "archived" in the Portfolio table with final
metrics frozen. Teardown artifacts are committed to the project
knowledge repo.

### Designer gate (Phase A, operator-overridable)

A product reaches launch only after the Designer emits a passing
`design_quality` artifact. Gate failure returns a remediation list;
the Developer re-opens the task. The operator can override; the
override is recorded as an `audit_event` and increments a "launches
needing override" counter visible on the Portfolio page. Phase B wires
the Designer role end-to-end; Phase A ships the gate machinery and
override path.

## Open questions

- Kill-workflow cascade timing: Stripe revoke synchronous or
  eventual-consistency within `kill_pipeline`? Defer to Architect.
- `[ask Founder]` drive session: if WIP 0073's session model does not
  support recurring-job roles, the button is grayed out with a
  "requires dispatcher role" tooltip.
- Founder dogfood cadence: twelve weekly cycles = 12 weeks. On-demand
  run endpoint compresses calibration (AC7).

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`
- Designs needed: `studio-project-kind`, `studio-admin-mode`,
  `founder-worker`
- Related: [studio](./studio.md), [admin-panel](./admin-panel.md),
  [worker-roles](./worker-roles.md),
  [task-orchestration](./task-orchestration.md),
  [self-healing](./self-healing.md)

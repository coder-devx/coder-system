---
id: studio-b2c-portfolio
title: Studio — B2C product portfolio operator contract
type: spec
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-19
last_verified_at: 2026-05-19
summary: "B2C product portfolio: project kind, Studio sidebar, Founder job, kill workflow, scaffold, and Stripe/PostHog wiring."
served_by_designs: []
related_specs: [admin-panel, worker-roles, task-orchestration, self-healing]
parent: knowledge-and-admin
---

# Studio — B2C product portfolio operator contract

## What it is

The operator-facing contract for Coder's B2C product portfolio — a set
of live products built and operated autonomously by the Coder fleet on
the public internet. The portfolio is Coder's demonstration surface and
marketing artifact simultaneously: every project the fleet has shipped
prior to the Studio sat behind a login, solving problems an operator
already knew about. The Studio adds a `b2c_product` project kind, a
Studio sidebar in the admin panel, a Founder recurring job, a kill
workflow, a template-driven scaffold path, and Stripe / PostHog wiring
per product. Quality, transparency, and build-in-public posture (defined
in `system/STUDIO_CHARTER.md`) are operator-visible constraints enforced
in the admin panel, not aspirations in a README.

## Capabilities

- **`b2c_product` project kind.** The project list and switcher render
  a type badge distinguishing `internal_tool` (existing, retroactively
  badged) from `b2c_product`. A `b2c_product` project-detail view
  replaces the standard pipeline tab with a Studio-flavoured view:
  Stripe connected-account state chip, monthly cost meter with $100 and
  $300 threshold lines, PostHog funnel snapshot
  (visitors → signups → activations → paying), and a kill-criteria
  tracker (five charter criteria with status and elapsed time when
  violated).
- **Studio sidebar.** When at least one `b2c_product` project exists,
  the sidebar gains a **Studio** section with three entries: **Idea
  Queue** (ranked Founder candidates with `[approve]` / `[reject]` /
  `[ask Founder]` actions — approve emits a PM draft task and writes
  `audit_event`; reject applies a decay factor, re-ranks, and writes
  `audit_event`); **Portfolio** (table of all Studio products with
  name, launch date, MRR, monthly spend, status: live / in-remediation /
  archived); **Per-product detail** (operator actions: `[flag for
  sunset]`, `[pause Founder reviews]`, `[view build artifacts]`).
- **Founder recurring job.** Runs as a scheduled Cloud Run Job — same
  machinery as `self-heal-tick`, not a dispatcher task. Two modes:
  **Weekly review** (default Monday 09:00 UTC; operator-triggered re-run
  available from the Studio sidebar header) reads all live products'
  PostHog aggregates, Stripe MRR, and cost data, emits a Markdown report
  card per product, and flags products meeting any kill criterion;
  appears in the operator's Now feed as a required-review item within
  15 minutes of completion. **Idea cycle** (runs after every weekly
  review) surveys approved idea sources, scores candidates against
  charter category constraints, and appends ranked ideas to the Idea
  Queue.
- **Kill workflow.** `[flag for sunset]` opens a confirmation dialog
  showing which kill criteria are met and since when, revenue-to-date
  (for refund scoping), and the downstream cascade (Stripe revoke,
  source-repo archive, DNS redirect to a "no longer maintained" notice,
  Resend notification to paying customers with refund details). On
  `[confirm sunset]` coder-core dispatches a `kill_pipeline` task with a
  live status stream per step. The product moves to "archived" in the
  Portfolio table with final metrics frozen; teardown artifacts are
  committed to the project knowledge repo.
- **Template-driven scaffold.** A `b2c_product` project is scaffolded
  from `coder-product-template` (Next.js + Stripe + PostHog + Resend +
  legal pages pre-wired — see [coder-product-template](./knowledge/coder-product-template.md)).
  The resulting Cloud Run service is reachable at a Cloudflare-managed
  domain within the same pipeline run that creates the project — no
  operator SSH, no manual DNS configuration.
- **Stripe Connect and PostHog wiring.** The Stripe state chip reflects
  the real OAuth connection state; the PostHog funnel snapshot
  populates from the project's PostHog project within 24 hours of the
  first event emitted by the deployed product. Full integration
  contract: see [studio-product-integrations](./knowledge/studio-product-integrations.md).
- **Designer gate (operator-overridable).** A product reaches launch
  only after the Designer emits a passing `design_quality` artifact.
  Gate failure returns a remediation list; the Developer re-opens the
  task. The operator can override; the override is recorded as an
  `audit_event` and increments a "launches needing override" counter
  visible on the Portfolio page.
- **Founder calibration dogfood.** Twelve Founder idea-cycle runs are
  executed against a dogfood context (the Coder project itself as test
  bed). The operator confirms calibration by marking the
  Founder-calibration checklist complete on the Studio admin page; the
  checklist is surfaced as a required Now item after the twelfth cycle.

## Interfaces

- **Admin SPA routes** (behind `VITE_STUDIO_ENABLED`): `/studio/ideas`,
  `/studio/portfolio`, `/projects/:projectId/studio`,
  `/projects/:projectId/studio/founder`.
- **Project type badge** rendered in the project list and project
  switcher; `b2c_product` project-detail view replaces the standard
  pipeline tab.
- **Founder on-demand run** — `POST /v1/projects/{id}/studio/founder/run?mode=idea_cycle`
  (design owns the exact shape).
- **Idea Queue actions** — `[approve]` (PM draft task + `audit_event`),
  `[reject]` (decay factor + `audit_event`), `[ask Founder]`
  (`/drive/{project}/founder`, gated by drive-mode availability).
- **Per-product actions** — `[flag for sunset]` (opens kill confirmation
  dialog), `[pause Founder reviews]`, `[view build artifacts]`.

## Dependencies

- [admin-panel](./knowledge/admin-panel.md) — renders the Studio sidebar
  and `b2c_product` project-detail view.
- [coder-product-template](./knowledge/coder-product-template.md) —
  template every Studio product is scaffolded from.
- [studio-product-integrations](./knowledge/studio-product-integrations.md)
  — Stripe Connect + PostHog backend wiring.
- [coder-studio-founder](./knowledge/coder-studio-founder.md) — the
  Founder recurring job that fills the Idea Queue and produces weekly
  reviews.
- [task-orchestration](./pipeline-operations.md) — `kill_pipeline` task
  dispatched on confirmed sunset.

## Evolution

- 2026-05-15 — Phase A ship (spec 0075): `b2c_product` project kind,
  Studio sidebar, Founder recurring job, kill workflow, scaffold
  contract, Stripe/PostHog wiring, Designer gate machinery, and
  Founder-calibration dogfood checklist.

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`
- Index: [studio](./knowledge/studio.md)
- Related: [admin-panel](./knowledge/admin-panel.md),
  [coder-studio-founder](./knowledge/coder-studio-founder.md),
  [coder-product-template](./knowledge/coder-product-template.md),
  [studio-product-integrations](./knowledge/studio-product-integrations.md),
  [worker-roles](./worker-roles.md)

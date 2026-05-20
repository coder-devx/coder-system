---
id: studio
title: Studio
type: index
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-20
last_verified_at: 2026-05-20
summary: Engineering view of the Studio — Coder's B2C product portfolio built and operated by the agent fleet.
implements_specs: [studio]
related_designs: [studio-b2c-portfolio, coder-studio-founder, coder-product-template, studio-product-integrations, admin-panel, worker-roles]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin, coder-system]
parent: knowledge-and-admin
---

# Studio

Engineering category for the Coder Studio — a B2C product portfolio
built and operated autonomously by the Coder agent fleet, used by real
external users. Designs in this category cover the per-product
operator contract, the Founder recurring job, the template scaffold
that every Studio product instantiates from, and the Stripe Connect +
PostHog integration backend.

## What this category covers

Engineering components that realise the Studio: the
`project_kind: b2c_product` polymorphic project surface in coder-core,
the Studio sidebar and `b2c_product` project-detail replacement in
coder-admin, the Founder Cloud Run Job and its Scheduler triggers,
the `coder-product-template` repo contract, the Stripe Connect Express
OAuth + webhook + MRR pipeline, the PostHog credential store and
6-hour funnel poll, the Designer launch-gate machinery, and the
`kill_pipeline` cascade task. Charter-level invariants (quality bar,
transparency, build-in-public posture, kill criteria — defined in
`system/STUDIO_CHARTER.md`) are operator-visible constraints enforced
in the admin panel.

## Components

- [studio-b2c-portfolio](../studio-b2c-portfolio.md) — `project_kind`,
  Studio sidebar, Founder recurring job, kill workflow, scaffolding,
  Designer launch-gate, and the operator-facing Studio mode in
  coder-admin.
- [coder-studio-founder](./coder-studio-founder.md) — Phase A
  Founder Cloud Run Job: idea cycles, weekly portfolio reviews,
  pause/resume, calibration dogfood.
- [coder-product-template](./coder-product-template.md) — repo
  contract every Studio product is instantiated from: pages,
  Lighthouse perf budget, integration wiring, `theme.config.ts`
  visual identity, Cloudflare DNS provisioning.
- [studio-product-integrations](./studio-product-integrations.md) —
  coder-core's Stripe Connect Express OAuth flow, webhook MRR
  pipeline, PostHog credential store, 6-hour funnel poll, and
  disconnect paths.

## Cross-cutting concerns

- **`project_kind` is the dispatch axis.** Workers are routed by
  `project_kind = internal_tool | b2c_product` via a roles-registry
  `worker_eligibility` lookup (no code branch). The dispatcher reads
  the column on every task lease. Per ADR
  [0033](../../../adrs/0033-polymorphic-project-kind-over-a-separate-product-entity.md).
- **One Stripe Connect account per project.** ADR
  [0009](../../../adrs/0009-per-managed-project-cloud-account-and-github-org.md)
  enforces per-project credential isolation; Studio inherits the
  pattern with one Stripe Connect Express account per
  `b2c_product`, secrets at
  `coder/{project_id}/stripe/connected_account` and
  `coder/{project_id}/posthog/credentials`. Webhook-secret rotation
  joins the
  [automated-secret-rotation](../tenancy/automated-secret-rotation.md)
  registry at 90 d cadence.
- **Studio mode lives inside coder-admin.** ADR
  [0034](../../../adrs/0034-studio-mode-in-coder-admin-over-a-separate-studio-spa.md)
  rules out a separate SPA; Studio chips, the sidebar, and the
  `b2c_product` project-detail replacement all live in
  [admin-panel](./admin-panel.md). Operator workflow is the same
  surface they already use for `internal_tool` projects.
- **Founder runs as a recurring job, not a dispatcher task.** ADR
  [0035](../../../adrs/0035-founder-as-a-recurring-job-over-a-normal-dispatcher-task.md)
  routes the Founder through Cloud Run Job + Scheduler ticks
  (mirrors `coder-core-self-heal-tick`), not the task queue.
- **Audit invariants are enforced, not aspirational.** Every Studio
  side effect (idea approve/reject, founder pause/resume,
  kill_pipeline, Stripe/PostHog connect & disconnect) emits an
  `audit_event` correlated to the originating cycle or operator
  action. See [audit-log](../tenancy/audit-log.md).
- **Charter compliance is operator-visible.** Kill-criteria status,
  loss-making chevrons, and "launches needing override" counters
  surface charter pressure in the admin UI; the operator overrides
  the Designer gate explicitly and the override increments a
  visible counter.

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`
- Specs index: [studio](../../../product-specs/active/knowledge/studio.md)
- Operator surface: [admin-panel](./admin-panel.md)
- Worker context: [worker-roles](../worker-roles.md)
- ADRs: [0009](../../../adrs/0009-per-managed-project-cloud-account-and-github-org.md),
  [0032](../../../adrs/0032-extend-coder-core-rather-than-spin-up-a-sibling-service.md),
  [0033](../../../adrs/0033-polymorphic-project-kind-over-a-separate-product-entity.md),
  [0034](../../../adrs/0034-studio-mode-in-coder-admin-over-a-separate-studio-spa.md),
  [0035](../../../adrs/0035-founder-as-a-recurring-job-over-a-normal-dispatcher-task.md)

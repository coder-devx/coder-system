---
id: studio
title: Studio
type: index
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-19
last_verified_at: 2026-05-19
summary: "B2C product portfolio built and operated autonomously by the Coder fleet."
served_by_designs: []
related_specs: [admin-panel, worker-roles, task-orchestration, self-healing]
parent: knowledge-and-admin
---

# Studio

The Studio is Coder's public-facing B2C product portfolio — a set of
live products built and operated autonomously by the Coder fleet, used
by real external users. The portfolio is Coder's demonstration surface
and marketing artifact simultaneously.

## What this category covers

Specs that define the Studio contract: how `b2c_product` projects are
created, scaffolded, operated, monitored, and killed; how the Founder
agent surfaces ranked product ideas to the operator; how quality gates
and transparency invariants are enforced.

## Components

- [studio-b2c-portfolio](./studio-b2c-portfolio.md) — B2C product
  portfolio operator contract: `project_kind: b2c_product`, Studio
  sidebar, Founder recurring job, kill workflow, scaffolding, and
  Stripe/PostHog wiring. Phase A: Foundations and Founder.

## Cross-cutting concerns

- **Charter invariants.** The Studio operates under invariants defined
  in `system/STUDIO_CHARTER.md`: quality bar, transparency,
  build-in-public posture, and kill criteria. These span every Studio
  component and are enforced via the admin panel's Studio sidebar and
  the Founder's weekly review — not aspirational notes in a README.
- **Operator surface.** Every Studio component renders into the admin
  panel's Studio sidebar (Idea Queue, Portfolio, per-product detail)
  and the `b2c_product` project-detail view. Workers do not have a
  separate Studio UI.
- **Audit.** Every Studio mutation (idea approve / reject, founder
  pause / resume, kill workflow, Stripe / PostHog connect) emits an
  `audit_event` correlated to the originating cycle or operator action.

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`
- Admin surface: [admin-panel](./admin-panel.md)
- Worker context: [worker-roles](./worker-roles.md)

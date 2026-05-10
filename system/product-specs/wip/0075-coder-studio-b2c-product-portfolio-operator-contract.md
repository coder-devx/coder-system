---
id: '0075'
title: Coder Studio — B2C product portfolio operator contract
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
- admin-panel
- worker-roles
- task-orchestration
- self-healing
parent: knowledge-and-admin
---

# Coder Studio — B2C product portfolio operator contract

**Phase:** A — Foundations and Founder
**Progress:** 0 / 7 acceptance criteria

## Problem

Coder today builds and operates internal tooling only. Every project the fleet has shipped sits behind a login, in a private GitHub org, solving a problem its operator already knew about. Operators who want to demonstrate Coder's capability to a skeptical external audience have no live evidence to point at.

The Studio closes this gap: a portfolio of B2C products built and operated autonomously by the Coder fleet, live on the public internet, used by real strangers. The portfolio is the demonstration and the marketing artifact simultaneously. Because the demonstration goal is fragile — one under-quality product undercuts the rest — the quality bar, transparency, and build-in-public posture described in `system/STUDIO_CHARTER.md` are operator-visible constraints enforced in the admin panel, not aspirational notes in a README.

## Users / personas

- **Portfolio operator.** Spends roughly one day per week reviewing the Founder's idea pipeline, approving the next bet, reviewing live-product metrics, and making kill or invest decisions. The admin panel is their entire Studio interface.
- **Product end-user** (beneficiary, out of spec scope). External strangers who use the Studio's products. Their presence or absence is the ground truth behind the kill criteria.

## Goals

When Phase A ships:

- `project_kind = b2c_product` is a first-class type in the project list and switcher, visually distinct from existing internal-tool projects.
- A Studio sidebar section appears in the admin panel with an Idea Queue and Portfolio table.
- The Founder recurring job runs weekly, surfaces ranked ideas for operator approval, and emits a per-product review report visible in the operator's Now feed.
- Stripe Connect and PostHog are wired per-product; connection state and funnel data appear on each product-detail view.
- The `coder-product-template` scaffold deploys a Cloud Run service to a Cloudflare-managed domain inside a single pipeline run, no operator SSH or manual provisioning required.

One-year north star (charter success criteria, cited here not as ACs): three to five live products with verifiable external usage, at least one with paying customers, none that embarrassed Coder.

## Non-goals

- Native mobile — App Store cycle incompatible with the autonomous deploy loop; charter-excluded in v1.
- Specific product categories — the Founder agent selects candidates; this spec defines the system contract, not the content.
- The design-level choice of polymorphic `project_kind` vs. a separate product entity — Architect owns that ADR.
- Paid acquisition strategy — off by default per charter; any campaign over $500 is an explicit out-of-band operator decision, not a panel workflow.
- Social platform presence — charter excludes any surface requiring an agent to operate as a person.
- Phase B–D roles (Designer, Marketer, Analyst, Researcher) — permission table included here for Architect completeness; built in later phases.

## Scope

### project_kind: b2c_product

The project list and project switcher each gain a type badge: `internal_tool` (existing, retroactively badged) and `b2c_product` (Studio). A `b2c_product` project-detail view replaces the standard pipeline tab content with a Studio-flavored view: a Stripe connected-account state chip (disconnected / pending / live), a monthly cost meter with $100 and $300 threshold lines, a PostHog funnel snapshot (visitors → signups → activations → paying), and a kill-criteria tracker showing each of the five charter criteria with status (OK / at-risk / violated) and, when violated, elapsed time.

### Studio sidebar

When at least one `b2c_product` project exists the sidebar gains a **Studio** section with three entries:

- **Idea queue** — ranked candidates from the Founder awaiting operator action. Each row: title, one-line pitch, category, estimated monthly cost, Founder confidence score (0–100). Actions: `[approve]` (emits a PM draft task for the idea, removes from queue, writes `audit_event`); `[reject]` (applies a decay factor, re-ranks, writes `audit_event`); `[ask Founder]` (opens `/drive/{project}/founder`; requires WIP 0073 drive mode).
- **Portfolio** — table of all Studio products: name, launch date, current MRR (or $0), monthly spend, status (live / in-remediation / archived). Row click navigates to the product-detail view.
- **Per-product detail** — the product-detail view described above. Operator actions: `[flag for sunset]`, `[pause Founder reviews]`, `[view build artifacts]`.

### New worker roles — permission table

Five new roles follow the uniform folder shape from ADR 0027. Operator-visible permissions:

| Role | Reads | Writes | Can dispatch | Cannot |
|---|---|---|---|---|
| **Founder** | all project knowledge, idea corpus, PostHog aggregates, Stripe MRR | idea queue entries, weekly review report, `create-product` tasks | PM draft tasks | write code or design artifacts |
| **Designer** | product brief, brand assets, Replicate outputs | visual asset artifacts (GCS), `design_quality` gate verdicts | — | merge PRs, write backend code, override own gate |
| **Marketer** | product copy, PostHog funnel, opted-in email lists | SEO content, Resend sends | — | run paid campaigns without operator approval |
| **Analyst** | PostHog event stream, experiment log | funnel interpretation report, experiment proposals for Founder | — | modify PostHog config, access cross-product raw data |
| **Researcher** | qualitative inputs (surveys, support threads) | synthesis report for Founder | — | contact users outside an opted-in channel, access user PII |

Designer launch-gate authority: a product reaches launch only after the Designer emits a passing `design_quality` artifact. Gate failure returns a specific remediation list; the Developer re-opens the task. The operator can override; the override is recorded as an `audit_event` and increments a "launches needing override" counter visible on the Portfolio page.

### Founder recurring job

The Founder runs as a scheduled recurring job — same machinery as `self-heal-tick` — not as a dispatcher task. Two modes:

- **Weekly review** (default schedule: Monday 09:00 UTC; operator-triggered re-run available from the Studio sidebar header). Reads all live products' PostHog aggregates, Stripe MRR, and cost data; emits a Markdown report card per product; flags products meeting any kill criterion. Report appears in the operator's Now feed as a required-review item within 15 minutes of job completion.
- **Idea cycle** (runs after every weekly review). Surveys approved idea sources, scores candidates against the charter's category constraints, and appends ranked ideas to the Idea Queue.

### Kill workflow

The operator flags a product via `[flag for sunset]` on the product-detail card. A confirmation dialog shows: which kill criteria are met and since when, revenue-to-date (to scope refunds), and the downstream cascade that will execute — Stripe revoke, source-repo archive, DNS redirect to a "no longer maintained" notice, Resend notification to paying customers with refund details. On `[confirm sunset]` coder-core dispatches a `kill_pipeline` task; the operator sees a live status stream per step. The product moves to "archived" in the Portfolio table with final metrics frozen. Teardown artifacts are committed to the same project knowledge repo as the launch artifacts — the kill is documented as carefully as the launch.

## Acceptance criteria

- **AC1.** The admin panel renders a `b2c_product` type badge on all Studio projects in the project list and project switcher. A `b2c_product` project-detail view shows: Stripe connected-account state chip, monthly cost meter with $100 and $300 threshold lines, PostHog funnel snapshot (visitors → signups → activations → paying), and a kill-criteria tracker showing each criterion, its current status, and elapsed time when violated.
- **AC2.** The Studio sidebar section appears when at least one `b2c_product` project exists. It contains Idea Queue, Portfolio table, and per-product detail with the actions described in Scope. The Idea Queue is empty until the Founder's first run; the Portfolio table renders a row for each `b2c_product` project immediately on project creation.
- **AC3.** The Founder recurring job runs on a configurable schedule (default: Monday 09:00 UTC). Its weekly-review output appears in the operator's Now feed as a required-review item within 15 minutes of job completion. The idea cycle appends at least one ranked candidate to the Idea Queue on each run.
- **AC4.** `[approve]` on an Idea Queue row triggers a PM draft task for the idea and removes the row from the queue. `[reject]` applies a decay factor and re-ranks. Both actions write `audit_event` rows recoverable from the audit log page with the idea's queue entry id as correlation.
- **AC5.** A `b2c_product` project is scaffolded from `coder-product-template` (Next.js + Stripe + PostHog + Resend + legal pages pre-wired). The resulting Cloud Run service is reachable at a Cloudflare-managed domain within the same pipeline run that creates the project — no operator SSH, no manual DNS configuration.
- **AC6.** Stripe Connect and PostHog are wired: the Stripe state chip reflects the real OAuth connection state; the PostHog funnel snapshot on the product-detail view populates from the project's PostHog project within 24 hours of the first event emitted by the deployed product.
- **AC7.** After at least twelve Founder idea-cycle runs against a dogfood context (the Coder project itself as test bed), the operator can confirm that the Founder's top-ranked candidate matched the operator's own top pick in at least 7 of 12 cycles. This criterion is met when the operator marks the Founder-calibration checklist complete on the Studio admin page; the checklist is surfaced as a required Now item after the twelfth cycle.

## Open questions

- A `studio` category-rollup index spec (`system/product-specs/active/studio.md`, type: index) should be created to parent this and future Studio WIP specs. Until that exists this spec carries `parent: knowledge-and-admin` as the nearest approximation; the audit pipeline will flag the parent as imprecise on first audit.
- Kill-workflow cascade timing: Stripe revoke synchronous within the `kill_pipeline` task, or eventual-consistency (revoke queued, polled)? Defer to Architect design.
- `[ask Founder]` drive session: WIP 0073 (drive mode) is now shipping (PR #200/#48 merged 2026-05-10). Whether 0073's session model supports recurring-job roles (Founder is not a dispatcher task role) is an open design question; if it does not, the button is present but grayed out with a "requires dispatcher role" tooltip.
- Founder dogfood cadence: twelve cycles at weekly cadence takes 12 weeks. The operator may want on-demand runs to compress calibration. Design should expose `POST /v1/projects/{id}/studio/founder/run?mode=idea_cycle` for this.

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`
- Related specs: admin-panel, worker-roles, task-orchestration, self-healing
- Designs needed: studio-project-kind, studio-admin-mode, founder-worker

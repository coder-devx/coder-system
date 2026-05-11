# Studio Roadmap (draft)

> The execution plan for extending Coder into the B2C Studio. Companion
> to [`STUDIO_CHARTER.md`](./STUDIO_CHARTER.md): the charter says what
> the Studio is and what it won't do; this document says how the Coder
> system gets built out to operate it.
>
> **Status:** v0 draft, 2026-05-10. Iterate before formalizing. The
> per-phase scope is a starting hypothesis — phases B–D will be
> revised based on what Phase A reveals.

## Phase A live status (2026-05-11)

Six WIPs filed 2026-05-10 cover the Phase A surface. Per-WIP detail
and the per-ord ship/blocked breakdown live in
[`product-specs/PHASES.md`](./product-specs/PHASES.md#phase-a----studio-foundations-and-founder-in-active-build-since-2026-05-10).

| Spec | Title | State |
|---|---|---|
| 0075 | Studio operator contract — `project_kind`, sidebar, idea queue, kill workflow | ord 1 + 2 + 3 + 7 shipped; ord 4 needs decomposition; ord 5 + 6 blocked behind 4 |
| 0076 | Spec-bound architect dispatch from admin UI | shipped |
| 0077 | Founder role Phase A | ord 0 + 2 + 4 + 5 + 6 shipped (#210/#213/#222+#224/coder-admin#52/coder-admin#54); only ord 3 outstanding — awaiting design call on PR #216 conflict on `_founder_reviews` |
| 0078 | spec_run lifecycle auto-bootstrap | shipped |
| 0079 | `coder-product-template` repo contract | every executable slice operator-blocked on GitHub template-repo creation |
| 0080 | Stripe Connect + PostHog wired into coder-core | ord 0 + 3 + 4 + 5 shipped; ord 2 (Stripe OAuth) needs decomposition; ord 6 blocked behind ord 2 |

**Operator-only items blocking Phase A close-out:**

1. Create `coder-devx/coder-product-template` GitHub template repo + scope `coder-coder-github-pat` to it (unblocks 0079 ord 2–6).
2. Decompose three tasks that exceed the 40-min worker deadline: 0075 ord 4 (kill_pipeline + SSE + sunset), 0079 ord 7 (Cloudflare/DNS bootstrap), 0080 ord 2 (Stripe Connect Express OAuth).
3. Resolve the `_founder_reviews` design conflict on PR [coder-core#216](https://github.com/coder-devx/coder-core/pull/216) — `founder_job_runs.report_uri` (merged #214) vs `founder_cycles.report_body` + acknowledge endpoint.

Once those land, the Founder calibration dogfood (idea-pipeline cycles inside Coder) is the Phase A close-out gate per the charter rule that "phase N+1 doesn't start until one product is fully running on phase N."

## What we're building

The Studio is not a separate system. It's a polymorphic extension of
`coder-core`: a new `project_kind` ("b2c_product") alongside the
existing internal-tool projects, with its own role workers, its own
integration set, and its own slice of the admin panel — all riding on
the existing multi-tenant orchestrator, dispatcher, audit log,
escalations, secret rotation, and deploy pipeline. The substrate
carries over almost completely. What changes is the *kind* of agent
labor the fleet performs.

Five new role workers are added under `coder-core/src/coder_core/workers/`:
**Founder** (idea sourcing, scoring, kill decisions), **Designer**
(visual + brand + UX with launch-gate authority on quality),
**Marketer** (SEO content, transactional email, paid-ads-when-allowed),
**Analyst** (PostHog consumption, funnel interpretation, experiment
proposals back to Founder), **Researcher** (qualitative input from
real users back into the Founder's decision loop). Five new
integrations are added under `coder-core/src/coder_core/integrations/`:
Stripe Connect (one connected account per product, for clean
per-product accounting and easy sunsetting), PostHog (chosen over
Plausible because the agents need event-level data for funnel
analysis, not just pageviews), Resend (transactional email),
Replicate (image and video generation), and Cloudflare DNS (so the
Founder can register a domain and point it at the new product's
Cloud Run service without operator involvement). Two new domain areas
are added: `product_lifecycle/` (idea_queue, kill_policy,
capital_allocation, metering) and `studio/` (cross-product P&L
aggregation, portfolio dashboard). The admin panel gets a "studio"
mode — same SPA, same auth, new sidebar and dashboard. Two new
template repos are added to the workspace: `coder-product-template`
(Next.js + Tailwind + Stripe + PostHog + Resend + legal pages
pre-wired, the scaffold every new product instantiates from) and
`coder-studio-template` (the knowledge-repo blueprint for B2C
product projects, parallel to the existing `coder-system/template/`).

## Why this shape

A few of the architectural calls deserve their reasoning written down,
because the easy alternatives are wrong in non-obvious ways.

**Extending coder-core rather than spinning up a sibling service.**
coder-core is already a multi-tenant agent orchestrator with
project_id everywhere. A B2C product is just another kind of project.
A separate "coder-studio" service would duplicate the dispatcher, the
audit log, the escalations, and the deploy pipeline for no real
isolation gain. The cost is a slightly bigger coder-core; the benefit
is one place to operate, one place to monitor, one place to evolve.
If the product-lifecycle domain grows heavy enough to warrant
isolation later, splitting it out is a refactor — not a
green-field rewrite. Defer it until the evidence demands it.

**Polymorphic `project_kind` rather than a separate "product" entity.**
Treating B2C products as a fundamentally different aggregate would
fork the dispatcher, the API, the admin panel, and the knowledge
model. Treating them as a project subtype reuses every primitive.
The dispatcher's per-kind routing is a small addition; the bigger
change is that some role workers run only for one kind (Founder and
Designer don't make sense for an internal tool; PM and Architect work
for both with different prompts). Per-kind worker eligibility is a
table, not a code branch.

**Same admin SPA with a "studio" mode rather than a separate Studio
app.** The shell, auth, project switcher, command palette, and audit
viewer all carry over. Splitting the SPA buys nothing and costs a
second build, deploy, and login surface. The studio mode swaps the
sidebar and dashboard, lazy-loads its own bundle, and reuses the
project-detail page for product-detail views. If the studio IA
eventually justifies a separate frontend, the split is mechanical.

**Founder as a recurring meta-orchestrator rather than a normal
dispatcher task.** The Founder's job — survey idea sources, score
candidates, pick the next bet, and emit a "create-product" task that
kicks off the existing pipeline at the PM stage — doesn't fit the
per-task worker shape. It runs on a schedule, like
`auto-approve-tick` or `self-heal-tick`, and emits new tasks rather
than consuming them. The existing recurring-job machinery handles
this with one new job type. The Founder also runs in a second mode
during weekly review: produce a written report on portfolio state and
flag products approaching kill thresholds.

**Designer with launch-gate authority on quality.** Every other worker
produces output that the next role consumes; Designer's output is
sometimes a *veto*. Without that, the demonstration goal fails on
the first launch. The implementation is a new artifact type
(`asset_artifact`) that lands in GCS and is reviewable in the admin
panel, plus a new pipeline gate (`design_quality`) that the Designer
either passes or returns with specific remediation. The operator can
override the gate, but the override is logged and counts against the
"launches that needed operator override" metric.

## Phased plan

The plan unfolds across four phases, sized roughly two months each
with the explicit rule that **phase N+1 doesn't start until one
product is fully running on phase N**. The temptation is to build all
roles in parallel; that produces a wide system that doesn't actually
ship anything. Each phase ends on a concrete proof.

### Phase A — Foundations and Founder (6–8 weeks)

The goal is the runway, not a product. By the end of Phase A:
`project_kind` exists with dispatcher routing on it, the Founder
role is designed end-to-end and dogfooded inside Coder for a dozen
idea-pipeline cycles with the operator in the loop until its
judgment matches expectations, the `coder-product-template` repo is
built and Cloud Run-deployable, Stripe Connect is integrated in
coder-core, PostHog is integrated, and the studio mode exists in the
admin panel as a basic portfolio table and idea queue UI. No B2C
product is launched yet — Phase A ends when the Founder agent's idea
selection has earned the operator's trust.

The deepest work in Phase A is calibrating the Founder. The other
pieces are mechanical extension. The Founder is the role that most
defines whether the Studio works, and the cheapest place to discover
its weaknesses is before any real product is staked on its judgment.

### Phase B — First product end-to-end (6–8 weeks)

The goal is one product live, built and launched without operator
glue. Phase B adds the Designer role with the asset-artifact output
type and the design_quality gate, integrates Replicate for image and
video generation, integrates Resend for transactional email,
integrates Cloudflare DNS so the Founder can register a domain
autonomously, and ships one real B2C product picked by the Founder,
designed by Designer, built by the existing fleet (PM, Architect, TM,
Developer, Reviewer), deployed, indexed by search engines, and live
with Stripe Checkout. The product category is deliberately simple —
a programmatic tool or niche AI wrapper — to keep distribution
honest and isolate the variable to the agent loop.

Phase B's success criterion is not "the product makes money" — it's
"the entire loop ran without operator glue." Revenue is a Phase C
concern.

### Phase C — Portfolio dynamics (6–8 weeks)

The goal is multiple products operating simultaneously with
cross-product policy. Phase C adds the Marketer role (SEO content,
email campaigns, paid-ads-when-allowed), the Analyst role (PostHog
consumption, funnel interpretation, experiment proposals back to
Founder), the kill-policy implementation with auto-flagging and the
sunset workflow (revoke Stripe, archive repos, redirect domain,
notify customers), the capital-allocation policy (per-product
monthly budget with automatic shifts when one product clearly
outperforms), and the cross-product P&L rollup. By the end of Phase
C, three products are live simultaneously and the portfolio is
self-managing within the operator-approved policy envelope.

This is where the Studio stops being "build one product" and becomes
"manage a portfolio." The kill workflow is as important as the
launch workflow.

### Phase D — Trust escalation and scale (8–12 weeks)

The goal is the operator's role contracting from co-operator to
policy-setter. Phase D adds the Researcher role for qualitative
input back into Founder, generalizes the existing confidence-based
auto-approval machinery (Phase 7 in the current Coder roadmap) from
"is this PR safe" to "is this strategic move within policy," and
runs the system to a steady state of five to ten live products with
the operator spending roughly four hours a week on portfolio review.
Mobile is explicitly out of scope for v1; revisit only if the
portfolio's natural product shape demands it.

Phase D ends when the operator can take a two-week vacation without
the Studio degrading.

## Role build order

The roles are added in dependency order, not in parallel. **Founder
first** because without it the system has no judgment about what to
build. **Designer second** because the first product launched
without it will look like an internal admin panel and the
demonstration fails on day one. **Analyst third** because you cannot
iterate on consumer products without funnel data and qualitative
read. **Marketer fourth** because distribution matters but only
after there's something to distribute. **Researcher fifth** because
qualitative research is the highest-leverage input back into the
Founder loop, but only once there are real products generating
real users to research.

Each new role is dogfooded inside Coder itself for several cycles
before it's pointed at customer-product work — the same playbook
already used for the existing roles. The Founder evaluates ideas
for Coder's own roadmap; the Designer designs the studio mode UI;
the Analyst interprets the metrics on Coder's own dispatcher
performance. This both calibrates the role and produces real value
for Coder before the Studio depends on it.

## Integration rationale

Stripe Connect with a separate connected account per product is
chosen over a single platform Stripe account because per-product
revenue accounting is necessary for honest kill decisions and any
eventual sale of a product as an asset. The integration cost is a
couple of weeks; the alternative entangles all products' revenue
forever.

PostHog is chosen over Plausible because the Analyst role needs
event-level funnel data, not aggregate pageviews. Self-hosting
PostHog is in scope if cloud costs become non-trivial within the
$10k/year budget envelope.

Resend is chosen for transactional email because of clean API, good
deliverability, and small surface area. Marketing email (broadcast
campaigns) is a Phase C concern owned by the Marketer role and may
warrant a different provider.

Replicate is chosen for image and video generation as the broadest,
fastest-evolving model surface; the Designer role wraps it and
maintains a small library of prompt patterns and brand-consistency
checks. The integration is intentionally model-agnostic so the
underlying provider can change.

Cloudflare DNS is chosen because the API is clean and the operator
already has an account; the Founder agent needs domain-registration
authority to launch a product autonomously.

## The hard gaps

Two gaps cannot be closed by adding a role or an integration, and
they will shape the Studio's evolution.

**Distribution.** Most platforms that drive consumer traffic
explicitly ban bot accounts. The Studio's legitimate distribution
surfaces are SEO via product-led content and programmatic landing
pages, transactional email to opted-in lists, embedded sharing and
referral mechanics inside each product, and operator-fronted launches
on HN / Product Hunt / niche forums. Categories whose distribution
depends on social-platform participation are out of scope by the
charter; the roadmap doesn't try to solve a problem it shouldn't
solve.

**Taste.** Claude is competent but median. Consumer products win on
specific, opinionated, somewhat weird aesthetics. The Designer role's
calibration is more about constraining the model with strong
references than about teaching it taste. The first three products'
visual quality is the diagnostic — if they all converge to
shadcn-default, the Designer prompt and reference library need
significant work before Phase D.

## Kill switches at the system level

The roadmap itself can fail in instructive ways, and a few signals
should trigger a stop-and-rethink rather than continuing to build.

If after Phase A the Founder agent's idea-selection judgment is
materially worse than the operator's, Phase B does not start until
that's fixed — adding the rest of the system on top of a bad
Founder produces a fast machine pointed in random directions, which
is worse than no machine at all.

If after Phase B the first product launches but is recognizably
"AI-generated" to first-time visitors (visual blandness, generic
copy, obvious shortcuts), the Designer role and the product template
need rework before Phase C.

If after Phase C the portfolio has three products live but none
have crossed the $0 → $1 boundary on revenue, that's evidence the
charter's category constraints are wrong, not that the system is
broken — revisit the charter, don't build more system.

## Amendment

Like the charter, this roadmap is a living document but not a
casual one. Phase scopes will be revised based on evidence from
the prior phase. The role build order can be reordered if a phase
reveals an unexpected dependency. The integration set will grow as
products demand it. Material changes happen in writing, on a
feature branch, with the operator's signature in the commit.

---
id: 0079
title: Coder Studio — coder-product-template repo contract
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
- '0077'
parent: knowledge-and-admin
---

# Coder Studio — coder-product-template repo contract

**Phase:** A — Foundations and Founder
**Progress:** 0 / 7 acceptance criteria

## Problem

Spec 0075 (AC5) commits to a `coder-product-template` scaffold that every new B2C product instantiates from, and spec 0077 (AC3) emits `create-product` PM draft tasks with a `repo = studio-{slugified-title}` placeholder — but the template repo does not yet exist. Without a defined contract for what the template delivers, a Founder approval has nowhere to scaffold from: the orchestrator can name a repo but cannot populate or deploy it. This spec defines the operator-observable contract for `coder-product-template` — what every instantiated product gets out of the box, at what quality level, and how each integration is wired — so the Developer and Reviewer building the repo have an acceptance surface and Phase A can close.

## Users / personas

- **Portfolio operator.** Approves ideas in the Studio panel; expects a deployed, reachable product at the end of `create-product` with no SSH, no manual DNS, no environment-variable hunting.
- **Developer worker.** Instantiates the template when building a new product; expects `theme.config.ts`, env-var conventions, and page routes to be stable and documented across template versions.

## Goals

- Every instantiated product ships a complete page set (landing, pricing, checkout, success, sunset, contact, legal) with no stub or placeholder content.
- Lighthouse mobile LCP < 2 s on a cold load, enforced by CI on every commit.
- Stripe Connect, PostHog, and Resend are wired via env vars; missing vars degrade gracefully with user-visible messages, not silent failures.
- Visual identity is isolated to `theme.config.ts`; a Designer write there changes rendered output on next deploy with no code change required.
- A `create-product` pipeline run scaffolds, builds, and deploys a new Cloud Run service end-to-end with no operator intervention.

## Non-goals

- The Designer worker that writes `theme.config.ts` — Phase B role spec.
- The kill_pipeline orchestration that uses `/sunset` — Phase C.
- The Founder `create-product` full orchestration — spec 0077.
- Specific product content (hero copy, value proposition) — per-product, not template-level.
- A11y compliance beyond WCAG AA basics.
- Internationalization — English-only for v1.
- Registration of `coder-product-template` in `system/repos/registry.yaml` — a separate engineering act once the repo is created.

## Scope

### Page contract

Every instantiated product ships these routes with no stubs:

| Route | Purpose |
|---|---|
| `/` | Landing page — hero, value prop, primary CTA |
| `/pricing` | Pricing tiers; links to `/checkout` |
| `/checkout` | Stripe-hosted checkout redirect |
| `/success` | Post-checkout confirmation |
| `/sunset` | "No longer maintained" notice; kill_pipeline DNS target |
| `/contact` | Resend-backed contact form |
| `/legal/privacy` | Privacy policy |
| `/legal/terms` | Terms of service |

All pages include a "built by Coder" footer per charter. `/legal/*` pages are statically rendered with zero client-side JS.

### Performance budget

Lighthouse mobile LCP < 2 s on a representative cold load (charter gate). Enforced via `lighthouse-ci` in CI on every commit; a regression fails the build and blocks merge. Images use Next.js `<Image />` with explicit dimensions; fonts are subsetted at build time. The PostHog SDK bundle is excluded from `/legal/*` pages.

### Stripe Connect wiring

Template reads `STRIPE_CONNECT_ACCOUNT_ID` at boot. With a valid value, `/checkout` initiates a Stripe-hosted session (`application_fee_amount=0`; platform fee policy is a Phase C concern). With the var unset or empty, `/checkout` returns HTTP 503 with a user-visible "Checkout is being configured" page — no silent redirect, no unhandled error. A `/api/internal/stripe-status` endpoint returns `{ "state": "live" | "pending" | "disconnected" }` by calling the Stripe API; the Studio panel's Stripe chip polls this endpoint.

### PostHog wiring

Template reads `POSTHOG_PROJECT_API_KEY` at boot. A thin PostHog SDK init lives in `app/layout.tsx`; it checks the browser's DNT header and a `POSTHOG_EU_COMPLIANCE=true` env flag before emitting events. Funnel event names are a documented convention shipped with the template: `signup` (signup form submit), `activate` (first action completed), `checkout_start` (arrives at `/checkout`), `checkout_complete` (Stripe webhook confirms payment).

### Resend wiring

Template reads `RESEND_API_KEY` at boot. The `/contact` form posts to `/api/contact`, which calls Resend with `from: noreply@{PRODUCT_DOMAIN}` (set at instantiation as a template substitution variable). Rate-limited at 5 requests per minute per IP via an in-process sliding-window counter; excess returns HTTP 429.

### Domain pointing

The `create-product` task runs a bootstrap step: registers a subdomain via Cloudflare API, creates a CNAME record pointing at the new Cloud Run service URL, and writes the DNS record id to the product knowledge repo at `system/dns.yaml` so kill_pipeline can revert it. Cloudflare manages the vanity domain; Cloud Run is the origin.

### Visual identity

`theme.config.ts` at the repo root exposes: `primaryColor`, `secondaryColor`, `accentColor` (hex strings); `fontPair: { heading: string; body: string }` (Google Fonts family names); `heroIllustrationSlot` (path to a static asset under `/public/`). All pages import from this config at build time. Changing the file and redeploying is the complete Designer workflow — no template fork required.

## Acceptance criteria

- **AC1.** Instantiating the template into a new product project via `create-product` produces a Cloud Run service that responds HTTP 200 on `/`, `/pricing`, `/legal/privacy`, and `/legal/terms` within the same pipeline run — no operator SSH, no manual provisioning.
- **AC2.** A Lighthouse CI run against the deployed `/` shows LCP < 2 s on a mobile cold-load profile. A performance regression in any later commit fails CI and blocks merge.
- **AC3.** With a valid `STRIPE_CONNECT_ACCOUNT_ID` env var, hitting `/checkout` opens a Stripe-hosted checkout. With the var unset, `/checkout` returns HTTP 503 with a user-visible "Checkout is being configured" message.
- **AC4.** With a valid `POSTHOG_PROJECT_API_KEY`, submitting the signup form fires a `signup` PostHog event. The Studio panel's product-detail funnel snapshot populates from PostHog within 24 hours of the first event (per spec 0075 AC6).
- **AC5.** Submitting `/contact` with valid input sends a Resend email to the configured address and returns HTTP 200. More than 5 submissions per minute from the same IP return HTTP 429.
- **AC6.** `/sunset` returns HTTP 200 and is styled. The kill_pipeline DNS rewrite points here when a product is sunset; no other code change is required.
- **AC7.** The Designer worker writes `theme.config.ts` with updated color and font values; on next deploy the rendered pages reflect the new visual identity with no other code change.

## Open questions

- Template versioning: when `coder-product-template` is updated, how do already-instantiated products pick up changes — git subtree sync, Renovate-style automated PRs per product, or manual? Defer to Architect design.
- Stripe webhook verification: the template should verify `Stripe-Signature` headers on `/api/stripe/webhook`; key derivation from Secret Manager is the expected pattern but env var name convention needs Architect confirmation.
- `POSTHOG_EU_COMPLIANCE` behavior: self-hosted PostHog vs. EU cloud region — the flag's precise effect should be defined in the Architect design to avoid silent compliance gaps.
- A "studio" category-rollup index spec should give Studio specs (0075, 0077, 0079) a dedicated parent; until that exists this spec sits under `knowledge-and-admin` as an approximation.

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`
- Parent spec: [0075 — Coder Studio B2C product portfolio operator contract](../wip/0075-coder-studio-b2c-product-portfolio-operator-contract.md)
- Sibling spec: [0077 — Coder Studio Founder role Phase A](../wip/0077-coder-studio-founder-role-phase-a.md)

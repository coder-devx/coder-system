---
id: coder-product-template
title: Coder Studio — coder-product-template contract
type: spec
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-19
last_verified_at: 2026-05-19
summary: "Operator-observable contract for the coder-product-template scaffold: page set, perf budget, integration wiring, and visual identity."
served_by_designs: []
related_specs: [studio-b2c-portfolio, studio-product-integrations, admin-panel]
parent: knowledge-and-admin
---

# Coder Studio — coder-product-template contract

## What it is

Every Coder Studio B2C product is instantiated from
`coder-product-template`. This spec defines the operator-observable
contract for what every instantiated product gets out of the box — the
page set, performance budget, integration wiring, visual identity, and
domain provisioning path — so Developers building the template and
Reviewers checking it have a concrete acceptance surface, and so the
operator can trust that `create-product` produces a deployed, reachable
product with no SSH, no manual DNS, and no env-var hunting.

## Capabilities

- **Standard page set.** Every instantiated product ships these routes:
  `/` (landing — hero, value prop, primary CTA); `/pricing` (tiers
  linking to `/checkout`); `/checkout` (Stripe-hosted checkout
  redirect); `/success` (post-checkout confirmation); `/sunset` (the
  "no longer maintained" notice used as the `kill_pipeline` DNS
  target); `/contact` (Resend-backed contact form); `/legal/privacy`
  and `/legal/terms` (statically rendered, zero client-side JS). All
  pages include a "built by Coder" footer per charter.
- **Lighthouse performance budget.** Mobile cold-load LCP < 2s
  enforced by `lighthouse-ci` in CI on every commit. A regression
  fails the build and blocks merge. Next.js `<Image />` with explicit
  dimensions; fonts subsetted at build time; PostHog SDK excluded from
  `/legal/*` pages.
- **Stripe Connect wiring.** Reads `STRIPE_CONNECT_ACCOUNT_ID` at boot.
  Valid → `/checkout` initiates a Stripe-hosted session
  (`application_fee_amount=0`; platform fee policy is Phase C). Unset
  or empty → `/checkout` returns HTTP 503 with a user-visible
  "Checkout is being configured" page — no silent redirect. A
  `/api/internal/stripe-status` endpoint returns
  `{ "state": "live" | "pending" | "disconnected" }` by calling the
  Stripe API; the Studio panel's Stripe chip polls this endpoint.
- **PostHog wiring.** Reads `POSTHOG_PROJECT_API_KEY` at boot. SDK
  init in `app/layout.tsx` checks the browser's DNT header and a
  `POSTHOG_EU_COMPLIANCE=true` env flag before emitting events.
  Standard funnel event names shipped with the template: `signup`,
  `activate`, `checkout_start`, `checkout_complete`.
- **Resend wiring.** Reads `RESEND_API_KEY` at boot. `/contact` posts
  to `/api/contact` with `from: noreply@{PRODUCT_DOMAIN}` (set at
  instantiation as a template substitution variable). Rate-limited at
  5 requests/min/IP via an in-process sliding-window counter; excess
  returns HTTP 429.
- **Domain provisioning.** The `create-product` task registers a
  subdomain via the Cloudflare API, creates a CNAME record pointing at
  the new Cloud Run service URL, and writes the DNS record id to
  `system/dns.yaml` in the product knowledge repo so `kill_pipeline`
  can revert it.
- **Visual identity contract.** `theme.config.ts` at the repo root
  exposes `primaryColor`, `secondaryColor`, `accentColor` (hex
  strings); `fontPair: { heading: string; body: string }` (Google
  Fonts family names); and `heroIllustrationSlot` (path to a static
  asset under `/public/`). All pages import from this config at build
  time — changing the file and redeploying is the complete Designer
  workflow, no template fork required.

## Interfaces

- **Page routes** (every instantiated product): `/`, `/pricing`,
  `/checkout`, `/success`, `/sunset`, `/contact`, `/legal/privacy`,
  `/legal/terms`.
- **Internal endpoints:** `/api/internal/stripe-status` (status chip
  poll), `/api/contact` (Resend form submission, rate-limited).
- **Required env vars at boot:** `STRIPE_CONNECT_ACCOUNT_ID`,
  `POSTHOG_PROJECT_API_KEY`, `RESEND_API_KEY`, `PRODUCT_DOMAIN` (set
  via template substitution at instantiation), `POSTHOG_EU_COMPLIANCE`
  (optional).
- **Repo-root config files:** `theme.config.ts` (visual identity
  contract), `system/dns.yaml` (Cloudflare DNS record id for
  `kill_pipeline`).
- **CI surface:** `lighthouse-ci` step on every commit; LCP regression
  blocks merge.

## Dependencies

- [studio-b2c-portfolio](../studio-b2c-portfolio.md) — `create-product`
  scaffolds from this template; the Stripe / PostHog chips on the
  product-detail page poll the endpoints this template exposes.
- [studio-product-integrations](./studio-product-integrations.md) —
  the coder-core side of Stripe Connect OAuth, webhook ingest, and
  PostHog polling that this template's env-var contract pairs with.
- [admin-panel](./admin-panel.md) — Studio panel chips that read the
  status / funnel endpoints exposed here.
- External services: Stripe Connect, PostHog (cloud), Resend,
  Cloudflare, Google Cloud Run.

## Evolution

- 2026-05-15 — Phase A ship (spec 0079): page set + Lighthouse perf
  budget + Stripe/PostHog/Resend wiring + Cloudflare domain
  provisioning + `theme.config.ts` visual identity contract; first
  instantiated products use this contract end to end.

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`
- Related: [studio-b2c-portfolio](../studio-b2c-portfolio.md),
  [studio-product-integrations](./studio-product-integrations.md),
  [admin-panel](./admin-panel.md)

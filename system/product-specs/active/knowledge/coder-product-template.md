---
id: coder-product-template
title: Coder Studio — coder-product-template contract
type: spec
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-15
last_verified_at: 2026-05-15
summary: "Operator-observable contract for the coder-product-template scaffold: page set, perf budget, integration wiring, and visual identity."
served_by_designs: []
related_specs: []
parent: knowledge-and-admin
---

# Coder Studio — coder-product-template contract

Every Coder Studio B2C product is instantiated from `coder-product-template`. This spec defines what every instantiated product gets out of the box — the page set, performance budget, integration wiring, and visual identity contract — so Developers building the template and Reviewers checking it have a concrete acceptance surface.

## Users

- **Portfolio operator.** Expects a deployed, reachable product at the end of `create-product` with no SSH, no manual DNS, no env-var hunting.
- **Developer worker.** Expects `theme.config.ts`, env-var conventions, and page routes to be stable and documented across template versions.

## Page contract

| Route | Purpose |
|---|---|
| `/` | Landing — hero, value prop, primary CTA |
| `/pricing` | Pricing tiers; links to `/checkout` |
| `/checkout` | Stripe-hosted checkout redirect |
| `/success` | Post-checkout confirmation |
| `/sunset` | "No longer maintained" notice; kill_pipeline DNS target |
| `/contact` | Resend-backed contact form |
| `/legal/privacy` | Privacy policy |
| `/legal/terms` | Terms of service |

All pages include a "built by Coder" footer per charter. `/legal/*` pages are statically rendered with zero client-side JS.

## Performance budget

Lighthouse mobile LCP < 2 s enforced by `lighthouse-ci` in CI on every commit. A regression fails the build and blocks merge. Next.js `<Image />` with explicit dimensions; fonts subsetted at build time. PostHog SDK excluded from `/legal/*` pages.

## Integration wiring

### Stripe Connect

Reads `STRIPE_CONNECT_ACCOUNT_ID` at boot. Valid → `/checkout` initiates a Stripe-hosted session (`application_fee_amount=0`; platform fee policy is Phase C). Unset or empty → `/checkout` returns HTTP 503 with a user-visible "Checkout is being configured" page — no silent redirect. A `/api/internal/stripe-status` endpoint returns `{ "state": "live" | "pending" | "disconnected" }` by calling the Stripe API; the Studio panel's Stripe chip polls this endpoint.

### PostHog

Reads `POSTHOG_PROJECT_API_KEY` at boot. SDK init in `app/layout.tsx` checks the browser's DNT header and a `POSTHOG_EU_COMPLIANCE=true` env flag before emitting events. Standard funnel event names shipped with the template: `signup`, `activate`, `checkout_start`, `checkout_complete`.

### Resend

Reads `RESEND_API_KEY` at boot. `/contact` posts to `/api/contact` with `from: noreply@{PRODUCT_DOMAIN}` (set at instantiation as a template substitution variable). Rate-limited at 5 requests/min/IP via in-process sliding-window counter; excess returns HTTP 429.

## Domain provisioning

The `create-product` task registers a subdomain via Cloudflare API, creates a CNAME record pointing at the new Cloud Run service URL, and writes the DNS record id to `system/dns.yaml` in the product knowledge repo so kill_pipeline can revert it.

## Visual identity

`theme.config.ts` at the repo root exposes: `primaryColor`, `secondaryColor`, `accentColor` (hex strings); `fontPair: { heading: string; body: string }` (Google Fonts family names); `heroIllustrationSlot` (path to a static asset under `/public/`). All pages import from this config at build time. Changing the file and redeploying is the complete Designer workflow — no template fork required.

## Acceptance criteria

- **AC1.** Instantiating the template via `create-product` produces a Cloud Run service that responds HTTP 200 on `/`, `/pricing`, `/legal/privacy`, and `/legal/terms` within the same pipeline run — no operator SSH, no manual provisioning.
- **AC2.** A Lighthouse CI run against the deployed `/` shows LCP < 2 s on a mobile cold-load profile. A performance regression in any later commit fails CI and blocks merge.
- **AC3.** With a valid `STRIPE_CONNECT_ACCOUNT_ID`, hitting `/checkout` opens a Stripe-hosted checkout. With the var unset, `/checkout` returns HTTP 503 with a user-visible "Checkout is being configured" message.
- **AC4.** With a valid `POSTHOG_PROJECT_API_KEY`, submitting the signup form fires a `signup` PostHog event. The Studio panel's product-detail funnel snapshot populates from PostHog within 24 hours of the first event.
- **AC5.** Submitting `/contact` with valid input sends a Resend email to the configured address and returns HTTP 200. More than 5 submissions per minute from the same IP return HTTP 429.
- **AC6.** `/sunset` returns HTTP 200 and is styled. The kill_pipeline DNS rewrite points here when a product is sunset; no other code change is required.
- **AC7.** The Designer worker writes `theme.config.ts` with updated color and font values; on next deploy the rendered pages reflect the new visual identity with no other code change.

## Non-goals

- Designer worker that writes `theme.config.ts` — Phase B role spec.
- kill_pipeline orchestration using `/sunset` — Phase C.
- Founder `create-product` full orchestration — spec 0077 (WIP).
- Specific product content (hero copy, value proposition) — per-product, not template-level.
- A11y compliance beyond WCAG AA basics.
- Internationalization — English-only for v1.
- Registration of `coder-product-template` in `system/repos/registry.yaml` — a separate engineering act once the repo is created.

## Open questions (deferred to Architect design)

- Template versioning strategy for already-instantiated products (git subtree sync, Renovate-style automated PRs, or manual).
- Stripe webhook `Stripe-Signature` verification and key derivation from Secret Manager — env var name convention.
- `POSTHOG_EU_COMPLIANCE` precise effect (self-hosted vs. EU cloud region).

## Links

- Charter: `system/STUDIO_CHARTER.md`
- Roadmap: `system/STUDIO_ROADMAP.md`

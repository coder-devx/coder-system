---
id: 0080
title: Coder Studio — Stripe Connect and PostHog integration in coder-core
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
- 0079
parent: knowledge-and-admin
---

# Coder Studio — Stripe Connect and PostHog integration in coder-core

**Phase:** A — Foundations and Founder
**Progress:** 0 / 7 acceptance criteria

## Problem

Spec 0075 (AC1, AC6) commits the Studio panel to showing a Stripe connected-account chip, an MRR meter, and a PostHog funnel snapshot per `b2c_product` project. Spec 0079 defines what the product itself exposes (`/api/internal/stripe-status`, PostHog SDK init, funnel event names). Neither spec defines what coder-core must contribute: the Stripe Connect Express OAuth flow, the webhook endpoint that ingests subscription events, the MRR computation, the PostHog credential store, and the 6-hour funnel poll. Until this ships, every product-detail chip renders blank and every metric reads zero regardless of what the product template exports.

## Users / personas

- **Portfolio operator.** Monitors Stripe state and MRR/cost delta from the Studio panel to make live kill-or-invest decisions; expects chips to settle within 60 seconds of any configuration action.
- **Founder recurring job.** Reads per-product MRR when scoring kill criteria (charter: cost-exceeds-MRR is a kill signal); no operator involvement in the poll loop.

## Goals

- Stripe Connect Express OAuth flow per `b2c_product` project; connected-account credentials stored in Secret Manager under `{project_id}/stripe/connected_account`.
- `POST /v1/webhooks/stripe` on coder-core receives, verifies via `Stripe-Signature`, and persists subscription and payment events; MRR derives from active subscriptions and refreshes within 5 minutes of each event.
- Product-detail cost meter gains `MRR: $X · MTD cost: $Y` with a yellow chevron on loss-making products; existing budget reads in `budget.py` are unchanged (additive column only).
- PostHog `project_api_key` + `region` stored per-project, verified on save against the PostHog `/api/projects` endpoint, funnel polled every 6 hours, snapshot persisted.
- Disconnect paths for both integrations revert chips to unconfigured state and are reusable by Phase C `kill_pipeline`.

## Non-goals

- Resend / broadcast email — Phase C (Marketer role).
- PostHog cohort analysis or experiment tracking — Phase C (Analyst role).
- Stripe Connect Standard — charter commits to Express.
- Self-hosted PostHog — only if cloud bills exceed budget envelope (Phase C+).
- Cross-product MRR rollup — Phase C portfolio P&L surface.
- Refund initiation from the panel — `kill_pipeline` owns refunds during sunset.
- Tax handling (Stripe Tax wiring) — operator-decided per-product.

## Scope

All changes land in coder-core. The operator surface is the `b2c_product` project-detail page in the admin SPA. Both integrations ship together because they share the same operator surface (per-product chips on the same card) and the same OAuth-or-API-key + webhook-or-poll pattern.

## Acceptance criteria

- **AC1.** A `b2c_product` project with no connected Stripe account shows a `[Connect Stripe]` button on its project-detail page. Clicking opens Stripe Connect Express OAuth consent; after the operator authorizes, the chip transitions `disconnected → pending → live` within 60 seconds of webhook confirmation, and the chip text links to the connected account in the Stripe dashboard.
- **AC2.** `POST /v1/webhooks/stripe` with a valid `Stripe-Signature` and a recognized event type (`customer.subscription.created/updated/deleted`, `invoice.payment_succeeded`, `charge.refunded`) returns 200 and persists the event to a `stripe_events` table scoped by `connected_account_id`. A request with an invalid signature returns 401 and persists nothing.
- **AC3.** The product-detail card's cost meter shows `MRR: $X · MTD cost: $Y` for any project with at least one active subscription. MRR refreshes within 5 minutes of a `customer.subscription.*` event. A loss-making product (MRR < MTD cost) shows a yellow chevron; no other UI noise.
- **AC4.** A `b2c_product` project with no PostHog config shows `[Configure PostHog]`. The form accepts `project_api_key` and `region` (`us` | `eu`); on submit, coder-core hits PostHog's auth check and shows `verified` or `auth_failed` inline within 10 seconds. A verified config persists per-project in Secret Manager.
- **AC5.** For a PostHog-connected product, the funnel chip renders the most recent persisted snapshot (≤ 6 hours old) showing the four standard steps (`signup → activate → checkout_start → checkout_complete`). Clicking the chip opens a funnel detail card with per-step counts and a last-updated timestamp.
- **AC6.** `[Disconnect Stripe]` and `[Disconnect PostHog]` (each behind a confirm dialog) revert the respective chips to unconfigured state. The next webhook to the disconnected Stripe account returns 410 Gone; the next scheduled funnel poll skips the disconnected project.
- **AC7.** Existing budget tracking (cost reads, monthly rollups, ADR 0031 canonical reads) continues to work unchanged for both `internal_tool` and `b2c_product` project kinds after the MRR column is added. No regression in cost-meter values for projects with no Stripe connection.

## Open questions

- Stripe Connect OAuth callback URL: per-deploy-environment (prod vs staging) or single prod-only — defer to Architect.
- Webhook secret rotation cadence: alignment with the existing secret-rotation runbook (spec 0025 / design `automated-secret-rotation`) — defer to Architect.
- PostHog snapshot storage: full per-day rows or upsert-latest — defer based on funnel-detail card's data needs.
- Studio category-rollup: a dedicated `studio` parent in the INDEX tree is a known follow-up across 0075, 0077, 0079, and this spec — captured here, tracked separately.

## Links

- Parent spec: 0075 — Coder Studio b2c product portfolio operator contract
- Sibling spec: 0079 — Coder Studio product template repo contract (product-side env vars and `/api/internal/stripe-status`)
- Sibling spec: 0077 — referenced via related_specs
- ADR 0009 — per-managed-project cloud account and GitHub org (per-product isolation model)
- Design: `knowledge-and-admin` (parent category)
- Stripe Connect Express OAuth docs: https://stripe.com/docs/connect/oauth-reference
- PostHog Projects API: https://posthog.com/docs/api/projects

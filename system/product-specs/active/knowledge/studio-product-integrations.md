---
id: studio-product-integrations
title: Studio — Stripe Connect and PostHog integration
type: spec
status: active
owner: ro
created: 2026-05-15
updated: 2026-05-15
last_verified_at: 2026-05-15
summary: Stripe Connect Express OAuth, webhook MRR pipeline, and PostHog funnel polling for b2c_product projects in coder-core.
served_by_designs: []
related_specs: [admin-panel, secret-rotation]
parent: knowledge-and-admin
---

# Studio — Stripe Connect and PostHog integration

## What it is

coder-core's backend contribution to the Coder Studio b2c-product
surface: the Stripe Connect Express OAuth flow, the webhook endpoint
that ingests subscription events and computes MRR, the PostHog
credential store and 6-hour funnel poll, and the disconnect paths that
revert both integrations to unconfigured state. The operator surface is
the `b2c_product` project-detail page in the admin SPA (see
[admin-panel](./admin-panel.md)).

Both integrations ship together because they share the same operator
surface (per-product chips on the same card) and the same
OAuth-or-API-key + webhook-or-poll credential pattern.

## Users

- **Portfolio operator.** Monitors Stripe state and MRR/cost delta from
  the Studio panel; expects chips to settle within 60 seconds of any
  configuration action.
- **Founder recurring job.** Reads per-product MRR when scoring kill
  criteria (charter: cost-exceeds-MRR is a kill signal); no operator
  involvement in the poll loop.

## Capabilities

- **Stripe Connect Express OAuth flow.** A `b2c_product` project with no
  connected Stripe account shows a `[Connect Stripe]` chip on its
  project-detail page. Clicking opens Stripe Connect Express OAuth
  consent; after the operator authorizes, the connected-account
  credentials are stored in Secret Manager under
  `{project_id}/stripe/connected_account`. The chip transitions
  `disconnected → pending → live` within 60 seconds of webhook
  confirmation and links to the connected account in the Stripe
  dashboard.
- **Stripe webhook endpoint.** `POST /v1/webhooks/stripe` verifies the
  `Stripe-Signature` header; returns 200 for valid events and 401 for
  invalid signatures, persisting nothing on 401. Recognized event types
  (`customer.subscription.created/updated/deleted`,
  `invoice.payment_succeeded`, `charge.refunded`) are persisted to a
  `stripe_events` table scoped by `connected_account_id`.
- **MRR computation.** MRR derives from active subscriptions and
  refreshes within 5 minutes of any `customer.subscription.*` event.
  The product-detail cost meter shows `MRR: $X · MTD cost: $Y`;
  loss-making products (MRR < MTD cost) show a yellow chevron. Existing
  budget reads in `budget.py` (ADR 0031 canonical reads) are unchanged —
  MRR is an additive column only.
- **PostHog credential store.** A `b2c_product` project with no PostHog
  config shows `[Configure PostHog]`. The form accepts `project_api_key`
  and `region` (`us` | `eu`); on submit, coder-core validates against
  the PostHog `/api/projects` endpoint and returns `verified` or
  `auth_failed` inline within 10 seconds. A verified config is stored
  per-project in Secret Manager.
- **PostHog funnel polling.** For PostHog-connected products, a scheduled
  job polls every 6 hours, persists the snapshot, and drives the funnel
  chip showing the four standard steps
  (`signup → activate → checkout_start → checkout_complete`) with
  per-step counts and a last-updated timestamp. The chip always renders
  the most recent snapshot (≤ 6 hours old). Clicking opens a funnel
  detail card.
- **Disconnect paths.** `[Disconnect Stripe]` and `[Disconnect PostHog]`
  (each behind a confirm dialog) revert the respective chips to
  unconfigured state. The next webhook to a disconnected Stripe account
  returns 410 Gone; the next scheduled funnel poll skips disconnected
  projects. Both paths are designed for reuse by the Phase C
  `kill_pipeline`.

## Interfaces

- `POST /v1/projects/{id}/studio/stripe/connect` — initiate Stripe
  Connect Express OAuth flow; returns a redirect URL for the operator.
- `GET /v1/projects/{id}/studio/stripe/callback` — OAuth callback;
  exchanges code for credentials, stores to Secret Manager, triggers
  chip state transition.
- `POST /v1/webhooks/stripe` — Stripe event ingestion (global, not
  project-scoped); verifies `Stripe-Signature`; routes to the matching
  `connected_account_id`; returns 200 (valid + persisted), 401
  (invalid signature), or 410 Gone (disconnected account).
- `DELETE /v1/projects/{id}/studio/stripe` — disconnect Stripe;
  credentials revoked from Secret Manager, chip returns to
  disconnected state, future webhooks for this account return 410.
- `POST /v1/projects/{id}/studio/posthog` — store and verify PostHog
  `project_api_key` + `region`; returns `{"status": "verified"}` or
  `{"status": "auth_failed"}`.
- `DELETE /v1/projects/{id}/studio/posthog` — disconnect PostHog;
  credentials removed from Secret Manager, next scheduled poll skips
  the project.
- `GET /v1/projects/{id}/studio/funnel` — latest persisted PostHog
  funnel snapshot (≤ 6 hours old) with per-step counts and
  `last_updated` timestamp.
- **Secret Manager paths:** `{project_id}/stripe/connected_account`,
  `{project_id}/posthog/credentials`.
- **DB:** `stripe_events` table — `id`, `connected_account_id`,
  `event_type`, `payload`, `received_at`. MRR stored as a computed
  column on the existing project budget row (additive; no existing
  columns altered).

## Non-goals

- Resend / broadcast email — Phase C (Marketer role).
- PostHog cohort analysis or experiment tracking — Phase C (Analyst).
- Stripe Connect Standard — charter commits to Express only.
- Self-hosted PostHog — cloud only in Phase A; revisit if cloud costs
  exceed budget envelope.
- Cross-product MRR rollup — Phase C portfolio P&L surface.
- Refund initiation from the panel — `kill_pipeline` owns refunds
  during sunset.
- Tax handling (Stripe Tax wiring) — operator-decided per-product.

## Dependencies

- `secret-rotation` — webhook secret rotation aligns with the
  existing rotation runbook (design `automated-secret-rotation`);
  `{project_id}/stripe/connected_account` and
  `{project_id}/posthog/credentials` join the managed-secret registry.
- `admin-panel` — operator-facing chip UI and connect / configure /
  disconnect actions rendered in the admin SPA.
- ADR 0031 — budget read path; MRR column is additive; canonical
  reads in `budget.py` unchanged.
- ADR 0009 — per-managed-project cloud account isolation; Secret
  Manager paths are project-scoped.

## Open questions (deferred to Architect)

- Stripe Connect OAuth callback URL: per-deploy-environment (prod vs
  staging) or single prod-only.
- Webhook secret rotation cadence alignment with design
  `automated-secret-rotation`.
- PostHog snapshot storage: full per-day rows or upsert-latest
  (depends on funnel-detail card data needs).

## Evolution

- 0080 Phase A ship (2026-05-15) — initial spec: Stripe Connect
  Express OAuth, webhook endpoint with signature verification, MRR
  computation, PostHog credential store, 6-hour funnel poll, and
  disconnect paths for both integrations.

## Links

- Related specs: [admin-panel](./admin-panel.md),
  [secret-rotation](./secret-rotation.md)
- Phase A parent context: WIP 0075 — Coder Studio b2c product
  portfolio operator contract
- Phase A sibling: WIP 0079 — Coder Studio product template repo
  contract (product-side env vars and `/api/internal/stripe-status`)

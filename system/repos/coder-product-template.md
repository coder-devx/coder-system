---
id: coder-product-template
name: coder-product-template
type: repo
status: active
owner: ro
github: coder-devx/coder-product-template
default_branch: main
hosts_services: []
language: typescript
ci:
  provider: github-actions
  workflows: [ci]
cd:
  target: cloud-run
  trigger: push-to-main
decided_by: []
last_verified_at: '2026-05-13'
---

# coder-product-template

## What it holds

GitHub template repository for the Coder Studio's `b2c_product`
projects. Every product spawned by the Studio's create-product
bootstrap (Cloudflare CNAME → Cloud Run deploy → DNS write) starts
as a fork of this template — a Next.js + Tailwind + Stripe + PostHog
+ Resend scaffold pre-wired to the Studio runtime contract.

## Layout

The template is consumed via GitHub's "Use this template" API
(`PATCH is_template=true`); per-product forks land at
`coder-devx/<product-slug>` and inherit:

- Next.js app router with 8 standard routes (landing, pricing,
  signup, login, account, settings, dashboard, contact).
- Tailwind v4 with a theme contract in `theme.config.ts` —
  per-product visual tokens live here, the rest of the stack reads
  the contract.
- Stripe Connect + webhook handler stubs.
- PostHog client (web + server) with the per-product project key
  passed in at deploy time.
- Resend contact-form handler.
- Lighthouse CI configured to fail builds slower than 2s p75.

## CI / CD

- **CI**: ESLint + `tsc --noEmit` + Lighthouse-CI budget assertion
  on every PR.
- **CD**: per-product forks deploy via the Studio's bootstrap
  pipeline (`POST /studio/bootstrap`), not via this repo's own
  workflow. Pushes to `main` on the template itself are validation
  builds only — no Cloud Run target.

## Branching

- `main` is the template baseline. Studio forks branch from it at
  bootstrap time and evolve independently.

## Linked services

- Indirectly hosts every per-product Cloud Run service deployed by
  the Studio. Not directly bound to a single service in
  [services/registry.yaml](../services/registry.yaml) — the
  template itself isn't a runtime, only its forks are.

## Notes

- The template's scaffold was shipped by spec 0079 dev tasks
  ([coder-product-template#1-#5](https://github.com/coder-devx/coder-product-template/pulls?q=is%3Apr+is%3Aclosed)).
- Worker token (`coder-coder-github-pat`) has push + PR scope on
  this repo as of the Phase A bootstrap. Direct-to-main pushes are
  forbidden by branch protection per spec 0089.

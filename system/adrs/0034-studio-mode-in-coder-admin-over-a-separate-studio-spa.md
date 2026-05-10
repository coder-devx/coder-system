---
id: '0034'
title: Studio mode in coder-admin over a separate Studio SPA
type: adr
status: proposed
date: '2026-05-10'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- '0075'
---

# ADR 0034 — Studio mode in coder-admin over a separate Studio SPA

## Context

The Studio requires new UI surfaces: a portfolio dashboard, idea queue, product P&L view, asset gallery, and kill workflow panel. We had to decide whether these surfaces live inside the existing `coder-admin` SPA or in a new `coder-studio-admin` SPA.

## Options considered

1. **Studio mode in coder-admin** — a `VITE_STUDIO_ENABLED` feature flag activates a sidebar swap and lazy-loads a `studio` bundle chunk. The shell, auth flow, project switcher, command palette, audit log viewer, and pipeline UI carry over unchanged.
2. **Separate `coder-studio-admin` SPA** — a second React app with its own build, deploy, and Cloud Run static service. Shares the same coder-core API and auth token but is a distinct frontend with a distinct URL.
3. **Micro-frontend with shared shell** — a shared shell app hosts both as module-federation remotes. Shared auth and project switcher; separate lazy-loaded bundles per app.

## Decision

Studio mode in coder-admin (option 1).

## Rationale

The shell, auth, project switcher, command palette, and audit log viewer are the expensive parts to build and maintain — they already exist in `coder-admin`. Option 2 duplicates login, token refresh, project-context propagation, and all common UI primitives for a second app serving the same single operator. Option 3 solves code-sharing through module federation but introduces a build and operational setup whose complexity is disproportionate for one user population and one deploy target. The studio mode is a sidebar swap and a lazy-loaded chunk; if the IA eventually justifies a separate product for a distinct second user persona, the mechanical split is straightforward at that point.

## Consequences

- Positive: no second build pipeline, no second Cloud Run static service, no second login flow.
- Positive: audit log, pipeline view, and command palette work in studio mode with no modification.
- Negative: studio mode and core mode share the same deploy; a studio UI regression ships alongside a tooling regression. Mitigation: separate Vitest suites for studio components; `VITE_STUDIO_ENABLED` flag for gradual rollout.
- Negative: coder-admin bundle grows. Mitigation: studio chunk is lazy-loaded; the main bundle is unaffected.
- Follow-up: add `VITE_STUDIO_ENABLED=false` to `.env.example` and CI environment before the first studio component lands.

---
id: coder-admin
name: Coder Admin Panel
type: service
status: active
owner: ro
tier: core
repos: [coder-admin]
tech: [typescript, react, vite, tailwind]
runtime: cloud-run
region: europe-west1
depends_on:
  services: [coder-core]
  integrations: [gcp]
  data_stores: []
exposes:
  - protocol: http
    port: 8080
    path: /
implements_designs: ["0001"]
decided_by: []
---

# Coder Admin Panel

## What it does

The user-facing surface for Coder. The user picks a project, watches
workers, inspects pipeline runs, debugs failures, takes over a role,
and overrides decisions.

This is the "god mode" UI from goal #7 — the place where the human
is in charge.

## Responsibilities

- **Project switcher** — every screen is scoped to a single active project.
- **Worker grid** — live status of every worker in the active project's team.
- **Pipeline view** — task list, state, logs, test environments.
- **Knowledge browser** — render the project's `coder-system` repo with
  cross-link navigation.
- **Override / drive** — pause, resume, retry, take over a role.
- **Chat** — talk to any worker (or to Core directly) over SSE.

## API surface

Browser app — consumes `coder-core` HTTP/SSE API. Does not expose its own.

## Interactions

```mermaid
flowchart LR
  user[User] --> admin[Admin Panel]
  admin -- REST + SSE --> core[Coder Core]
```

## Operational notes

- Static assets served from a Cloud Run container running `nginx:1.27-alpine`
  on port 8080. SPA fallback to `/index.html`. `/healthz` returns `ok`.
- Auth: not implemented yet (walking skeleton). Planned: Google OAuth,
  allow-listed identities mapped to project ACLs in Core.
- `VITE_API_BASE_URL` is **build-time** — baked into the bundle by Vite.
  Per-environment values live in `.env.development` and `.env.production`
  in the repo. Changing the API base URL requires a rebuild + redeploy.
- Cross-origin: the browser hits `coder-core` directly, so `coder-core`'s
  `CORS_ALLOWED_ORIGINS` must include this service's URL.

## Current state (2026-04-09)

Walking skeleton: a single page (`Home`) that calls `GET /v1/health` on
`coder-core` on mount and renders the response. Proves the SPA can reach
core cross-origin and that the deploy pipeline works end-to-end. Project
list, switcher, worker grid, pipeline view, and knowledge browser come
next.

## Open questions

- Per-project theming / isolation in the UI to prevent context bleed when
  switching projects fast?
- How much of the worker prompt / state should be exposed in the UI vs.
  reserved for the consultant role?

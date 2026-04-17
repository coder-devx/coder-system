---
id: coder-admin
name: coder-admin
type: repo
status: active
owner: ro
github: coder-devx/coder-admin
default_branch: main
hosts_services: [coder-admin]
language: typescript
ci:
  provider: github-actions
  workflows: [ci]
cd:
  target: cloud-run
  trigger: push-to-main
decided_by: []
last_verified_at: 2026-04-09
---

# coder-admin

## What it holds

React + Vite single-page app for the Coder Admin Panel. Multi-project
from day one (project switcher is a top-level concern, not a retrofit).

## Layout

```
src/
  main.tsx            entry, router setup
  App.tsx             top-level layout
  api/client.ts       fetch wrapper for coder-core
  pages/              one file per route (Home is the walking skeleton)
  index.css           Tailwind v4 import
tests/                vitest unit tests (jsdom + testing-library)
Dockerfile            multi-stage: node build → nginx serve
nginx.conf            SPA config, listens on 8080
.github/workflows/ci.yml   check · build · deploy via WIF
```

The full layout contract lives in [`AGENTS.md`](https://github.com/coder-devx/coder-admin/blob/main/AGENTS.md).
Future feature folders (projects, workers, pipeline, knowledge, chat,
overrides) will land under `src/features/` as the surface grows.

## CI / CD

- **CI**: ESLint, Prettier, `tsc --noEmit`, Vitest, `vite build` on every
  PR. Same job runs on every push to `main`.
- **CD**: push to `main` → multi-stage Docker build → push to
  `europe-west1-docker.pkg.dev/vibedevx/coder-admin/coder-admin:{git-sha}`
  → `gcloud run services update coder-admin --image=…`. Auths via WIF.
  See [`deploy-coder-admin`](../runbooks/deploy-coder-admin.md).

## Branching

- `main` is always deployable.

## Linked services

- Hosts [`coder-admin`](../services/coder-admin.md).

## Notes

- Replaces the old `coder-agent-admin`. Built clean — does **not** lift
  components from the old admin wholesale.
- Use `npm` (never `yarn`/`pnpm`). Node 22 is the floor (`.nvmrc`).
- `VITE_API_BASE_URL` is build-time only. Per-env values are committed
  in `.env.development` and `.env.production`. To override locally use
  `.env.local` (gitignored).

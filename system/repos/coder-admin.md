---
id: coder-admin
name: coder-admin
type: repo
status: planned
owner: ro
github: coder-devx/coder-admin
default_branch: main
hosts_services: [coder-admin]
language: javascript
ci:
  provider: github-actions
  workflows: [test, lint, build]
cd:
  target: cloud-run
  trigger: push-to-main
decided_by: []
---

# coder-admin

## What it holds

React + Vite single-page app for the Coder Admin Panel. Multi-project
from day one (project switcher is a top-level concern, not a retrofit).

## Layout (proposed)

```
src/
  app/                  routes, layout, project-switcher
  features/
    projects/
    workers/
    pipeline/
    knowledge/          knowledge repo browser
    chat/
    overrides/          drive / pause / take over a role
  api/                  Coder Core HTTP + SSE clients
  components/
  styles/
index.html
vite.config.ts
tailwind.config.js
```

## CI / CD

- **CI**: lint, type-check, unit + e2e tests on every PR.
- **CD**: push to `main` builds the static bundle, packs into a container,
  deploys to Cloud Run.

## Branching

- `main` is always deployable.

## Linked services

- Hosts [`coder-admin`](../services/coder-admin.md).

## Notes

- Replaces the old `coder-agent-admin`. Built clean — does **not** lift
  components from the old admin wholesale.

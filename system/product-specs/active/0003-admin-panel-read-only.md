---
id: "0003"
title: Admin Panel v0 (read-only)
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0001", "0002", "0006"]
---

# Admin Panel v0 (read-only)

**Phase:** Now (foundation)
**Progress:** 6 / 6 acceptance criteria

## Problem

Once projects exist and the knowledge API is serving, there has to be a
place for a human to *see* what's in the system — which projects exist,
which artifacts they contain, and whether the knowledge is well-formed.
Without a panel, the only way to inspect state is `psql` and GitHub,
which is fine for the person building `coder-core` but useless for
everyone else on the team. This v0 is deliberately read-only: we want
confidence in the data model before exposing mutations.

## Users / personas

- **Ro (the human owner)** — needs a surface to verify that projects
  are being created correctly and the knowledge read API returns what
  the file system says it should.
- **Software Architect** — validates that the knowledge graph renders
  end-to-end and that cross-links actually resolve when a human clicks
  them.
- **Developer** on `coder-admin` — needs a small, shippable scope that
  exercises the Core API without waiting on workers.
- **Any future teammate** — gets oriented in a new project by browsing
  its knowledge repo without ever opening GitHub.

## Goals

- Launch a React/Vite SPA at a known URL that talks only to `coder-core`.
- Project switcher in the top bar, backed by `GET /projects`.
- Project detail view showing the knowledge index for that project.
- Artifact detail view showing parsed frontmatter and rendered markdown
  body (including Mermaid).
- Clicking a cross-link inside an artifact navigates to the linked
  artifact without a full page reload.

## Non-goals

- Any mutation — no creating projects, no editing artifacts, no
  triggering pipeline runs. (Those land in spec `0006`.)
- Full-text search.
- Real authentication — v0 ships with a local dev login shim; proper
  auth lands alongside impersonation in spec `0007`.
- Dark mode, theming, or polish beyond "legible".

## Scope

- Vite + React + TypeScript app in a new `coder-admin` repo.
- Routing: `/`, `/projects/:id`, `/projects/:id/:type`,
  `/projects/:id/:type/:artifact_id`.
- Project switcher component in the header.
- Generic artifact renderer: frontmatter table + markdown body with
  Mermaid blocks rendered client-side.
- Minimal design system: system fonts, no CSS framework bigger than a
  100-line stylesheet.
- CI/CD scaffold: lint, typecheck, build, deploy to a preview env.

## Acceptance criteria

- [x] Loading the app against a seeded Core shows the project list.
- [x] Switching projects updates the URL and the visible knowledge
      without a full reload.
- [x] Opening a spec shows its parsed frontmatter and the rendered
      markdown body.
- [x] A Mermaid diagram inside an active design renders in the browser.
- [x] A cross-link inside an artifact body (e.g. "ADR 0005") is a
      clickable link that routes to the linked artifact.
- [x] The app makes zero direct calls to GitHub — all reads go through
      `coder-core`.

## Metrics

- **Time-to-first-render** of a project's knowledge index under 1s on a
  warm cache.
- **Zero** unhandled render errors across all artifact types in an
  end-to-end test that walks the whole registry.
- **Bundle size** under 300KB gzipped for v0.

## Open questions

- Local dev auth shim — hard-coded token, OS keychain, or just
  `localhost`-only bypass?
- Client-side Mermaid rendering library choice (`mermaid` official vs.
  a lighter wrapper)?
- Do we preview `coder-admin` per-PR or only on merge to main?

## Links

- Designs: [`0004`](../../designs/wip/0001-generalize-coder-from-vibetrade.md) (build plan step 3)
- Services: [`coder-admin`](../../services/coder-admin.md)
- Related specs: [`0001`](./0001-multi-tenant-project-crud.md), [`0002`](./0002-knowledge-repo-read-api.md), [`0006`](./0006-pipeline-ui-in-admin.md)

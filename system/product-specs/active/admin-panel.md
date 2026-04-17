---
id: admin-panel
title: Admin Panel
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-15
served_by_designs: [system-overview]
related_specs: []
---

# Admin Panel

## What it is

`coder-admin` is the human operator's primary control surface — a
React/Vite SPA that talks exclusively to `coder-core`. It browses a
project's knowledge repo, watches the pipeline live, and drives the
mutations that keep the system moving (create tasks, override stages,
approve merges, edit knowledge). Authenticated via Google OAuth with an
email allowlist; sessions carry an admin JWT with cross-project access.

## Capabilities

- Google OAuth login with email allowlist; unauthenticated requests
  redirect to the login flow. Admin JWT (HS256) sessions audited in
  `admin_sessions`.
- Project switcher in the header backed by `GET /v1/projects`, with
  per-project API-key prompt persisted in `localStorage`.
- Knowledge browser: project list, per-type registry list, artifact
  detail with frontmatter table, react-markdown body, lazy-loaded
  Mermaid rendering, and cross-links rewritten to in-app router
  navigation (zero direct GitHub reads from the browser).
- Inline editing of spec acceptance-criteria checkboxes, committed back
  through the knowledge write API.
- Pipeline view scoped to the selected project: live task list with
  status chips, filters by `role` and `status`, task detail with
  streamed logs and links out to repo/branch/commit.
- Task lifecycle mutations: create (role + repo + prompt form),
  pause/resume/retry/skip/reject overrides, approve-merge on reviewed
  tasks (squash-merge via GitHub API).
- Real-time updates via SSE — stage transitions and new messages appear
  within ~2s without polling.

## Interfaces

- Routes: `/`, `/projects/:id`, `/projects/:id/:type`,
  `/projects/:id/:type/:artifactId`, `/projects/:id/pipeline`,
  `/projects/:id/pipeline/:taskId`.
- Consumes `coder-core` REST (projects, knowledge, tasks, overrides,
  merge, knowledge PUT) and SSE event stream for pipeline + messages.
- Typed API client shared across views; reusable `StatusChip` and
  status/timestamp components.

## Dependencies

- multi-tenancy — project listing and scoping.
- knowledge-api — all artifact reads and checkbox edits.
- `coder-core` task + pipeline endpoints, override endpoint, merge
  endpoint, SSE event bus.
- GitHub (via `coder-core`) for merge action.

## Evolution

- 0003 Admin panel v0 (shipped 2026-04) — Vite/React SPA, project
  switcher, knowledge browser with Mermaid + cross-link rewriting,
  read-only, local dev auth shim.
- 0006 Pipeline UI in admin (shipped 2026-04) — pipeline tab with live
  task list, filters, streamed logs, commit deep-links; added
  `?role=`/`?status=` filters on `GET /tasks`.
- 0012 Admin auth and mutations (shipped 2026-04) — Google OAuth +
  email allowlist, admin JWT, task creation form, override and
  approve-merge actions, SSE-driven real-time pipeline, checkbox editing
  of knowledge.
- 0026 Pipeline run dashboard (shipped 2026-04-17) — Runs list sorts
  blocked-longest-first with a red "blocked Nm" badge per row;
  RunDetail renders an inline Gate card for spec/design approvals
  (approve / request-changes / reject, all from the run view) with a
  drill-through for plan approval; the step chip + blocked badge is
  the primary what-needs-me-now signal. Reads
  `pipeline_runs.step_started_at` / `blocked_since` (spec 0026
  migrations 0028/0029) and the new
  `GET /v1/projects/{id}/ops/step-stats` rollup.

## Links

- Designs: (none yet)
- Related components: multi-tenancy, knowledge-api

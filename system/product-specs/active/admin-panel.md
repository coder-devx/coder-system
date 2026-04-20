---
id: admin-panel
title: Admin Panel
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-19
last_verified_at: 2026-04-19
served_by_designs: [system-overview]
related_specs: [audit-log]
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
- **Ship gate panel.** RunDetail renders a two-column Ship gate when
  the close-cycle backstop has stamped `wips_pending_merge` on a
  pipeline run: left column shows the architect-drafted `merges[]`
  (per-file diff + post-merge frontmatter); right column shows the
  reviewer's `ship_attestation` (AC → `active/` section pairings and
  drop reasons). Approve calls `POST /knowledge/ship` which lands the
  atomic commit; Reject opens a structured audit record and leaves the
  WIP in flight. The gate is distinct from the existing PR-merge gate
  and never touches GitHub branch protection (ADR 0015).
- **Live pipeline-run timeline.** RunDetail's primary panel is a
  `RunTimeline` SVG swim-lane view — one lane per pipeline step
  (`pm_draft`, `architect`, `team_manager`, `pm_accept`), one bar per
  `task_stage_run` colored by outcome (succeeded/running/failed/blocked).
  Running bars live-tick via `useLiveTick`; per-lane median/p75 badges
  come from `pipeline_step_stats`. Click a bar to drill into the task;
  click the lane label to filter the pipeline view. SSE refetch is
  bounded to `pipeline_run.changed` only — no polling ladder.
  `VITE_RUN_TIMELINE_ENABLED` (default on) for hotfix rollback.
- **In-panel PR diff viewer.** TaskDetail carries a "PR" toggle that
  opens a lazy-loaded `PrViewer` panel rendering the unified diff +
  PR metadata + the reviewer's existing `review_verdict` / `review_body`
  banner. A custom Tailwind-only diff renderer (no extra deps) splits
  on `diff --git` and colours add/remove/hunk lines. Backed by a single
  `/tasks/{id}/pr` endpoint that fans out two concurrent GitHub calls.
  Empty, error, and loading branches all render. `VITE_PR_VIEWER_ENABLED`
  (default on).
- **Inline knowledge editor.** The artifact page carries an Edit
  toggle next to Approve / Reject that swaps the body section for a
  `<textarea>` + live `MarkdownBody` preview. Save calls the existing
  `PUT /knowledge/{type}/{id}`; the response's commit SHA is briefly
  surfaced ("Saved · abc1234"). `beforeunload` warns on unsaved
  edits; 4xx/5xx keep the editor open with the inline error; approve
  buttons disable while there are unsaved changes so approvals always
  gate the currently-committed content. Phase-1 scope is body-only —
  frontmatter editing is deferred. Behind `VITE_KNOWLEDGE_EDITOR_ENABLED`
  (default on).
- **Command palette (⌘K).** A global `CommandPalette` modal mounted at
  the App shell opens from any route on `⌘K` / `Ctrl+K` (also `?`),
  closes on Esc. Mixes navigation entries (projects, recent tasks,
  knowledge artifacts, pipeline runs) and runnable actions (retry
  stuck tasks, grant/revoke budget override, open run override). A
  project-scoped URL boosts that project's entries; recent activations
  (localStorage, 20 entries) boost as well. Hand-rolled fuzzy ranker
  (no `cmdk` / `fuse.js` dependency). Inert inside `<input>` /
  `<textarea>` unless the element opts in. Behind
  `VITE_COMMAND_PALETTE_ENABLED` (default on).
- **Audit log viewer.** Two routes render the system's mutation log:
  `/projects/:projectId/audit` (tenant-scoped) and `/admin/audit`
  (fleet). Table rows show timestamp (local TZ + UTC tooltip), actor,
  action, target type/id, project (fleet view only), and a clickable
  correlation chip that filters to every row sharing the same request
  ID. Filter bar: actor / action dropdowns, date range, correlation
  filter. Expand-row renders `before` / `after` JSON pretty-printed
  side-by-side. Loading / empty / error branches all render; "Load
  more" keyset-paginates via the `after=<lastId>` ULID cursor. The
  page shows an "Audit logging disabled" banner above historical rows
  when `CODER_AUDIT_LOG_ENABLED` is off so a log gap is a visible
  operator decision.

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
- 0044 Write-through enforcement on ship (shipped 2026-04-18) — new
  Ship gate panel on RunDetail fires off `wips_pending_merge`;
  two-column layout renders the architect-drafted `merges[]` beside
  the reviewer's `ship_attestation`. Approve posts to
  `/knowledge/ship` (atomic Git Trees commit); Reject records an
  audit entry and leaves the WIP in flight. Gate lives entirely in
  the admin panel — no branch-protection integration per ADR 0015.
- 0033 Live pipeline-run timeline (shipped 2026-04-19) — `RunTimeline`
  component renders the per-run swim-lane view on
  `/projects/:id/runs/:runId`. Backed by the new
  `GET /v1/projects/{id}/pipeline-runs/{run_id}/timeline` endpoint that
  reassembles `task_stage_runs` into a lane-per-step payload with
  `pipeline_step_stats` medians; no new storage. `useLiveTick` drives
  sub-second tick on open bars; refetch is `pipeline_run.changed`-SSE
  triggered (chattier events are ignored). Behind
  `VITE_RUN_TIMELINE_ENABLED` (default on).
- 0034 In-panel diff & PR viewer (shipped 2026-04-19) — new
  `PrViewer` panel on TaskDetail renders unified diffs inline. Backed
  by `GET /v1/projects/{id}/tasks/{task_id}/pr` which parses `pr_url`
  and fans out concurrent `fetch_pr` / `fetch_pr_diff` GitHubClient
  calls. Verdict/body come from the existing `review_verdict` /
  `review_body` columns — no new storage, no GitHub writes. Custom
  Tailwind-only diff renderer handles +/-/@@ colouring. Empty,
  error, and loading states all graceful. Behind
  `VITE_PR_VIEWER_ENABLED` (default on).
- 0035 Inline knowledge editor with approvals (shipped 2026-04-19,
  body-only) — new `ArtifactEditor` component on the artifact page
  with a state machine (`viewing → editing → saving → ok|conflict|error`).
  Save calls the existing `PUT /v1/projects/{pid}/knowledge/{type}/{id}`
  endpoint; no backend changes. Live preview reuses the same
  `MarkdownBody` renderer as the read view — no render drift.
  `beforeunload` guard on unsaved edits; approval buttons disabled
  while dirty. `knowledge_edited` structured log event at save.
  Frontmatter form deferred to phase 2. Behind
  `VITE_KNOWLEDGE_EDITOR_ENABLED` (default on).
- 0036 Command palette & keyboard-first navigation (shipped 2026-04-19)
  — new `CommandPalette.tsx` portal-mounted at the App shell,
  accessible from every route. `useCommandPalette()` hook binds
  `⌘K` / `Ctrl+K` globally (inert inside focused text inputs unless
  opted in). Entry sources are pluggable providers: `navProvider`,
  `projectsProvider`, `projectTasksProvider`, `projectArtifactsProvider`,
  `projectRunsProvider`, `actionsProvider`. Recent-activation history
  (localStorage, 20 entries) boosts fuzzy-rank score; project-scoped
  URL boosts per-project entries. Pure frontend — no backend changes.
  Hand-rolled ranker, no new runtime dep. Behind
  `VITE_COMMAND_PALETTE_ENABLED` (default on).
- 0037 Audit log viewer (shipped 2026-04-19) — new `AuditLog.tsx`
  page at `/projects/:projectId/audit` and `/admin/audit`, backed by
  the new `GET /v1/projects/{id}/audit-events` (tenant-scoped) and
  `GET /v1/admin/audit-events` (fleet). Table + filter bar + expand-
  for-payload + correlation-chip deep link. `listProjectAuditEvents`
  / `listFleetAuditEvents` client bindings; keyset pagination on the
  ULID cursor. Disabled-banner surfaces the
  `CODER_AUDIT_LOG_ENABLED=false` state. Full component lives in
  `pages/AuditLog.tsx`; no new runtime deps. Behind
  `VITE_AUDIT_LOG_ENABLED` (default on).

## Links

- Designs: (none yet)
- Related components: multi-tenancy, knowledge-api

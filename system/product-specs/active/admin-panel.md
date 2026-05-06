---
id: admin-panel
title: Admin Panel
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: [system-overview]
related_specs: [audit-log]
parent: knowledge-and-admin
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
- **Metrics dashboard.** `/projects/:projectId/metrics` renders cost
  and pipeline-health views: daily-cost sparkline, per-spec cost
  breakdown, average stage durations, per-role prompt-cache stats
  (spec 0029), per-tier model usage (spec 0030). Period selector
  (24h / 7d / 30d). Powers operator triage of cost spikes without a
  console query.
- **Freshness audit view.** `/freshness` (fleet) and
  `/projects/:projectId/freshness` show the knowledge-freshness
  dashboard (spec 0043): score histogram of the latest audit run,
  stale-count tile, "Needs attention" table of the lowest-scored
  artifacts, one-click `Verify` button that POSTs to
  `/knowledge/{type}/{id}/verify`. Operators can also trigger an
  on-demand audit pass via `triggerKnowledgeAudit()`.
- **Regression dashboard.** `/metrics/regressions` lists fleet-wide
  per-role cost regressions (spec 0032) with commit-suspect
  attribution and Slack-sent flag; `Acknowledge` action suppresses
  repeat fires for `(role, metric, day)`.
- **Plan review surface.** `/projects/:projectId/plans` lists draft
  Team-Manager plans; `/plans/:planId` opens the inline plan editor
  with per-task prompt / role / complexity / order edits before
  approve / reject (spec 0013).
- **Pipeline-run detail with live timeline + inline gate card.**
  `/projects/:projectId/runs/:runId` renders the `RunTimeline`
  swim-lane view (one lane per pipeline step, bars from
  `task_stage_runs`, live sub-second tick on running bars), an
  inline `GateCard` for spec/design/plan approvals, and the
  ship-gate panel when `wips_pending_merge` is stamped (spec 0044).
  The Runs list (`/projects/:projectId/runs`) sorts
  blocked-longest-first.
- **Auto-approval cards.** `ProjectDetail` renders `AutoApprovalCard`
  rows when `VITE_AUTO_APPROVE_ENABLED` is on (spec 0040): worker
  score, risk flags, justification, undo within window, force-finalize.
- **Per-project budget cards.** `ProjectDetail` carries
  `BudgetCard` / `BudgetStateCard` / `BudgetReadSourceCard` (spec
  0031 phase 2): hard/soft limits, daily-spend sparkline, 7-day
  cost, override grant/revoke (24h), forecast, rollup-reads toggle.
  `Projects.tsx` shows a per-project `BudgetCell` summary on the
  fleet overview.
- **Worker concurrency strip.** Live per-project worker-slot
  availability + queue depth poll (spec 0028); the fleet variant
  rides on the admin home.
- **Auth-mode toggle.** `ProjectDetail`'s `AuthModeCard` switches a
  project between API key, Claude OAuth, and inherit-fleet-default
  (spec service-accounts Evolution); `PATCH
  /v1/_admin/projects/{id}/auth-mode` writes the column and a
  `project.set_auth_mode` audit row.
- **Tenant-isolation coverage dashboard.** `/admin/isolation` (admin
  JWT, behind `VITE_ISOLATION_VIEW_ENABLED`) renders the parsed
  isolation manifest as three tables — endpoints / tables / tokens
  — with a covered/skipped/missing chip per row (spec 0039).
- **Secret-rotation registry.** `/admin/secrets` (admin JWT, behind
  `VITE_SECRET_ROTATION_ENABLED`) lists managed secrets with rotator
  state and last-rotated timestamp.
- **Escalations.** `/admin/escalations` (fleet) and
  `/projects/:projectId/escalations` (per-project) render open /
  acknowledged / resolved escalations with age, current rung,
  project, run/task target, and on-call identity. `Ack` and
  `Resolve` actions POST to the project endpoints; behind
  `VITE_ESCALATIONS_ENABLED`.
- **Managed-workflows matrix.** `/admin/managed-workflows` (fleet,
  admin JWT, behind `VITE_MANAGED_WORKFLOWS_ENABLED`) renders the
  fleet × workflow grid from the managed-workflows manifest: one row
  per project, one column per expected workflow. Cell status pill:
  `✓ installed` / `⚠ drift` / `✗ missing` / `… installing`
  (PR open). Click cell → PR URL (if installing), drift diff (if
  drift), or workflow source (if installed). Backed by
  `GET /v1/_admin/managed-workflows` (verify_workflow per cell,
  cached 5 min). See [managed-workflows](./managed-workflows.md).

## Interfaces

- **Routes (defined in `src/main.tsx`):**
  - Fleet: `/`, `/freshness`, `/metrics/regressions`, `/admin/audit`,
    `/admin/secrets` (flagged), `/admin/isolation` (flagged),
    `/admin/escalations` (flagged),
    `/admin/managed-workflows` (flagged).
  - Per-project: `/projects/:projectId`,
    `/projects/:projectId/freshness`,
    `/projects/:projectId/pipeline`,
    `/projects/:projectId/pipeline/:taskId`,
    `/projects/:projectId/metrics`,
    `/projects/:projectId/runs`, `/projects/:projectId/runs/:runId`,
    `/projects/:projectId/ship/:wipId`,
    `/projects/:projectId/audit`,
    `/projects/:projectId/escalations` (flagged),
    `/projects/:projectId/plans`,
    `/projects/:projectId/plans/:planId`,
    `/projects/:projectId/:type`,
    `/projects/:projectId/:type/:artifactId`.
- **Project sub-nav** (`ProjectNav.tsx`): Overview, Pipeline, Runs,
  Plans, Metrics, Freshness, Audit (flagged), Escalations (flagged).
- Consumes `coder-core` REST (projects, knowledge, tasks, overrides,
  merge, knowledge PUT, ship, escalations, audit, freshness, budget,
  isolation, regressions, secrets, managed-workflows) and the SSE
  event stream for pipeline / message / `pipeline_run.changed` /
  `pipeline_run.gate_blocked` events.
- Typed API client (`src/api/client.ts`) shared across views — every
  endpoint has a single typed function. Reusable `StatusChip`,
  `RunTimeline`, `PrViewer`, `MarkdownBody`, `CommandPalette`, plus
  per-feature card components on `ProjectDetail`.
- **Frontend feature flags** (`VITE_*_ENABLED`): `VITE_AUDIT_LOG_ENABLED`,
  `VITE_SECRET_ROTATION_ENABLED`, `VITE_ISOLATION_VIEW_ENABLED`,
  `VITE_ESCALATIONS_ENABLED`, `VITE_AUTO_APPROVE_ENABLED`,
  `VITE_RUN_TIMELINE_ENABLED`, `VITE_PR_VIEWER_ENABLED`,
  `VITE_KNOWLEDGE_EDITOR_ENABLED`, `VITE_COMMAND_PALETTE_ENABLED`,
  `VITE_MANAGED_WORKFLOWS_ENABLED`.

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
- 0041 Escalations admin pages (shipped 2026-05-03) — backend
  shipped 2026-04-22 alongside the watcher; the admin UI half landed
  today. New `/admin/escalations` fleet view +
  `/projects/:projectId/escalations` per-project tab list open /
  acknowledged / resolved / expired escalations with age, current
  rung, trigger kind, target run/task deep-link, and on-call ack/
  resolve identity. Status filter on both views; trigger filter on
  the fleet view. `Ack` and `Resolve` buttons POST to the existing
  project endpoints; the table updates the affected row in place.
  Backed by `listProjectEscalations` / `listFleetEscalations` /
  `acknowledgeEscalation` / `resolveEscalation` client bindings on
  the existing backend (`GET /v1/projects/{id}/escalations`,
  `GET /v1/_admin/escalations`,
  `POST /v1/projects/{id}/escalations/{id}/acknowledge`,
  `POST /v1/projects/{id}/escalations/{id}/resolve`). Behind
  `VITE_ESCALATIONS_ENABLED` (default on); the project sub-nav grows
  an Escalations tab when the flag is on. Page +
  6 vitest cases land in `pages/Escalations.tsx`. See
  [escalations](./escalations.md).
- Claude OAuth auth-mode toggle (shipped 2026-04-22) — `ProjectDetail`
  gains a per-project auth-mode selector (`api_key` default /
  `oauth`) backed by `PATCH /v1/_admin/projects/{id}/auth-mode`.
  Selects which credential the dispatcher hands to a worker's
  `claude` process. See [service-accounts](./service-accounts.md)
  Evolution for the server-side wiring.
- 0052 Managed-workflows matrix (shipped 2026-05-06) — new
  `/admin/managed-workflows` fleet page renders the project × workflow
  install-status grid from the fleet manifest. Cell click shows PR
  URL, drift diff, or workflow source depending on verify status.
  Backed by `GET /v1/_admin/managed-workflows` (5-min cache). Behind
  `VITE_MANAGED_WORKFLOWS_ENABLED` (default off). See
  [managed-workflows](./managed-workflows.md).

## Links

- Designs: [system-overview](../../designs/active/system-overview.md)
- Related components: [multi-tenancy](./multi-tenancy.md),
  [knowledge-api](./knowledge-api.md), [audit-log](./audit-log.md),
  [escalations](./escalations.md), [observability](./observability.md),
  [task-orchestration](./task-orchestration.md),
  [managed-workflows](./managed-workflows.md)

---
id: admin-panel
title: Admin Panel
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-20
last_verified_at: 2026-05-20
summary: User-facing SPA for status, debug, override.
served_by_designs: [system-overview]
related_specs: [audit-log, studio-b2c-portfolio]
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
- **`failure_kind` chip label map.** The Pipeline list's status chip
  resolves known `failure_kind` codes to human-readable labels:
  `spec_collision` → "Spec collision", `adr_collision` → "ADR
  collision", `schema` → "Schema error". All collision-kind chips
  share consistent styling. The task-detail page renders the
  `failure_detail` JSON block when present; for `adr_collision` tasks
  this surfaces `collided_adr_ids` and `committed_adr_ids` inline,
  giving operators a direct list of which ADRs need hand-recovery.
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
- **CI Fix Loop card.** RunDetail and TaskDetail carry a collapsible
  `CiFixLoopCard` (behind `VITE_CI_FIX_LOOP_ENABLED`) showing the
  original task id, each fix-up attempt's task id + outcome, the
  current attempt counter, and the last failure excerpt if escalated.
  Backed by the `pr_to_task_map` row surfaced through the task detail
  endpoint. Operators can deep-link to each attempt task directly
  from the card.
- **Reviewer security and performance chips.** TaskDetail for
  reviewer-role tasks shows a "Security" count chip and a
  "Performance" count chip alongside the existing verdict chip,
  reading `security_finding_count` and `performance_finding_count`
  from task metadata. Counts of 0 render as `0 security` /
  `0 performance`; non-zero counts use a distinct colour to draw
  operator attention. Behind `VITE_REVIEWER_FINDINGS_ENABLED`
  (default on).
- **Timed-out stall callout.** TaskDetail renders a "Timed out"
  callout above the message log for `status = timed_out` tasks,
  naming the last pipeline stage and total elapsed time (e.g.,
  "Timed out in `executing` after 8m 23s"). The callout includes a
  "Jump to transcript" button that scrolls the message-log panel to
  the final pre-timeout message and highlights it, using stable
  `id="msg-{message_id}"` DOM anchors on message rows. The pipeline
  task list renders a secondary stage label on `timed_out` rows
  (e.g., "timed out · executing") so the stall stage is visible
  without navigating to the task-detail page. Both surfaces render
  regardless of which system path produced the `timed_out` status
  (worker subprocess timeout, self-healing remediator, or platform
  error). Backed by `timeout_stage`, `timeout_total_elapsed_s`, and
  `timeout_stage_elapsed_s` on `GET /v1/projects/{id}/tasks/{tid}`
  (see [task-orchestration](../../pipeline/task-orchestration.md)).
- **`b2c_product` project kind.** The project list and project switcher
  render a type badge distinguishing `internal_tool` (existing,
  retroactively badged) from `b2c_product` (Studio). A `b2c_product`
  project-detail view replaces the pipeline tab with a Studio-flavoured
  view: Stripe connected-account state chip, monthly cost meter with
  $100 and $300 threshold lines, PostHog funnel snapshot
  (visitors → signups → activations → paying), and a kill-criteria
  tracker (five charter criteria with status and elapsed time when
  violated). Kill-workflow confirmation dialog shows criteria met,
  revenue-to-date, and the downstream cascade before operator confirms
  sunset. Behind `VITE_STUDIO_ENABLED`.
- **Studio sidebar.** When at least one `b2c_product` project exists,
  the sidebar gains a **Studio** section: Idea Queue (ranked Founder
  candidates with `[approve]` / `[reject]` / `[ask Founder]` actions;
  approve triggers a PM draft task and writes `audit_event`; reject
  applies a decay factor, re-ranks, and writes `audit_event`),
  Portfolio table (name, MRR, spend, status), and per-product detail
  (`[flag for sunset]`, `[pause Founder reviews]`,
  `[view build artifacts]`). Behind `VITE_STUDIO_ENABLED`. Full
  contract: see [studio-b2c-portfolio](../studio-b2c-portfolio.md).

## Interfaces

- **Routes (defined in `src/main.tsx`):**
  - Fleet: `/`, `/freshness`, `/metrics/regressions`, `/admin/audit`,
    `/admin/secrets` (flagged), `/admin/isolation` (flagged),
    `/admin/escalations` (flagged).
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
  - Studio (behind `VITE_STUDIO_ENABLED`): `/studio/ideas`,
    `/studio/portfolio`, `/projects/:projectId/studio`,
    `/projects/:projectId/studio/founder`.
- **Project sub-nav** (`ProjectNav.tsx`): Overview, Pipeline, Runs,
  Plans, Metrics, Freshness, Audit (flagged), Escalations (flagged).
- Consumes `coder-core` REST (projects, knowledge, tasks, overrides,
  merge, knowledge PUT, ship, escalations, audit, freshness, budget,
  isolation, regressions, secrets) and the SSE event stream for
  pipeline / message / `pipeline_run.changed` /
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
  `VITE_CI_FIX_LOOP_ENABLED`, `VITE_REVIEWER_FINDINGS_ENABLED`,
  `VITE_STUDIO_ENABLED`.

## Dependencies

- multi-tenancy — project listing and scoping.
- knowledge-api — all artifact reads and checkbox edits.
- `coder-core` task + pipeline endpoints, override endpoint, merge
  endpoint, SSE event bus.
- GitHub (via `coder-core`) for merge action.

## Evolution

- 2026-04 — v0 through pipeline mutations (specs 0003, 0006, 0012):
  Vite/React SPA shell, project switcher, knowledge browser
  (Mermaid + cross-link rewrite), pipeline tab with streamed logs and
  filters, Google OAuth + admin JWT, task creation, override and
  approve-merge actions, SSE-driven real-time pipeline, checkbox
  editing of knowledge.
- 2026-04-17 through 2026-05-03 — RunDetail surfaces (specs 0026, 0044,
  0033, 0034, 0035, 0036, 0037, 0041): blocked-longest-first runs
  list, inline Gate card, ship-gate panel for `wips_pending_merge`,
  swim-lane `RunTimeline`, in-panel `PrViewer`, `ArtifactEditor`
  inline knowledge editor, `CommandPalette` (⌘K), audit log viewer,
  escalations admin pages, Claude OAuth auth-mode toggle.
- 2026-05-12 through 2026-05-15 — Failure-mode chips and Studio
  surfaces (specs 0086, 0094, 0075): `adr_collision` chip with inline
  collided/committed ADR ids; reviewer "Security" / "Performance"
  count chips on TaskDetail; `b2c_product` type badge, Studio sidebar
  (Idea Queue / Portfolio / per-product detail), and Studio-flavoured
  project-detail replacement behind `VITE_STUDIO_ENABLED`. Full
  Studio contract: see [studio-b2c-portfolio](../studio-b2c-portfolio.md).
- 2026-05-20 — Timed-out stall visibility: TaskDetail "Timed out"
  callout with stage name, elapsed time, and "Jump to transcript"
  button; pipeline list secondary stage label on `timed_out` rows
  (spec 0096).

## Links

- Designs: [system-overview](../../designs/active/system-overview.md)
- Related components: [multi-tenancy](./multi-tenancy.md),
  [knowledge-api](./knowledge-api.md), [audit-log](./audit-log.md),
  [escalations](./escalations.md), [observability](./observability.md),
  [task-orchestration](./task-orchestration.md),
  [reviewer-worker](./reviewer-worker.md),
  [studio-b2c-portfolio](../studio-b2c-portfolio.md)

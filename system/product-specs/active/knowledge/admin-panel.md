---
id: admin-panel
title: Admin Panel
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-17
last_verified_at: 2026-05-17
summary: User-facing SPA for status, debug, override.
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
approve merges, edit knowledge). Authenticated via Google OAuth with
an email allowlist; sessions carry an admin JWT with cross-project
access.

## Capabilities

The surface is organised around four operator jobs:

- **Knowledge browser & editor.** Per-project artifact lists (specs,
  designs, ADRs, roles, services, repos, runbooks), artifact detail
  with frontmatter table, react-markdown body, lazy Mermaid render,
  and in-app cross-link rewriting (no GitHub reads from the browser).
  Inline editor toggles the body section into an edit-mode textarea
  with live preview; saves call the knowledge write API. Inline
  spec-AC checkbox edits commit through the same path. The freshness
  view ranks the lowest-scored artifacts and exposes a one-click
  `Verify` button.

- **Pipeline & task control.** Per-project Pipeline list with
  status-chip filters by role and status; task detail page with
  streamed logs, repo/branch/commit deep links, and a lazy-loaded
  `PrViewer` panel that renders the unified diff inline. Create-task
  form supports a "Bind to spec" autocomplete (role=architect only,
  sourced from the project's WIP spec registry) — the dispatcher
  picks the bound spec id up as `Design ID` so the architect lands a
  design that shares the spec's numeric id with `implements_specs`
  set. Lifecycle overrides (pause / resume / retry / skip / reject)
  and approve-merge land in the message thread for audit. One-click
  retry clones a terminal task into a fresh queued one.

- **Runs, gates, and approvals.** Pipeline-run detail renders a
  `RunTimeline` swim-lane (one lane per pipeline step, bars from
  `task_stage_runs`, sub-second tick on running bars) plus an inline
  `GateCard` for spec/design/plan approvals from inside the run view.
  When the close-cycle backstop stamps `wips_pending_merge`, RunDetail
  opens a two-column **Ship gate** (architect-drafted `merges[]` on the
  left, reviewer's `ship_attestation` on the right); approve POSTs the
  atomic `/knowledge/ship` commit. The Runs list sorts
  blocked-longest-first with a red `blocked Nm` badge.

- **Observability & admin controls.** Per-project Metrics page (daily
  cost sparkline, per-spec breakdown, per-role prompt-cache stats,
  per-tier model usage); fleet Regressions dashboard with acknowledge
  flow; per-project Auto-approval, Budget, and Auth-mode cards;
  Worker-concurrency strip (per-project queue depth + slot
  availability). Audit log viewer at `/admin/audit` and
  `/projects/:id/audit` (table + filters + correlation chip + before/
  after JSON expand). Admin-only surfaces (behind their own feature
  flags): tenant-isolation coverage, secret-rotation registry,
  escalations queue (ack / resolve), CI Fix Loop card on RunDetail.
  Reviewer security and performance count chips on reviewer-task
  details.

Cross-cutting affordances: a `⌘K` command palette mounted at the App
shell (fuzzy-ranked across projects, recent tasks, artifacts, runs,
and runnable actions), SSE-driven live updates for pipeline and
message events, typed API client (`src/api/client.ts`) shared across
views, per-feature `VITE_*_ENABLED` flags for hotfix rollback.

## Interfaces

- **Routes** (declared in `src/main.tsx`):
  - Fleet: `/`, `/freshness`, `/metrics/regressions`, `/admin/audit`,
    `/admin/secrets`, `/admin/isolation`, `/admin/escalations`.
  - Per-project: `/projects/:projectId` (+ `/freshness`, `/pipeline`,
    `/pipeline/:taskId`, `/metrics`, `/runs`, `/runs/:runId`,
    `/ship/:wipId`, `/audit`, `/escalations`, `/plans`,
    `/plans/:planId`, `/:type`, `/:type/:artifactId`).
- **Project sub-nav** (`ProjectNav.tsx`): Overview, Pipeline, Runs,
  Plans, Metrics, Freshness, Audit, Escalations.
- **`coder-core` consumers**: projects, knowledge (read + PUT + ship),
  tasks (create + override + retry + messages + pr + stage-runs),
  pipeline-runs (list + timeline + override), audit-events, freshness,
  budget, isolation, regressions, secrets, escalations. SSE event
  stream for `pipeline_run.changed`, `pipeline_run.gate_blocked`,
  `message_created`, and `knowledge_approved` / `_rejected`.
- **Frontend feature flags** (`VITE_*_ENABLED`): `AUDIT_LOG`,
  `SECRET_ROTATION`, `ISOLATION_VIEW`, `ESCALATIONS`, `AUTO_APPROVE`,
  `RUN_TIMELINE`, `PR_VIEWER`, `KNOWLEDGE_EDITOR`, `COMMAND_PALETTE`,
  `CI_FIX_LOOP`, `REVIEWER_FINDINGS`, `SPEC_COORDINATOR`. Default-on
  per feature unless noted; flip-off is a hotfix.

## Dependencies

- [multi-tenancy](../tenancy/multi-tenancy.md) — project listing and scoping.
- [knowledge-api](./knowledge-api.md) — all artifact reads, edits, and
  the `/knowledge/ship` atomic merge.
- [task-orchestration](../pipeline/task-orchestration.md) — task and pipeline
  endpoints, override path, SSE event bus.
- [audit-log](../tenancy/audit-log.md) — backing data for `/admin/audit` and
  per-project audit views; correlation-chip joins.
- GitHub (via `coder-core`) for the approve-merge action.

## Evolution

- 2026-04 — v0 SPA + knowledge browser + Mermaid + pipeline live
  tab + Google OAuth + JWT sessions + inline AC checkboxes.
- 2026-04-19 — pipeline-run dashboard week: RunTimeline, inline
  GateCard, PR diff viewer, inline knowledge editor, command palette,
  audit log viewer all shipped (specs 0026, 0033–0037).
- 2026-05 — ship-gate panel + spec-bound architect dispatch + ADR-
  collision and reviewer-findings chips (spec 0044, 0076, 0086, 0094).

## Links

- Designs: [system-overview](../../designs/active/system-overview.md)
- Related components: [multi-tenancy](../tenancy/multi-tenancy.md),
  [knowledge-api](./knowledge-api.md), [audit-log](../tenancy/audit-log.md),
  [escalations](../pipeline/escalations.md), [observability](../pipeline/observability.md),
  [task-orchestration](../pipeline/task-orchestration.md),
  [reviewer-worker](../workers/reviewer-worker.md)

---
id: "0026"
title: Pipeline run dashboard — live timeline + inline gates
type: spec
status: wip
owner: ro
created: 2026-04-17
updated: 2026-04-17
served_by_designs: ["0026"]
related_specs: [admin-panel, task-orchestration]
---

# Pipeline run dashboard — live timeline + inline gates

## Problem

The admin panel already has a Runs list
([`Runs.tsx`](../../designs/active/system-overview.md) entry) and a
per-run detail page (`RunDetail.tsx`) — both polling
`GET /v1/projects/{id}/pipeline-runs`. They work, but they don't
tell the operator what they actually want to know at a glance:

- **Where is this run right now, and for how long?** Current
  surface shows the `current_step` enum string. It doesn't surface
  which step is blocking, how long the step has been running, or
  how that compares to typical durations.
- **Which runs need me?** The list view is chronological; it
  doesn't sort by "runs blocked on a gate I could approve." An
  operator scanning the page sees nothing actionable.
- **Approve/reject without leaving the page.** Today the operator
  has to navigate into a spec-approval or design-approval modal
  from elsewhere — the run view knows a gate exists but has no
  button to clear it.
- **Fresh vs stale.** Both views poll every 3 s. That's wasted
  calls on idle runs, and stale on active ones. SSE already ships
  for task messages (spec 0015); pipeline-run transitions should
  ride the same feed.

Phase 5's admin-v2 vision (ROADMAP 0033) treats the pipeline view
as the thing you keep open all day. This spec is the Phase 3
foundation: make the run view live, make the gates actionable, and
surface blocking status as the primary list-view sort.

## Users / personas

- **Operator watching the fleet** — wants the Runs list sorted
  by "needs me now." A run blocked on a human gate for 5 min is
  more important than a run that's been running for 3 hours but
  is self-progressing.
- **Project owner investigating a slow run** — wants to see which
  step is slow and whether the slowdown is per-step typical or
  anomalous.
- **Phase 5 admin-v2 work (spec 0033)** — needs a live-timeline
  primitive it can reuse for the per-project pipeline dashboard.

## Goals

- **Live updates.** Pipeline-run row changes push via SSE (extend
  the existing feed) so the dashboard doesn't poll an idle run.
- **Timeline per run.** The detail view renders steps as a
  horizontal strip with per-step duration bars. Each step shows
  its status (waiting / running / done / blocked), its elapsed
  time, and a median-duration comparator so anomalies jump out.
- **Inline gates.** The detail view renders pending
  spec-approval / design-approval / plan-approval gates as an
  actionable card with Approve / Reject / Request-changes buttons
  wired to the existing endpoints. No modal navigation.
- **Sort-by-blocking.** The Runs list sorts by "blocked on
  human-gate, oldest first" by default, then by status. Idle /
  self-progressing runs sink to the bottom.
- **Auto-refresh at scale.** Per-run SSE opt-in; list view
  subscribes to a single "any run changed for this project"
  channel rather than per-row subscriptions.

## Non-goals

- **Cross-project runs view.** The dashboard stays project-scoped.
  A fleet-wide view is a Phase 5 admin-home concern (spec 0033).
- **Historical replay.** The dashboard is live-state + recent
  duration comparator. Deep historical replay goes through the
  `task_stage_runs` archive (spec 0024), not this dashboard.
- **Gate approval flows beyond spec / design / plan.** The
  existing three approve/reject endpoints are the surface; no new
  gate types.
- **Re-architecting the existing `PipelineRun` row.** Column
  additions are OK; the schema stays single-row-per-run.

## Scope

**In:**

- New column `pipeline_runs.blocked_since` (timestamptz, nullable)
  populated when a run transitions into a `*_approval` step and
  cleared on gate resolution. The "sort by blocking" list uses
  it directly (migration 0028).
- New column `pipeline_runs.step_started_at` (timestamptz,
  nullable) reset on every step transition. Enables the
  timeline's elapsed-time bar without a join through
  `task_stage_runs`.
- SSE extension: new event types `pipeline_run.changed` and
  `pipeline_run.gate_blocked` on the existing feed
  (`/v1/projects/{id}/sse`). Frontend subscribes once per project
  and dispatches to whichever component is mounted.
- Backend median-duration rollup: nightly job computes the
  per-step median duration over the last 7 days into a new
  `pipeline_step_stats` table (migration 0029). Admin reads it
  via `GET /v1/projects/{id}/ops/step-stats`; used as the
  comparator in the timeline.
- Admin `RunDetail` redesign:
  - Horizontal step strip with per-step duration bar + median
    overlay + status pill.
  - Gate card (when `blocked_since` is set) with Approve /
    Reject / Request-changes buttons wired to the existing
    spec / design / plan approval endpoints. The right endpoint
    is dispatched based on `current_step`.
  - "Last activity" chip showing the most recent SSE tick.
- Admin `Runs` (list) redesign:
  - Default sort: blocked-longest-first, then
    running-oldest-first, then terminal.
  - Each row shows the current step + elapsed time + blocked-gate
    badge.
  - SSE subscription replaces the 3-s poll.
- Runbook `runbooks/pipeline-run-blocked.md` — operator decision
  tree when a run sits on a gate for > 30 min.

**Out:**

- Per-project aggregated queue depth (that's 0028).
- Cross-project blocked-run alerts (future).
- Slack notifications on gate-blocked (adjacent work; out of v1
  scope).

## Acceptance criteria

- [ ] Migration 0028 adds `pipeline_runs.blocked_since TIMESTAMPTZ NULL`
      and `pipeline_runs.step_started_at TIMESTAMPTZ NULL`.
      `blocked_since` is set when a run enters a `*_approval` step
      and cleared on resolution; `step_started_at` is reset on
      every step transition.
- [ ] Migration 0029 adds `pipeline_step_stats (project_id,
      step, median_duration_seconds, sample_size, computed_at)`.
      A nightly Cloud Scheduler job populates it from the last
      7 days of `pipeline_runs` transitions.
- [ ] `GET /v1/projects/{id}/ops/step-stats` returns the table
      rows for this project, project-API-key auth.
- [ ] SSE events `pipeline_run.changed` (payload: the updated
      `PipelineRunRead`) and `pipeline_run.gate_blocked` (payload:
      `{run_id, step, blocked_since}`) fire on every
      `pipeline_runs` mutation. No new database work — publish
      fires from the same transaction that writes the row.
- [ ] Admin `RunDetail` renders a horizontal step strip with
      per-step duration bar + median overlay; the running step
      ticks every second from `step_started_at` without
      re-fetching. No more 3-s polling on the detail view.
- [ ] Admin `RunDetail` renders a Gate card when `blocked_since`
      is non-null, with Approve / Reject / Request-changes
      buttons that call the existing
      `POST .../knowledge/{specs|designs}/{id}/approve|reject`
      or `.../task-plans/{id}/approve|reject` endpoint based on
      `current_step`.
- [ ] Admin `Runs` list sorts by blocked-longest-first →
      running-oldest-first → terminal by default, with a
      column toggle to fall back to chronological. Each row
      shows current step, elapsed time, and a blocked badge
      when applicable.
- [ ] Runs list subscribes to a single project SSE channel and
      refreshes on `pipeline_run.changed` events instead of
      polling.
- [ ] Runbook `runbooks/pipeline-run-blocked.md` covers: opening
      a run from the blocked-runs sort, reading the gate card,
      deciding between approve / reject / request-changes,
      escalation path when the gate needs the PM worker rather
      than a human.
- [ ] Tests:
      - Unit: per-step-stats SQL rollup against a seeded run history.
      - Unit: timeline elapsed-time math (step_started_at +
        wall-clock tick).
      - Integration: gate approval from the detail view hits the
        right underlying endpoint.
      - Visual: RunDetail renders gate card when `blocked_since`
        is set; renders timeline with median overlay.

## Metrics

- **Primary:** median time a run spends in a `*_approval` step,
  per-project per-week. Target: < 15 min once the sort-by-blocking
  default + inline gate are live. Baseline unknown; the new
  columns enable the measurement.
- **Dashboard health:** SSE reconnect rate per open session.
  < 1 / hr is healthy; > 5 / hr means the gateway is dropping
  connections and polling fallback should kick in.
- **Anomaly catch-rate:** runs whose current step exceeds
  2× the 7-day median duration for that step per week. This is
  the signal the timeline median-overlay is designed to surface.

## Open questions

- **`step_started_at` accuracy across fix loops.** A task that
  bounces to `fixing` and back doesn't change `current_step` but
  arguably restarts the clock. First cut: `step_started_at`
  tracks step transitions only, not fix bounces. If operator
  feedback flags it as misleading, revisit.
- **Median or P75 as the comparator?** Median is less noisy but
  hides long-tail pain. Start with median + sample_size; the UI
  can expose a toggle later.
- **Reject semantics at the inline Gate card.** Reject without
  follow-up drops the run; reject with "request changes" spawns
  a revision task. The Phase 3 scope includes both paths; the
  button labels make the choice explicit.
- **SSE fan-out cost.** Every pipeline-run write fires two SSE
  events. At fleet scale (N projects × K open sessions), this
  multiplies. First cut fires unconditionally; if metrics show
  SSE-bus pressure, gate on "there's a subscriber for this
  project" (a subscriber-count check in the publisher).
- **Gate card for `plan_approval`.** The existing flow takes the
  operator into the Plan Detail page to edit the plan before
  approving. Should the inline Gate card expose inline plan
  editing, or keep the "edit in place" as a drill-in link? First
  cut: drill-in; inline editing is a Phase 5 concern (spec 0033
  / 0034).

## Links

- Related specs: [admin-panel](../active/admin-panel.md),
  [task-orchestration](../active/task-orchestration.md).
- Related ADRs: —.
- Adjacent roadmap: 0033 (Phase 5 — live pipeline timeline),
  0034 (in-panel diff & PR viewer), 0035 (inline knowledge
  editor). This spec is the Phase 3 foundation those Phase 5
  items build on.
- Roadmap: [ROADMAP.md](../ROADMAP.md) — Phase 3, item 0026.

---
id: fleet-patterns
title: Fleet pattern surfacing
type: spec
status: active
owner: ro
created: 2026-05-06
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: Surface recurring failure patterns across managed projects.
served_by_designs: []
related_specs: [knowledge-api, admin-panel, architect-worker, pm-worker, reviewer-worker, multi-tenancy, knowledge-freshness]
parent: knowledge-and-admin
---

# Fleet pattern surfacing

## What it is

A read-only fleet-scoped surface that makes structural patterns observable
across all Coder projects without relaxing per-project knowledge isolation.
An offline indexer computes five pattern groups daily — similar ADRs,
similar spec problems, recurring failure taxonomies, role-prompt impact
deltas, and template-drift candidates — and persists them for operator
browsing and optional worker consultation.

## Capabilities

- **Five pattern groups** computed daily by `coder-core-pattern-indexer`
  (Cloud Run Job, scheduled 03:00 UTC; also triggerable via
  `POST /v1/_admin/patterns/index/run`):
  - `adr` — ADRs whose title tokens (Jaccard ≥ 0.5) overlap across ≥ 2
    projects; members carry `(project_id, adr_id, adr_title, decision_pill)`
    where `decision_pill` is the ADR's `## Decision` first sentence (≤ 200
    chars). Does not expose the full ADR body cross-tenant.
  - `spec_problem` — specs whose `## Problem` first-paragraph tokens
    (Jaccard ≥ 0.4) overlap across projects; members carry
    `(project_id, spec_id, spec_title, problem_summary)`.
  - `failure_taxonomy` — `tasks.failure_kind` values recurring across ≥ 2
    projects in the last 30-day window; members carry
    `(project_id, failure_kind, count, last_seen_at)`.
  - `role_prompt_delta` — role-file edits with measurable accepted-rate
    movement (≥ 3 pp delta, sample_size_n ≥ 20, 3-day pre vs 7-day post
    window); admin responses include full diff hunks; worker-consult
    responses carry hash + line-count + delta number only (schema test is
    load-bearing — adding a future kind that exposes hunks to worker scope
    must fail it).
  - `template_drift` — frontmatter keys present in a project's local
    `_TEMPLATE.md` but absent from the central `coder-system` template;
    surfaces candidates for a 0047 migration.
- **Stable pattern IDs.** Each group has a deterministic first-appearance
  hash id; the indexer reuses an existing id when member-key Jaccard ≥ 0.6
  against the prior run's group. Citations in shipped ADRs stay resolvable
  across re-runs even when membership drifts.
- **Storage.** `pattern_groups` table (migration 0057):
  `id, kind, title, members JSONB, index_run_id, computed_at, score,
  sample_size_n`. `pattern_index_runs` (same migration):
  `id, started_at, completed_at, status, error_kind, error_detail,
  per_kind_counts JSONB`. Old rows from prior runs are retained for
  history; the default list endpoint returns only the latest run.
  `consultations` table (migration 0058): `id, project_id,
  requesting_task_id, topic, kinds_requested, pattern_ids_returned,
  consulted_at`. One row per consult endpoint call. Migration 0058 also
  adds `projects.fleet_patterns_index_opt_in` (boolean, default true) and
  `projects.fleet_patterns_enabled` (nullable boolean, NULL = inherit fleet
  default, tri-state).
- **`informed_by_patterns` frontmatter field.** Optional field added to
  `template/system/designs/_TEMPLATE.md`,
  `template/system/adrs/_TEMPLATE.md`, and
  `template/system/product-specs/_TEMPLATE.md` via a 0047 migration.
  Workers write the ids of any pattern groups they chose to cite. CI
  validator warns (not errors) if a cited id no longer resolves in the
  latest index run (patterns may have rotated out).
- **Indexer determinism.** A re-run on identical project snapshots and
  indexer code version produces identical `pattern_groups` rows (modulo
  `id` and `computed_at`).
- **Admin-scope endpoints** (admin token required):
  - `GET /v1/_admin/patterns?kinds=&min_projects=&since=` — paginated
    group list, latest run by default, filterable by kind / minimum
    project count / recency. Admin panel filters to groups active in the
    last 90 days by default (toggle to see all).
  - `GET /v1/_admin/patterns/{pattern_id}` — full group detail with
    members and `index_age_minutes`.
  - `GET /v1/_admin/patterns/index/runs[?limit=N]` — recent indexer runs
    with status and per-kind counts.
  - `POST /v1/_admin/patterns/index/run` — manual indexer trigger.
- **Worker consult endpoint** (project token or admin token):
  `GET /v1/projects/{id}/patterns/consult?topic=&kinds=&max_results=5` —
  returns ≤ `max_results` pattern groups (members reduced to
  `project_id, artifact_id, decision_pill_or_summary, pattern_id`). Writes
  one `consultations` row and one `audit_events` row
  (`action='pattern.consulted'`, `target_type='pattern_consultation'`,
  `target_id=<consultation row id>`) per call. Workers access via the
  impersonation broker; the broker attaches admin scope for the internal
  lookup without exposing it to the worker's token directly.
- **Rate cap.** Consult endpoint enforces a per-project cap
  (`patterns_consult_per_project_per_minute`, default 30); over-cap
  returns 429 with `Retry-After`.
- **Opt-out.** `projects.fleet_patterns_index_opt_in` (default true);
  opted-out projects' artifacts never enter pattern groups.
- **Feature flags.** Fleet-wide `CODER_FLEET_PATTERNS_ENABLED` (default
  off on first deploy). Per-project `projects.fleet_patterns_enabled`
  (NULL = inherit). Worker consultation gated on the per-worker setting
  AND both flags. Admin panel page gated on `VITE_FLEET_PATTERNS_ENABLED`.
- **Runbook.** `system/runbooks/fleet-patterns.md` documents: how each
  pattern kind is computed; how to read a group; how to disable a kind;
  how to interpret `role_prompt_delta` sample sizes; how to propose a
  template promotion from `template_drift`; the privacy boundary (no body
  content crosses tenant lines via worker consult).

## Interfaces

- `GET /v1/_admin/patterns?kinds=&min_projects=&since=`
- `GET /v1/_admin/patterns/{pattern_id}`
- `GET /v1/_admin/patterns/index/runs[?limit=N]`
- `POST /v1/_admin/patterns/index/run`
- `GET /v1/projects/{id}/patterns/consult?topic=&kinds=&max_results=`
- Tables: `pattern_groups`, `pattern_index_runs` (migration 0057);
  `consultations`, `projects.fleet_patterns_index_opt_in`,
  `projects.fleet_patterns_enabled` (migration 0058).

## Dependencies

- multi-tenancy — per-project scoping and isolation enforcement.
- impersonation — broker-scoped pass-through for worker consultations.
- knowledge-api — per-project knowledge snapshots consumed by the indexer.
- admin-panel — `/admin/patterns` browse surface.
- audit-log — `pattern.consulted` and indexer-run `audit_events` rows.

## Evolution

- 0048 — initial ship (2026-05-06). Five pattern kinds;
  `coder-core-pattern-indexer` Cloud Run Job (daily 03:00 UTC); admin +
  worker endpoints; `pattern_groups` / `pattern_index_runs` /
  `consultations` tables; `informed_by_patterns` frontmatter field;
  `CODER_FLEET_PATTERNS_ENABLED` fleet flag; per-project opt-in and
  fleet-enabled columns; architect worker consultation step (see
  [architect-worker](../workers/architect-worker.md)).

## Links

- Designs: [fleet-patterns](../../designs/wip/0048-cross-project-patterns.md)
- Related components: [knowledge-api](./knowledge-api.md),
  [admin-panel](./admin-panel.md),
  [architect-worker](../workers/architect-worker.md),
  [pm-worker](../workers/pm-worker.md),
  [reviewer-worker](../workers/reviewer-worker.md),
  [multi-tenancy](../tenancy/multi-tenancy.md),
  [knowledge-freshness](./knowledge-freshness.md)

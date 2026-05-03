---
id: '0048'
title: Cross-project pattern surfacing
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ['0048']
related_specs:
  - knowledge-api
  - admin-panel
  - architect-worker
  - pm-worker
  - team-manager-worker
  - reviewer-worker
  - developer-worker
  - multi-tenancy
  - knowledge-freshness
parent: knowledge-and-admin
---

# 0048 — Cross-project pattern surfacing

## Problem

Coder runs N projects, each with its own knowledge repo
(`coder-system/template/`-shaped, isolated by `project_id` per
the `multi-tenancy` spec). Today every project's knowledge is a
silo: an ADR landed in `coder` justifying "use Cloud Run Jobs +
Scheduler over Celery" cannot inform `vibetrade`'s architect
worker the next time it considers that decision; a recurring
failure mode in `vibetrade`'s pipeline cannot be surfaced as
"this has happened in 2 other projects too — here's what they
did"; a role-prompt tweak that improved `coder`'s reviewer
approval rate cannot be visible to other projects' operators.

The siloing is a deliberate isolation property — `multi-tenancy`
guarantees a tenant's knowledge is invisible to other tenants
through normal API paths, and `service-accounts` + `impersonation`
make it _enforced_, not just polite. We are not relaxing that.
But the operator persona spans projects: ops on call sees every
project, the human author of architectural decisions on
`coder` is the same person reviewing `vibetrade`'s. Today they
must hold the cross-project pattern map in their head, which
limits the size of the fleet they can usefully steward. With
0043 (freshness) + 0044 (write-through) keeping each project's
knowledge clean, the next leverage is making patterns _across_
projects observable to operators and (carefully) suggestable to
workers.

What's missing is a read-only fleet-scoped surface that
**operators can browse** ("show me ADRs across projects whose
titles or content are similar") and that **workers can opt in to
consult** at decision-relevant moments ("about to write an ADR —
what have other projects decided here?"), backed by an audit
trail showing how often a worker actually used a cross-project
hint and which one.

## Users

- **Architect worker** — primary worker consumer. When asked to
  draft a design that needs a non-obvious decision (anything
  that would warrant an ADR), it can call a new
  `GET /v1/_admin/patterns/adrs?topic=...` endpoint to see
  cross-project ADRs whose topic resembles the proposed
  decision. The worker decides whether to cite or ignore;
  citations are recorded in the new design's `informed_by_patterns`
  frontmatter so the trail is visible.
- **PM worker** — when drafting a spec, similar query against
  cross-project specs whose problem statement resembles the
  current draft. Same opt-in shape.
- **Reviewer worker** — when reviewing a developer task, can
  surface cross-project failure patterns that match the
  task's failure (if any). Read-only suggestion to operator on
  the verdict; doesn't change the verdict shape.
- **Operator (release manager / on-call)** — primary human
  consumer. The admin panel grows a `/admin/patterns` page that
  lists cross-project pattern groupings: similar ADRs, similar
  spec problems, recurring failure kinds, role-prompt diffs that
  produced measurable approval-rate deltas.
- **Schema author** (0047) — sees cross-project drift signals
  on the `/admin/patterns/template-drift` view, which surfaces
  fields that one project added locally to its `_TEMPLATE.md`
  but the central template doesn't have — candidates for
  promotion to the central template via 0047 migration.

## Goals

- **Surface, don't auto-apply.** Every output of 0048 is
  observable suggestion, never automatic action. A worker
  consulting the patterns endpoint receives a list; it does
  not retrieve ready-to-paste content. An ADR on project A
  never lands content from project B's ADR without a human
  having moved the words across.
- **Read-only fleet surface, isolation preserved.** The new
  endpoints are admin-scoped (`_admin/patterns/...`) and use
  the existing fleet auth (admin token, not project token).
  Project-scoped tokens cannot reach this surface. A project's
  workers consult the surface via the impersonation broker's
  existing project-token path; the broker, not the worker,
  attaches the admin scope on outbound for this specific
  endpoint set, and audit-logs each consultation. (See the
  design for the broker change.)
- **Five pattern groups, each surfaced through one endpoint.**
  v1 ships with a small fixed list — ADRs, spec problems,
  recurring failure taxonomies, role-prompt diff impact, and
  template drift. v2+ may grow. Each group is computed by an
  offline indexer; nothing here runs at every request.
- **Workers' use is opt-in, audited, and decision-trail-
  visible.** A worker that consulted patterns annotates the
  artifact it produced with `informed_by_patterns: [pattern_id, ...]`
  in frontmatter, and the consultation itself writes an
  `audit_events` row. Operators can answer "did the worker
  consult patterns before writing this?" by reading either.
- **Indexer cadence is daily, not live.** The patterns surface
  is an index over knowledge + audit + outcomes; computing it
  per-request would be expensive. A daily Cloud Run Job
  computes pattern groupings and persists them. Stale-pattern
  risk is acceptable for the persona (operators browsing
  weekly, workers consulting at gate-decision time) but is
  marked: every endpoint response carries
  `index_age_minutes`.

## Non-goals

- **Cross-project _writes_.** Nothing here writes into a
  project's knowledge repo. A worker can cite a pattern in its
  output frontmatter, but the citation is just a string id
  pointing at the pattern's stable name in the index — not a
  copy of another project's content.
- **Semantic similarity across projects' bodies.** v1's
  similarity is structural + frontmatter-based (e.g. ADRs
  whose titles tokenise similarly, specs whose `## Problem`
  first-paragraph tokens overlap, failure-kinds equal). No
  embedding store, no LLM-as-similarity. ADR 0014 already
  rejected semantic similarity as the basis for freshness;
  the same reasoning applies — it's expensive, opaque, and
  the structural signal is the cheap-and-honest first cut.
- **Auto-promoting a pattern to the central template.** The
  template-drift view _surfaces_ candidates; promoting one to
  the central template is a 0047 migration the operator
  authors. No auto-PR.
- **Cross-tenant data leakage.** The patterns surface is
  available only via admin-scope endpoints and via the broker-
  attached scope for worker consultations. A worker call to
  the patterns endpoint never returns _content_ from another
  project — only structural metadata + a stable pattern id +
  the (already-public-within-the-fleet) project-id list of
  origins. To read another project's actual content, the
  operator clicks through and reads it directly with their
  own admin scope, in the admin panel — not by way of a
  worker's response. (See design for exact response shapes.)
- **Cross-project comparison of secrets, audit content,
  costs.** Strictly knowledge-repo + worker outcomes
  metadata. Cross-tenant cost / spend comparison is 0031's
  surface and stays there.
- **Replacing 0046's graph retrieval.** 0046 is intra-project
  graph; 0048 is inter-project pattern. They do not overlap;
  workers can use both in the same task.

## Scope

### In scope — the five pattern groups (v1)

Each pattern group is computed by an indexer pass and
persisted to a `pattern_groups` table (migration 0057). Each
group has a stable id (`adr-cloudrun-vs-celery-2026-q2`),
a `kind` (`adr | spec_problem | failure_taxonomy |
role_prompt_delta | template_drift`), and a `members[]` list
referencing per-project artifacts.

1. **`adr`** — ADRs whose title tokens (case-folded, stop-
   word-removed) overlap above a similarity threshold across
   ≥ 2 projects. Members carry `(project_id, adr_id,
   adr_title, decision_pill)` where `decision_pill` is the
   ADR's `## Decision` first sentence (truncated to 200
   chars). Surfaces "this question was answered in 2 other
   places" without exposing the full ADR content.

2. **`spec_problem`** — specs whose `## Problem` first
   paragraph tokens overlap across projects. Members carry
   `(project_id, spec_id, spec_title, problem_summary)`.
   Surfaces "this problem has been written about elsewhere"
   to the PM worker drafting a similar spec.

3. **`failure_taxonomy`** — `tasks.failure_kind` values
   recurring across projects with a count threshold per
   30-day window. Members carry
   `(project_id, failure_kind, count, last_seen_at)`. Helps
   the reviewer or operator see "this failure-kind has shown
   up in N projects this month — is it a fleet pattern?"
   Distinct from a 0032 cost-regression alert (that's per-
   project temporal); this is per-`failure_kind` cross-
   project structural.

4. **`role_prompt_delta`** — when a project edits a worker
   role's prompt (these live in `roles/` per the
   `knowledge-repo-model`), the indexer pairs the diff with
   the project's _subsequent_ approval-rate / failure-rate
   movement (3 day window pre vs 7 days post). Surfaces
   "project A edited the reviewer prompt and approval-rate
   went +6 pp" — a candidate other projects might want to
   adopt. Member shape: `(project_id, role_id, diff_summary,
   approval_rate_delta_pp, sample_size_n)`.

5. **`template_drift`** — fields present in one project's
   `system/<artifact_type>/_TEMPLATE.md` that are absent from
   the central `coder-system/template/system/<...>/_TEMPLATE.md`.
   These are local additions a project found useful that
   never made it into the central template. Member shape:
   `(project_id, artifact_type, field_name,
   first_seen_in_artifact)`. Feeds the schema author's
   "promote to template via 0047 migration" decision.

### In scope — endpoints

All under `/v1/_admin/patterns/` (admin scope only):

- `GET /v1/_admin/patterns?kinds=adr,spec_problem&min_projects=2&since=30d`
  — paginated list of pattern groups, latest first by
  `index_run.computed_at`. Filter by kind, minimum project
  count, recency.
- `GET /v1/_admin/patterns/{pattern_id}` — one group's full
  detail with members + `index_age_minutes`.
- `GET /v1/_admin/patterns/index/runs[?limit=N]` — recent
  indexer runs with status and what they computed.
- `POST /v1/_admin/patterns/index/run` — manual trigger of
  the indexer (admin token).

For workers (broker-scoped pass-through):
- `GET /v1/projects/{id}/patterns/consult?topic=<short string>&kinds=adr,spec_problem&max_results=5`
  — the worker's consultation surface. Internally, the
  endpoint runs a token-overlap match against the index
  using the supplied `topic` (the worker passes its decision
  shorthand, e.g. "background job runner choice"), filters by
  the requested kinds, and returns up to `max_results`
  pattern groups with members reduced to
  `(project_id, artifact_id, decision_pill_or_summary,
  pattern_id)`. This endpoint **writes a `consultations`
  table row** (migration 0058) per call:
  `(project_id, requesting_task_id, topic, kinds_requested,
  pattern_ids_returned, consulted_at)`. The trail of "did
  this worker consult patterns?" lives here.

### In scope — `informed_by_patterns` frontmatter

Designs and ADRs (and specs in PM-draft mode) gain an
optional frontmatter field
`informed_by_patterns: [pattern_id, ...]`. The worker writes
this when it consulted the patterns endpoint and chose to
cite one or more groups in shaping its output. This makes the
trail readable in the artifact itself, not just in the
consultations table — a reviewer reading the design later can
see "this design cites pattern X" and click through to view
the cross-project members.

The field is added to the relevant `_TEMPLATE.md` files (a
0047 migration ships the change to managed projects). v1
treats the field as informational — the validator confirms
each id resolves against the indexer's persisted set, but
doesn't enforce its presence.

### In scope — admin panel `/admin/patterns`

Page lists the latest indexer run's pattern groups, filterable
by kind, sortable by member-project count, with one row per
group:
- Group title (e.g. "ADR: background job runner choice (3
  projects)").
- Member chips per project, click-through to the project's
  artifact view.
- A "How is this scored?" link to the runbook explaining the
  similarity heuristic.
- For `role_prompt_delta`: the approval-rate delta as a
  signed pp value with sample size, hover for the diff.
- For `template_drift`: a "Propose template promotion"
  button that opens a pre-filled migration scaffold
  (0047 territory; 0048 produces the scaffold, the operator
  reviews + ships).

Behind `VITE_FLEET_PATTERNS_ENABLED`.

### In scope — the indexer

A new Cloud Run Job `coder-core-pattern-indexer` (oneshot,
also scheduled daily at 03:00 UTC):

- Fetches the latest knowledge snapshot per project (one
  graph fetch per project rooted at the registry — shared
  with 0046's graph endpoint where applicable).
- Per pattern kind, runs the kind-specific computation:
  - `adr`: token-bag intersection on titles, threshold ≥ 0.5
    Jaccard.
  - `spec_problem`: token-bag intersection on first
    `## Problem` paragraph, threshold ≥ 0.4 Jaccard
    (specs are usually longer, looser threshold).
  - `failure_taxonomy`: SQL aggregate on `tasks.failure_kind`
    over the last 30 days, group on `failure_kind`, keep
    where `count_distinct(project_id) ≥ 2`.
  - `role_prompt_delta`: per role file, find each project's
    latest commit touching the file in the last 30 days;
    compute the project's `tasks.status='accepted'`-rate
    over (3 day window before commit, 7 day window after
    commit); keep deltas with `|delta_pp| ≥ 3` and
    `sample_size_n ≥ 20`.
  - `template_drift`: parse each project's
    `system/<type>/_TEMPLATE.md`, compare frontmatter keys
    against `coder-system/template/system/<type>/_TEMPLATE.md`,
    emit groups for keys present in 1+ project but absent
    centrally.
- Writes `pattern_groups` (migration 0057) rows with the
  current `index_run_id` (also migration 0057, separate
  table). Old rows from prior `index_run_id`s are kept for
  historical viewing but the default `GET /patterns` returns
  only the latest run.
- One `audit_events` row per indexer run
  (`action='pattern_index.completed' | '.failed'`) carrying
  the row counts per kind in the detail.

### Out of scope

- **Embedding-based similarity** — see non-goals. Out of v1.
- **Auto-citing patterns from worker output** — workers
  cite by writing `informed_by_patterns` in frontmatter; the
  output schema isn't extended to require it. Pure opt-in.
- **Surfacing patterns _during_ a worker's claude spawn** —
  workers consult before spawning (in their pre-claude
  context assembly). No mid-spawn callback.
- **Project-A → project-B notifications** ("project A just
  decided X, FYI"). A daily indexer run + a browseable page
  is the v1 push surface.
- **Suggesting code patterns from one project's code repo to
  another's**. Knowledge-repo only.

## Acceptance criteria

- **AC1.** `pattern_groups` table (migration 0057) exists with
  columns `id, kind, title, members JSONB, index_run_id,
  computed_at, score, sample_size_n`. Companion
  `pattern_index_runs` (same migration): `id, started_at,
  completed_at, status, error_kind, error_detail,
  per_kind_counts JSONB`.

- **AC2.** Cloud Run Job `coder-core-pattern-indexer` exists,
  scheduled daily at 03:00 UTC, also invokable via
  `POST /v1/_admin/patterns/index/run`. Runs the five pattern
  kinds, writes rows under one new `pattern_index_runs.id`,
  emits one `audit_events` row at completion.

- **AC3.** Endpoints exist:
  `GET /v1/_admin/patterns?kinds=&min_projects=&since=`,
  `GET /v1/_admin/patterns/{id}`,
  `GET /v1/_admin/patterns/index/runs`,
  `POST /v1/_admin/patterns/index/run`,
  `GET /v1/projects/{id}/patterns/consult?topic=&kinds=&max_results=`.
  Admin endpoints require admin token; the per-project
  consult endpoint requires either project token or admin
  token; both paths log to `consultations`.

- **AC4.** `consultations` table (migration 0058):
  `id, project_id, requesting_task_id, topic, kinds_requested,
  pattern_ids_returned, consulted_at`. One row per consult
  endpoint call.

- **AC5.** `informed_by_patterns: [pattern_id]` is added to
  `template/system/designs/_TEMPLATE.md`,
  `template/system/adrs/_TEMPLATE.md`,
  `template/system/product-specs/_TEMPLATE.md` (as optional
  frontmatter). The CI validator checks each id resolves
  against `pattern_groups`; missing → warning, not error
  (patterns may have rotated out of the latest run).

- **AC6.** The five pattern kinds compute deterministically
  given (project snapshots, indexer code version): a
  re-run on the same input produces identical
  `pattern_groups` rows (modulo `id` and `computed_at`).

- **AC7.** The consult endpoint enforces a per-project rate
  cap (`patterns_consult_per_project_per_minute`, default 30)
  to prevent runaway worker loops. Over-cap → 429 with
  `Retry-After`.

- **AC8.** Admin `/admin/patterns` page renders the latest
  indexer run's groups behind `VITE_FLEET_PATTERNS_ENABLED`,
  filterable by kind, sortable by member count.
  `template_drift` rows have a "Propose template promotion"
  button that opens a pre-filled 0047 migration scaffold
  (ALLOW_BATCHING, the operation, the affecting types).

- **AC9.** Audit: every consult endpoint call writes an
  `audit_events` row (`action='pattern.consulted'`,
  `target_type='pattern_consultation'`,
  `target_id=<consultation row id>`). Indexer runs + admin
  endpoint hits already covered via existing audit
  middleware.

- **AC10.** Architect worker's pre-claude assembly gains a
  consultation step (gated on `settings.architect_pattern_consult_enabled`,
  default false): if the task's spec frontmatter implies an
  ADR-warranting decision (presence of `decided_by` request
  or a `## Open questions` section asking for one), the
  worker calls `/patterns/consult?kinds=adr&topic=<derived>`
  and includes returned pattern groups as a `# Cross-project
  precedent` block in its prompt context. Output's
  `informed_by_patterns` frontmatter lists any pattern_ids
  the worker chose to cite. Same opt-in shape ships for PM
  and Reviewer in subsequent phases (ACs deferred).

- **AC11.** Flag-gated fleet-wide on
  `CODER_FLEET_PATTERNS_ENABLED` (default off on first
  deploy). Per-project escape hatch
  `projects.fleet_patterns_enabled` (NULL = inherit, tri-state).
  Worker consultation gated on the per-worker setting AND
  the fleet/project flag.

- **AC12.** Runbook `system/runbooks/fleet-patterns.md`
  documents: how the five pattern kinds are computed; how to
  read a pattern group; how to disable a pattern kind
  (config); how to interpret a `role_prompt_delta` (sample
  size matters); how to propose a template promotion from
  template_drift; the privacy boundary (no body content
  crosses tenant lines via worker consult).

## Metrics

- **Pattern coverage** — count of `pattern_groups` rows per
  kind per indexer run. Tracks how much overlap the fleet
  surfaces. Target: ≥ 5 ADR groups + ≥ 3 spec_problem groups
  by month 2 (with two managed projects, more once the fleet
  grows).
- **Worker consultation rate** — count of `consultations`
  rows per project per week. Headline KPI for adoption: are
  workers actually consulting before deciding? Target: ≥ 30%
  of architect tasks producing an ADR call the consult
  endpoint at least once.
- **Citation rate** — fraction of worker outputs whose
  `informed_by_patterns` frontmatter is non-empty among the
  outputs whose task's `consultations` row returned ≥ 1
  pattern. Tracks worker behaviour: when shown patterns,
  how often does it cite? Low (< 10%) means the worker
  consults but rarely finds the patterns useful — investigate
  prompt + similarity threshold.
- **Operator browse rate** — count of distinct admins loading
  `/admin/patterns` per week. Soft signal for whether the
  surface is delivering operator value.
- **Template-drift → 0047-migration promotion lag** — time
  from a `template_drift` group first appearing on the index
  to the operator authoring the corresponding 0047 migration
  (or explicitly dismissing). Watches the schema-evolution
  feedback loop.
- **Indexer wall-clock + spend** — per-indexer-run wall
  clock + token cost (the role_prompt_delta computation
  doesn't use the model; the others might in v2). Target:
  < 10 min per run at the current fleet size.

## Decisions

Resolved 2026-04-27 ahead of architect dispatch.

- **Similarity threshold tuning — runbook documents the
  tuning loop.** With fleet=2, the 0.5/0.4 Jaccard floors are
  hand-eyeballed. The runbook (new, alongside the indexer
  ship) specifies: spot-check 20 groups per run, label
  false-positives and false-negatives, adjust thresholds in a
  small reviewable PR carrying the labelling data. Repeat at
  every fleet-size milestone (3, 4, 8 projects) until the
  detector stabilises.
- **`failure_taxonomy` to architect — v1 narrow,
  `kinds=adr` only.** Architect's pre-claude consult ships
  with ADR patterns only. Failure-taxonomy to architect
  expands once Stage 3 data shows non-trivial architect
  citation rate on the ADR surface. Endpoint shape supports
  the additional kind from day 1; the architect prompt change
  is the deferred bit.
- **`role_prompt_delta` privacy — hunks for admin, hash+lines
  for worker.** The indexer materialises `diff_summary` with
  full hunks. Admin-scope responses include hunks; the
  worker-consult response model strips to hash + line count
  via Pydantic field exclusion. **Schema test enforces** that
  worker-scope consult on `kinds=role_prompt_delta` (if ever
  added) returns only hash + delta number. The schema test is
  load-bearing — adding a future kind that exposes hunks to
  worker scope must fail this test.
- **Stable `pattern_id` — sticky on first appearance with
  member-overlap matching.** Indexer's prior-run match pass
  reuses an existing `pattern_id` when member-key Jaccard ≥
  0.6 against the prior group; otherwise assigns a new id from
  a deterministic first-appearance hash. Stability over time
  is the load-bearing property — `informed_by_patterns`
  citations in shipped ADRs stay resolvable across indexer
  re-runs even when membership drifts.
- **Per-tenant opt-out — `projects.fleet_patterns_index_opt_in`,
  default true.** Ship for completeness even without a
  requesting tenant. The indexer's per-project fetch step
  respects the flag; opted-out projects' artifacts never
  enter the pattern groups. Migration 0058 adds the column.
- **Aging out old patterns — admin page filters to active in
  last 90 days by default.** With a toggle to see all.
  `pattern_groups` rows are kept regardless for history; the
  filter is purely UI. Default chosen to surface recently-
  relevant patterns and demote stale matches that no project
  has cited or revisited.

## Open questions

_None — all resolved. See Decisions above._

## Links

- Related specs:
  [knowledge-api](../active/knowledge-api.md),
  [admin-panel](../active/admin-panel.md),
  [architect-worker](../active/architect-worker.md),
  [pm-worker](../active/pm-worker.md),
  [team-manager-worker](../active/team-manager-worker.md),
  [reviewer-worker](../active/reviewer-worker.md),
  [developer-worker](../active/developer-worker.md),
  [multi-tenancy](../active/multi-tenancy.md),
  [knowledge-freshness](../active/knowledge-freshness.md)
- Design: [0048](../../designs/wip/0048-cross-project-patterns.md)
- Roadmap entry: [ROADMAP.md](../ROADMAP.md) → Phase 8 / 0048

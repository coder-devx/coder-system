---
id: "0043"
title: Knowledge freshness signals
type: design
status: wip
owner: ro
created: 2026-04-17
updated: 2026-04-17
last_verified_at: 2026-04-17
implements_specs: ["0043"]
decided_by: ["0014"]
related_designs: [knowledge-repo-model, knowledge-write-api, architect-worker, observability-and-cost-tracking]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin, coder-system]
---

# Knowledge freshness signals

## Context

The knowledge repo is structured ([knowledge-repo-model](../active/knowledge-repo-model.md)),
schema-validated ([ADR 0008](../../adrs/0008-ci-validation-of-knowledge-repo.md)),
and atomically written ([knowledge-write-api](../active/knowledge-write-api.md)).
None of that tells a reader whether an artifact still reflects reality.
A design describing `task-orchestration` may describe the shape of two
releases ago; the Knowledge API serves it unchanged; the Architect
worker plans against it. Integrity and freshness are different
properties — CI catches the first, nothing catches the second.

Spec 0043 asks for an inspectable freshness signal: a per-artifact
score, a read-time flag on the Knowledge API, an audit loop that
re-verifies the most stale artifacts, and an admin-panel surface. The
score must be derivable from fields artifacts already declare —
`affects_services`, `affects_repos`, cross-links — not from semantic
comparison of prose against code (see [ADR 0014](../../adrs/0014-freshness-from-declared-affects.md)).

Freshness is signalling only. It is distinct from spec 0044
(write-through enforcement): 0044 prevents one specific cause of rot
at ship time; 0043 surfaces ambient rot regardless of cause.

## Goals / non-goals

- **Goals**
  - Every artifact carries `last_verified_at` (required) and
    `verified_by` (optional); CI enforces both.
  - A deterministic `freshness_score ∈ [0, 100]` derived from three
    inputs: verify-age, declared-target activity, dependency rot.
  - Read-time integration: every Knowledge API envelope includes a
    `freshness` block; callers may demand `min_freshness=N` and
    receive `409 STALE` (with the artifact still in body) when below
    threshold.
  - A write-time attestation endpoint (`POST .../verify`) bumps
    `last_verified_at` and records `verified_by` in one commit.
  - A nightly per-project audit job that picks the N lowest-freshness
    artifacts, dispatches a `knowledge-audit` task to the Architect
    worker, and acts on a three-outcome verdict.
  - Admin panel shows freshness as badge + column, with a
    "Needs attention" widget for needs-rewrite reports.
- **Non-goals**
  - Sub-artifact (per-section) freshness. Artifact-level is the unit.
  - Real-time tripwires on target-code commits — derivation at read
    time and on the nightly audit is enough.
  - Semantic similarity between doc and code (see ADR 0014).
  - Automating the rewrite itself. The audit loop flags and dispatches;
    the rewrite is a separate task a human approves.

## Design

```mermaid
flowchart TB
  subgraph write [Write paths]
    create[POST knowledge/{type}<br/>sets last_verified_at = today] --> commit1[(commit)]
    verify[POST .../verify<br/>bumps last_verified_at] --> commit2[(commit)]
    edit[PUT knowledge/{type}/{id}<br/>body change clears last_verified_at<br/>to force re-attestation] --> commit3[(commit)]
  end

  subgraph read [Read path]
    get[GET knowledge/{type}/{id}<br/>?min_freshness=N] --> svc
    svc[FreshnessService.score] -->|score >= N| ok[200 with freshness block]
    svc -->|score < N| stale[409 STALE with body + freshness block]
  end

  subgraph score [FreshnessService.score]
    age[age since last_verified_at] --> weight[weighted sum<br/>0.3 age + 0.5 activity + 0.2 deps]
    activity[activity in affects_* since verify] --> weight
    deps[min freshness of depends_on / related_*] --> weight
    weight --> out[score in 0..100]
  end

  subgraph audit [Nightly audit job per project]
    pick[pick 5 lowest-freshness<br/>above staleness floor] --> task[create knowledge-audit task]
    task --> arch[Architect worker]
    arch -->|verified| callverify[call .../verify]
    arch -->|needs_rewrite| report[file needs-rewrite report]
    arch -->|uncertain| queue[queue for human triage]
  end

  write -.- read
  read -.- score
  audit -.-> write
```

### Parts

- **Frontmatter schema change** (one repo-wide migration)
  - `_TEMPLATE.md` for each artifact type under `system/` and
    `template/` gains required `last_verified_at: YYYY-MM-DD` and
    optional `verified_by: <actor-slug>`.
  - Applies to specs, designs, services, repos, roles, integrations,
    runbooks. **Excluded:** ADRs (append-only; freshness is binary —
    superseded or not), `glossary.md` (atemporal), generated
    `REGISTRY.md` files.
  - `scripts/validate.py` extended: required field, parseable ISO
    date, `<= today`. See ADR 0008 — this is an additive check.
  - One-shot back-fill migration `scripts/backfill_last_verified.py`:
    for any artifact missing the field, sets it to the file's latest
    git commit date (`git log -1 --format=%cs -- <path>`). Opens one
    PR per project, reviewed before merge.

- **`FreshnessService`** (new module in `coder-core`)
  - `freshness/service.py`. Pure computation given an `Artifact` and
    the project's git + registry state.
  - `score(artifact) -> FreshnessScore` returns
    `{score: int, last_verified_at, reasons: [(kind, detail)]}`
    where `kind ∈ {age, activity, dependency}` and `detail` is the
    specific signal that pulled the score down.
  - `freshness/weights.py` — a single config block, default
    `age=0.3, activity=0.5, deps=0.2`. Revisitable; weights are a
    deployment-time setting, not per-project.
  - `freshness/activity.py` — reads the project's repo HEAD and counts
    commits touching any declared `affects_services` / `affects_repos`
    path since `last_verified_at`. Uses the same GitHub client as the
    Knowledge API.
  - `freshness/deps.py` — transitive walk over cross-link fields
    (`depends_on`, `related_designs`, `implements_specs`,
    `served_by_designs`). Dependency score is the `min` across the
    set, not the mean — one rotten dependency poisons the lookup.
    Cycle-safe (visited set).

- **Knowledge API read envelope** (extends `knowledge-write-api` design)
  - `GET /v1/projects/{id}/knowledge/{type}/{artifact_id}` response
    gains top-level `freshness: {score, last_verified_at, reasons}`.
  - Query param `?min_freshness=N` (integer 0–100). Below-threshold
    reads return `409 STALE` with the full body plus the `freshness`
    block — the caller decides whether to use it. Backwards-compatible:
    absent param → no threshold check, 200 as before.
  - List endpoints (`GET /v1/projects/{id}/knowledge/{type}`) include
    a `freshness.score` per entry but not the reasons (too heavy).

- **Verify endpoint**
  - `POST /v1/projects/{id}/knowledge/{type}/{artifact_id}/verify`
    body: `{summary: string, verified_by?: actor-slug}`. Bumps
    `last_verified_at` to today, writes `verified_by` (defaults to
    the authenticated actor), and commits with
    `knowledge(verify): {type}/{id} — {summary}` — same commit
    formatter as the Write API.
  - 404 if the artifact doesn't exist; 409 on concurrent edit
    (SHA conflict, same contract as the Write API).
  - Does **not** edit the body. A verification that requires body
    changes uses `PUT` + the next-day `verify`, or (preferred) ends
    with a body-rewrite and a fresh `last_verified_at` = today
    written as part of the `PUT`.

- **Body-change invalidates verification**
  - `PUT /v1/projects/{id}/knowledge/{type}/{artifact_id}` — when the
    body changes, the handler clears `last_verified_at` to today only
    if the caller also sets `verified_by`; otherwise **clears the field
    to the previous date** and tags `reasons` with `body_changed`
    until a new `verify`. This prevents silent "edited without
    re-attestation" drift.
  - Frontmatter-only edits (e.g. updating `affects_services`) do not
    clear `last_verified_at` — they may, however, change what
    `activity` counts.

- **Nightly audit job**
  - Cloud Scheduler triggers `coder-core`'s
    `/internal/jobs/knowledge-audit/{project_id}` once per project
    per 24 h, staggered to avoid concurrent GitHub reads.
  - Handler: list all artifacts for the project, compute scores,
    filter by `score < staleness_floor` (default 60, per-project
    override), pick the bottom 5 by score, dispatch one
    `knowledge-audit` task per artifact via `task-orchestration`.
  - Architect worker's task prompt includes the artifact, its declared
    `affects_*` targets, and the git log of commits to those targets
    since `last_verified_at`. The worker's output schema
    (under spec 0025's umbrella) has three outcomes:

    ```json
    {"decision": "verified", "summary": "<one-line reason>"}
    {"decision": "needs_rewrite", "gaps": ["<specific issue>", ...]}
    {"decision": "uncertain", "questions": ["<what's unclear>", ...]}
    ```
  - Post-worker dispatcher logic: `verified` calls `.../verify` and
    closes the task; `needs_rewrite` and `uncertain` open a
    structured audit record in a new `knowledge_audit_reports` table
    surfaced in the admin panel.

- **Admin panel surface** (`coder-admin`)
  - List views (specs, designs, services, repos, roles, integrations,
    runbooks) gain a **Freshness** column: coloured pill with the
    score — green ≥ 80, yellow 60–79, red < 60. Sortable.
  - Detail view: freshness badge at the top with a popover showing
    the three `reasons` values (age days, activity commits, deps min).
  - New left-nav entry **Needs attention** listing the
    `knowledge_audit_reports` with `decision ∈ {needs_rewrite, uncertain}`,
    sorted by most-recent. Each row links to the artifact and the
    audit task that produced it. Dismiss / "mark triaged" sets a flag;
    it does not edit the artifact.
  - Filter chip **Stale only** (threshold configurable) on every
    list view.

- **Observability** (extends [observability-and-cost-tracking](../active/observability-and-cost-tracking.md))
  - Structured log events (ride the existing feed; no Prometheus
    scrape — see design 0018):
    - `knowledge_freshness_read` — per read, `{project_id, type, id, score, min_freshness_requested, returned_stale: bool}`.
    - `knowledge_freshness_audit` — per audit outcome, `{project_id, type, id, decision, score_at_audit}`.
    - `knowledge_freshness_verify` — per `.../verify` call, `{project_id, type, id, actor, summary}`.
  - One nightly job computes fleet aggregates (median, quartiles,
    per-type breakdown) and emits a
    `knowledge_freshness_summary` event for the weekly report.

- **Runbook** `runbooks/knowledge-freshness-audit.md` — the weekly
  human pass: where to find the `Needs attention` queue, what
  `needs_rewrite` vs `uncertain` imply, how to convert a rewrite
  report into a WIP-rewrite task via the PM worker.

### Data flow

**Happy read with threshold.**

1. Worker calls `GET /v1/projects/{id}/knowledge/design/architect-worker?min_freshness=70`.
2. Handler loads artifact, reads its `last_verified_at`, and asks
   `FreshnessService.score(artifact)`.
3. `FreshnessService` computes three terms:
   - `age_term = max(0, 100 - days_since_verify * 1.5)` (clamped).
   - `activity_term = max(0, 100 - commits_to_affects_since_verify * 5)`.
   - `deps_term = min(score(d) for d in transitive_deps)` or `100` if
     no deps.
   - Weighted sum, clamped to `[0, 100]`, rounded.
4. Score 82 ≥ threshold 70 → return `200` with body + `freshness: {score: 82, last_verified_at: 2026-04-10, reasons: [(age, "7d"), (activity, "1 commit to coder-core"), (dependency, "min 95 via worker-communication")]}`.

**Stale read.**

1. Same call, but score is 54.
2. `409 STALE` with the same body + `freshness` block.
3. Caller either: (a) treats as a hard failure, (b) logs and retries
   with a lower threshold, or (c) uses the body anyway — their choice.

**Audit loop.**

1. Scheduler triggers nightly audit for project P.
2. Handler picks 5 lowest-score artifacts above the floor, dispatches
   5 `knowledge-audit` tasks.
3. Architect worker runs each task; output JSON goes through the 0025
   schema gate.
4. `verified` → `.../verify` commit, score resets to ~100.
5. `needs_rewrite` / `uncertain` → audit report row, admin surface.

**Body change without verify.**

1. Operator edits an artifact via `PUT` without setting `verified_by`.
2. Handler keeps the old `last_verified_at` but adds a
   `body_changed_since_verify: true` frontmatter flag.
3. `FreshnessService` adds a synthetic `(integrity, "body changed since last verify")` reason and caps `age_term` at 40 until the next `verify` clears the flag.

### Invariants

- Every read endpoint either returns a `freshness` block with a score
  or fails with 5xx. No path returns an artifact body without a score.
- `last_verified_at` is monotonic per artifact: it only moves forward
  through a `PUT` (with `verified_by`) or a `.../verify` call. A
  `PUT` without attestation does not move it.
- Score computation is deterministic given (artifact, repo HEAD,
  registry snapshot, weights). Two calls at the same HEAD return the
  same score.
- ADRs are exempt: they have no `last_verified_at`, their envelope
  includes `freshness: {score: null, reason: "adr_exempt"}` so the
  client renders a neutral indicator rather than a red "stale" pill.
- The audit dispatcher never opens > 5 tasks per project per night.
  Hard cap; if the queue is bigger, the tail waits for tomorrow.

### Edge cases

- **Artifact with no `affects_*` fields.** `activity_term` defaults to
  100 (no evidence of rot), and a synthetic reason
  `(activity, "no affects_ declared — cannot detect target drift")`
  appears so the operator can see the gap. Back-fill surfaces these
  for triage.
- **Dependency cycle.** The walker uses a visited set; each node's
  contribution is its own age+activity terms only (cycle breaks the
  deps recursion at the revisit).
- **Artifact with a future `last_verified_at`.** Rejected at validate
  time and at write time. `FreshnessService` never sees it.
- **Very old artifact with low activity.** Age term dominates; score
  drops. This is correct: even a quiet subsystem needs periodic
  re-attestation.
- **WIP artifact.** `last_verified_at` is set at create time and
  cleared on body change per the rules above. A WIP is expected to
  churn and will score highly as long as every body change is
  accompanied by a re-attestation. If it doesn't, it should show up
  stale — that's a signal, not a bug.
- **Artifact the audit worker can't decide about.** `uncertain`
  path keeps the artifact in the queue with the Architect's
  questions recorded; a human operator resolves or escalates.
- **A project with > 5 stale artifacts every night.** The 5-per-night
  cap is deliberate (bounds cost). The `knowledge_freshness_summary`
  event surfaces queue depth; if depth grows sustainedly, the
  operator raises the cap for that project or schedules a cleanup
  cycle.

## Rollout

Single PR per component boundary, gated by a sequence — the schema
change and back-fill must precede the read-envelope change, which
must precede the audit loop.

1. **Schema + validator + back-fill migration.** Frontmatter change,
   `_TEMPLATE.md` updates, validator check, back-fill script. Runs
   across `coder-system/` and every managed project repo. Land before
   anything else.
2. **`FreshnessService` module + API read-envelope extension.**
   Behind `settings.knowledge_freshness_enabled` (default `false`).
   When off, the service is loaded but API responses omit the
   `freshness` block entirely. Shadow mode: service runs on every
   read but the score is logged-only via
   `knowledge_freshness_shadow` for a week before going public.
3. **`.../verify` endpoint.** Lands with the flag still off;
   admin-panel detail view gains the "Verify" button but the flag
   keeps it hidden. Internal smoke test with Architect worker issuing
   a manual verify.
4. **Flag flip.** Flip `knowledge_freshness_enabled=true`. Read
   envelopes start including `freshness`. `min_freshness` becomes
   honoured. Existing callers are unaffected until they opt in.
5. **Audit loop.** Cloud Scheduler entry + job handler + Architect
   task template + report table + admin "Needs attention" view.
   Lands behind `settings.knowledge_audit_enabled` (default `false`).
   Canary on one project for 2 weeks; then enable fleet-wide.
6. **Runbook** `runbooks/knowledge-freshness-audit.md` lands with
   step 5 and is referenced in the weekly operator checklist.

## Open questions

- **Weights calibration.** `0.3/0.5/0.2` is a starting point. After
  one week of shadow data we'll have a distribution of scores and
  can tune so that (a) the "green ≥ 80" band captures
  recently-verified-with-low-activity, (b) the "red < 60" band
  captures verified-long-ago *or* high-activity-since-verify. If
  the band centres drift, the weights are the first knob.
- **Dependency score: min vs percentile.** `min` is strict — a
  single stale dep drags the score down hard. An alternative is
  `percentile(20)` which tolerates one outlier. Starting strict;
  revisit if audits are over-dominated by transitive rot.
- **Body-change flag storage.** `body_changed_since_verify: true` as
  a frontmatter field keeps the rule visible in the file, but it's
  also a field the validator needs to know about and that humans
  might hand-edit. Alternative: derive it on read from
  `git log --format=%cs <path>` vs `last_verified_at`. The git
  derivation is truer to reality and removes the field; pick it if
  the GitHub read cost is tolerable. Decide in the PR.
- **Audit cost ceiling.** 5 artifacts × 1 task × Architect-token
  cost ≈ a known number per project per night. At fleet scale we
  may need to batch multiple artifacts into one audit task. Defer
  until the per-project cost shows up on the weekly cost report.
- **`min_freshness` default for the Architect worker.** Workers
  will likely want a sensible default (e.g. 70). Do we set this in
  the worker, in a per-role config, or require each call site to
  pass it? Leaning "per-role config" — but not this PR.

## Links

- Spec: [wip/0043-knowledge-freshness-signals](../../product-specs/wip/0043-knowledge-freshness-signals.md)
- ADRs:
  [0008 — CI validation of the knowledge repo](../../adrs/0008-ci-validation-of-knowledge-repo.md)
  (validator extension),
  [0014 — freshness derives from declared affects, not semantic similarity](../../adrs/0014-freshness-from-declared-affects.md)
  (this design's key architectural constraint).
- Related designs: [knowledge-repo-model](../active/knowledge-repo-model.md),
  [knowledge-write-api](../active/knowledge-write-api.md),
  [architect-worker](../active/architect-worker.md),
  [observability-and-cost-tracking](../active/observability-and-cost-tracking.md).
- Peer WIPs: [0044 — write-through enforcement on ship](./0044-write-through-enforcement.md)
  (prevents one source of the rot this design surfaces).
- Runbook: `runbooks/knowledge-freshness-audit.md` (lands in rollout step 6).

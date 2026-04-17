---
id: "0043"
title: Knowledge freshness signals
type: spec
status: wip
owner: ro
created: 2026-04-17
updated: 2026-04-17
served_by_designs: ["0043"]
related_specs: [knowledge-api, architect-worker, reviewer-worker, admin-panel, observability]
---

# Knowledge freshness signals

## Problem

The knowledge repo is structured, validated, and atomically written —
but it has no concept of *freshness*. A design describing how
`task-orchestration` works may describe how it worked three releases
ago. The Knowledge API happily serves it; the Architect worker happily
plans against it; the Reviewer worker happily approves code that
"matches the spec" even when the spec is fiction.

Every stale artifact is a confident lie the system tells itself. And
because the fiction is cross-linked and schema-valid, CI validation
(ADR 0008) can't catch it — integrity and freshness are different
problems.

Symptoms we've already seen:

- Architect plans citing an `active/` design whose behaviour was
  altered by a shipped WIP but never merged back (also the motivation
  for spec 0044).
- Operator reads `observability.md` to debug a run and finds the
  described metrics were renamed two weeks ago.
- No way to answer "is this design still true?" without reading the
  code. Defeats the purpose of the knowledge repo.

The repo's value compounds only if readers can trust it. Freshness is
the mechanism that makes that trust inspectable instead of assumed.

## Users / personas

- **Architect / PM worker** — loading designs and specs. Wants to
  know "is this current?" before basing a plan on it, and wants to
  refuse to use content below a freshness threshold.
- **Reviewer worker** — checking a PR against the spec's acceptance
  criteria. Needs to flag when the spec it's reviewing against is
  stale rather than silently rubber-stamp.
- **Operator** — browsing the admin panel. Wants a visible signal of
  which artifacts are decaying so a human can triage.
- **Knowledge API caller** (any worker) — wants to request "give me
  the current truth" and get either a fresh artifact or an explicit
  staleness flag, never silent rot.

## Goals

- Every knowledge artifact carries a `last_verified_at` date and an
  optional `verified_by` (actor slug), persisted in frontmatter.
  Set on create, on explicit re-verification, and cleared on any
  change to the body.
- A computed `freshness_score` in `[0, 100]` per artifact, derived
  from age since `last_verified_at`, commits to declared
  `affects_services` / `affects_repos` since that date, and the
  minimum freshness of artifacts it depends on (transitive rot).
- Knowledge API includes `freshness_score`, `last_verified_at`, and
  the top contributing staleness reasons in every artifact response.
  Callers can request `min_freshness=N` to get a 409 rather than a
  stale artifact.
- A scheduled weekly "freshness audit" job per project that picks the
  N most stale artifacts, hands them to the Architect worker for a
  re-verification pass, and either bumps `last_verified_at` or files
  a structured "needs-rewrite" report that a human can triage.
- Admin panel renders a freshness column on list views and a badge
  on detail views; sort/filter by staleness.

## Non-goals

- Not automating the rewrite itself. Freshness flags the rot; spec
  0044 (write-through on ship) prevents one source of rot; a future
  spec will consider auto-rewrite. This one is signalling.
- Not a full provenance / audit surface — that's the audit log
  (spec 0037). Freshness records "is this current?"; audit records
  "who changed it and when?". Different questions.
- Not a vector-similarity "is the doc semantically close to the
  code?" check. Too expensive, too noisy, not defensible; we rely on
  declared `affects_*` fields the artifact already has.
- Not changing any existing retrieval behaviour for callers that
  don't pass `min_freshness` — backwards-compatible by default.

## Scope

**In:**

- Frontmatter schema change: add `last_verified_at` (required,
  date) and `verified_by` (optional, actor slug) to specs, designs,
  services, repos, roles, integrations, runbooks. ADRs are
  append-only and exempt (their freshness is binary: superseded or
  not).
- CI validator (ADR 0008) extended: `last_verified_at` required,
  parseable, not in the future.
- One-shot back-fill migration that sets `last_verified_at` to the
  file's latest git commit date where the field is absent.
- `FreshnessService` in `coder-core` computing `freshness_score` from
  three inputs, weighted and clamped: age since verify, activity in
  `affects_*` targets since verify, minimum dependency freshness.
  Weights live in a single config block, revisitable.
- Knowledge API: every read envelope gains `freshness` object
  (`score`, `last_verified_at`, `reasons: [kind, detail]`). Reads
  accept optional `min_freshness` query param; below-threshold reads
  return `409 STALE` with the artifact still in the body so the
  caller can choose to use it anyway.
- Knowledge API: `POST /v1/projects/{id}/knowledge/{type}/{id}/verify`
  — attestation endpoint that bumps `last_verified_at` and records
  `verified_by`, with a required `summary` commit message.
- Scheduled audit job: nightly per project, picks 5 lowest-freshness
  artifacts above a staleness floor, creates a `knowledge-audit`
  task for the Architect worker. The worker re-reads the artifact
  plus the changes to its declared targets and emits one of:
  `{decision: verified, summary}`, `{decision: needs_rewrite, gaps}`,
  or `{decision: uncertain, questions}`. First case calls `/verify`;
  other two file a structured report surfaced in the admin panel.
- Admin panel: freshness column in list views (with colour scale),
  badge on detail views, filter chip, sort toggle, and a "Needs
  attention" widget listing audit-reported needs-rewrite artifacts.
- Observability: `knowledge_freshness_score{project,type}` gauge,
  `knowledge_stale_reads_total{project,type,threshold}` counter,
  `knowledge_audit_outcome_total{project,outcome}` counter.
- Runbook: `runbooks/knowledge-freshness-audit.md` describing the
  weekly human pass over the audit queue.

**Out:**

- Per-section (sub-document) freshness. Artifact-level is the unit.
- Real-time tripwire notifications on a target-code commit. The
  signal is derived on read and on the nightly audit; good enough
  and avoids a CI-coupled feedback loop.
- Changing `last_verified_at` semantics for ADRs.
- Freshness for the glossary (atemporal by definition) and for
  `registry.yaml` / `REGISTRY.md` (generated).

## Acceptance criteria

- [ ] All active artifact templates (`_TEMPLATE.md`) include
      `last_verified_at` and `verified_by` in their frontmatter.
      Repo-wide migration lands in one PR.
- [ ] `scripts/validate.py` enforces `last_verified_at` presence,
      parseable date, and `<= today`.
- [ ] `FreshnessService.score(artifact)` returns a value in `[0,100]`
      with unit tests covering: artifact verified today with no
      target activity → 100; artifact 30 days old with no activity
      → ≥ 70; artifact with a commit to a declared `affects_service`
      since verify → ≤ 60; artifact whose transitive dependency has
      score 20 → ≤ 40.
- [ ] Every Knowledge API read response includes a `freshness` object
      matching the documented shape.
- [ ] `GET /v1/projects/{id}/knowledge/{type}/{id}?min_freshness=80`
      returns `409 STALE` with the artifact body when score < 80,
      `200` when ≥ 80.
- [ ] `POST .../verify` bumps `last_verified_at` to today, writes
      `verified_by`, and commits with a structured message including
      the supplied `summary`.
- [ ] Nightly audit job schedules a `knowledge-audit` task for the
      Architect worker per project; the worker's output matches the
      three-outcome schema and each outcome has its documented effect.
- [ ] Admin panel shows freshness badge/column and a "Needs
      attention" widget with the audit queue.
- [ ] Metrics emit on each read, on each audit outcome, and as a
      gauge refreshed nightly.
- [ ] Back-fill migration: after running it, every artifact in
      `system/` and in each managed project's repo has a
      `last_verified_at`. CI passes.

## Metrics

- **Primary:** median freshness score across the fleet, tracked
  weekly. Baseline unknown pre-rollout; target is monotonically
  non-decreasing once the audit loop is live. A declining trend
  means the audit isn't keeping up with rot.
- **Adoption:** share of Knowledge API reads that pass
  `min_freshness`. Low early (backwards-compatible default),
  should trend up as workers adopt the flag.
- **Detection health:** `knowledge_stale_reads_total` / total reads.
  If this is near zero we're either perfect or the threshold is too
  loose; if it's > 20% the thresholds or audit cadence need tuning.
- **Audit throughput:** number of artifacts the weekly audit cycles
  through per project. Target: the 5 lowest-freshness artifacts each
  run get an outcome within 24 h.

## Open questions

- **Weights for the three inputs.** Age, target-activity, and
  dependency-rot contribute to the score — starting weights of
  `0.3 / 0.5 / 0.2` is a guess. Need a calibration pass once we have
  a week of real data before committing these.
- **Staleness floor.** Below what score is an artifact "stale enough
  to audit"? 60 feels right, but tunable per project. One default +
  per-project override is probably correct.
- **Architect as auditor.** Architect already re-reads specs when
  planning; reusing the role is cheap. But a dedicated "Auditor"
  role may make the concern cleaner once this scales. Revisit after
  60 days.
- **`affects_*` coverage.** The score only works if artifacts
  declare their `affects_services` / `affects_repos`. Some active
  artifacts don't. The back-fill migration should flag these, and
  spec 0046 (graph-aware retrieval) reinforces the same requirement.
- **Interaction with WIP artifacts.** WIP is by definition in-flight
  and "fresh"; should WIP files always score 100? Probably, until
  they ship, because they haven't claimed to reflect reality yet.

## Links

- Related specs: [knowledge-api](../active/knowledge-api.md),
  [architect-worker](../active/architect-worker.md),
  [reviewer-worker](../active/reviewer-worker.md),
  [admin-panel](../active/admin-panel.md),
  [observability](../active/observability.md).
- Related ADRs: [0008 — CI validation of the knowledge repo](../../adrs/0008-ci-validation-of-knowledge-repo.md)
  (validator extension lands here).
- Roadmap: [ROADMAP.md](../ROADMAP.md) — Phase 8, item 0043.

---
id: knowledge-freshness
title: Knowledge Freshness
type: spec
status: active
owner: ro
created: 2026-04-17
updated: 2026-05-03
last_verified_at: 2026-05-03
summary: Automatic stale-artifact detection and rewrites.
served_by_designs: [knowledge-freshness]
related_specs: [knowledge-api, architect-worker, reviewer-worker, admin-panel, observability]
parent: knowledge-and-admin
---

# Knowledge Freshness

## What it is

The signalling layer over the [Knowledge API](./knowledge-api.md) that
makes "does this artifact still reflect reality?" an inspectable
property of every read, not an assumption. Each artifact carries a
`last_verified_at` date; a deterministic `freshness_score ∈ [0, 100]`
is computed on every read from age-since-verify, target-code activity
since verify, and the minimum freshness of declared content
dependencies; callers may refuse below-threshold reads; a nightly
audit dispatches the lowest-scored artifacts to the Architect worker
for a three-way verdict; a visible "Needs attention" queue surfaces
the verdicts operators should triage.

Freshness is distinct from schema integrity (validated by CI,
[ADR 0008](../../adrs/0008-ci-validation-of-knowledge-repo.md)) and
from write-through enforcement (spec 0044). Integrity answers "does
the file parse?"; write-through prevents one specific cause of rot at
ship time; freshness answers "is the file still true?" regardless of
cause.

## Capabilities

- **`last_verified_at` on every artifact.** Required frontmatter on
  specs, designs, services, repos, roles, integrations, and runbooks;
  optional `verified_by` (actor slug). ADRs are exempt (append-only;
  freshness is binary — superseded or not). The CI validator enforces
  presence, parseable date, and `<= today`.
- **Freshness score per read.** The Knowledge API's `GET` envelope for
  every artifact includes a `freshness: {score, last_verified_at,
  verified_by, reasons}` block. The score is the deterministic output
  of three inputs: age days since verify, commits to declared
  `affects_*` targets since verify, and the minimum freshness of
  declared content dependencies. Reasons list the top contributing
  factors in decreasing penalty order.
- **`min_freshness=N` query param.** Callers below the threshold get
  `409 STALE` with the stale artifact still in the response body, so
  they can opt in to using it. Absent param preserves the 200 legacy
  contract.
- **Attestation endpoint.** `POST
  /v1/projects/{id}/knowledge/{type}/{id}/verify` with a required
  `summary` bumps `last_verified_at` to today, records `verified_by`,
  and commits a structured message. Returns the commit SHA. ADRs are
  refused (400 `adrs_not_verifiable`).
- **Nightly audit loop.** Per project, once per day: list every
  artifact, score it, pick the bottom-N below the staleness floor
  (default 40, capped at 5 dispatches per run), and create one
  `architect` task per pick. The Architect emits
  `{decision: verified, summary}`,
  `{decision: needs_rewrite, gaps}`, or
  `{decision: uncertain, questions}`. The consumer calls `.../verify`
  on `verified`; records a structured report on the audit-item row
  for the other two.
- **Operator surface.** The admin panel shows a Freshness tab per
  project (and fleet-wide) with the score histogram of the latest
  audit run, a stale count, and a "Needs attention" table of the
  lowest-scored artifacts with a one-click Verify button.
- **Operational metrics.** `GET /v1/_admin/ops/freshness/metrics`
  exposes `knowledge_stale_reads_total{project,type,threshold}`,
  `knowledge_audit_outcome_total{project,outcome}`, and
  `knowledge_freshness_score{project,type}` as labelled rows a
  scraper can turn into Prometheus samples.

## Invariants

- Every read endpoint returns either a `freshness` block with a score
  or a 5xx. No path yields an artifact body without a freshness envelope.
- The score is deterministic given (artifact, repo HEAD, registry
  snapshot, weights). Two calls at the same HEAD return the same score.
- `last_verified_at` is monotonic per artifact — only `PUT` (with
  `verified_by`) or `.../verify` moves it forward. A `PUT` without
  attestation does not advance the date.
- ADRs carry `freshness: {score: 100, reasons: []}` (or 0 when
  superseded) so callers render a neutral pill rather than a "stale"
  indicator. There is no `last_verified_at` on them.
- The audit dispatcher never opens more than the per-run limit
  (default 5) tasks per project per night. A bigger backlog waits for
  the next run.

## Configuration

- **Weights.** Age / activity / dependency contributions are a single
  process-wide config block. Starting calibration:
  age penalty 1 point/day, activity 40 base + 10/extra commit
  (cap 80), dependency penalty `max(0, 80 - dep_min_score)`. The
  spec's open questions flag this for recalibration after a week of
  production data.
- **Staleness floor.** `DEFAULT_FLOOR = 40` today (stricter than the
  original spec suggestion of 60 — we start conservative). Per-project
  override is exposed via the admin audit-trigger endpoint's `floor`
  parameter.
- **Audit cap.** `DEFAULT_LIMIT = 5` dispatches per run. Over-limit
  below-floor artifacts are recorded as `skipped_over_limit` on the
  item ledger for visibility.
- **Activity cache TTL.** 10 minutes. A burst of reads against the
  same artifact within that window shares one GitHub list-commits
  round trip per `(repo, path, since_date)` tuple.

## Interfaces

- `GET /v1/projects/{id}/knowledge/{type}/{id}` — response envelope
  carries `freshness: {score, last_verified_at, verified_by, reasons}`.
- `GET .../knowledge/{type}/{id}?min_freshness=N` — returns
  `409 STALE` with the body still in the 409 detail when below
  threshold; `200` above.
- `POST .../knowledge/{type}/{id}/verify` — bumps `last_verified_at`
  to today, requires a `summary`, records `verified_by`, returns the
  commit SHA. ADRs are refused (400 `adrs_not_verifiable`).
- `POST /v1/_admin/knowledge-audit/run` — fires the nightly audit
  pass for a project (Cloud Scheduler calls this once per 24 h).
- `GET /v1/_admin/ops/freshness/metrics` —
  `knowledge_stale_reads_total{project,type,threshold}`,
  `knowledge_audit_outcome_total{project,outcome}`,
  `knowledge_freshness_score{project,type}` as scrape-ready rows.
- Frontmatter: `last_verified_at` required on every non-ADR artifact;
  optional `verified_by`. `scripts/validate.py` enforces shape.

## Dependencies

- [knowledge-api](./knowledge-api.md) — the read envelope this spec
  extends; the `verify` endpoint is part of that surface.
- [architect-worker](../workers/architect-worker.md) — the audit pass
  dispatches one architect task per below-floor artifact for the
  three-way verdict.
- [reviewer-worker](../workers/reviewer-worker.md) — also reads freshness on
  knowledge fetches during review.
- [admin-panel](./admin-panel.md) — renders the Freshness tab,
  histogram, stale-count tile, and one-click Verify.
- [observability](../pipeline/observability.md) — the audit-outcome and
  stale-read metric channel.

## Evolution

- 2026-04 — initial ship: deterministic score, per-read envelope,
  `min_freshness` 409, attestation endpoint, nightly audit loop,
  admin Freshness tab.

## Links

- Design: [knowledge-freshness](../../designs/active/knowledge/knowledge-freshness.md).
- Related specs:
  [knowledge-api](./knowledge-api.md),
  [architect-worker](../workers/architect-worker.md),
  [reviewer-worker](../workers/reviewer-worker.md),
  [admin-panel](./admin-panel.md),
  [observability](../pipeline/observability.md).
- ADRs:
  [0008 — CI validation of the knowledge repo](../../adrs/0008-ci-validation-of-knowledge-repo.md),
  [0014 — freshness from declared affects, not semantic similarity](../../adrs/0014-freshness-from-declared-affects.md).
- Runbook: [knowledge-freshness-audit](../../runbooks/knowledge-freshness-audit.md).

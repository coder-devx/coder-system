---
id: cold-start-ingestion
title: Cold-start knowledge ingestion
type: spec
status: active
owner: ro
created: 2026-04-27
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: "Bootstrap a new project's knowledge from existing repos."
served_by_designs: []
related_specs: [architect-worker, knowledge-api, knowledge-freshness, managed-workflows, onboarding]
parent: knowledge-and-admin
---

# Cold-start knowledge ingestion

## What it is

A Coder pipeline run that ingests an existing codebase into a single PR
against a new project's knowledge repo — same output shape the architect
worker writes for WIP designs, but targeting `active/` and a human-
reviewed PR rather than the normal approval gate. The operator's work
is correct/edit, not author from blank.

Cold-start is the one-shot bootstrap step that runs after
`coder project onboard` and before the ongoing freshness cycle
(specs 0043/0044) takes over. It harvests what the codebase and git
history already encode: directory layout → services, module
docstrings → designs, commit rationale → ADRs, repeated domain nouns
→ glossary entries.

## Capabilities

- **Architect worker `cold-start` mode.** When a task prompt begins
  with `# Knowledge cold start`, the architect worker swaps in
  `architect_cold_start.json` as its output schema and emits an
  `artifacts[]` array instead of a design envelope. Each entry carries
  `artifact_type` ∈ {`service`, `design`, `adr`, `glossary_entry`},
  `artifact_id`, `body`, `ingestion_provenance`, and
  `confidence ∈ [0, 100]`. Schema failures re-prompt via
  `validate_and_retry`; exhaustion lands `failure_kind="schema"` with
  per-batch detail.

- **Cloud Run Job `coder-core-cold-start-ingest`.** Oneshot (not
  scheduled) job takes `{project_id, code_repo_url, code_repo_ref}`.
  Pipeline: (1) shallow-clone + scan (directory tree `tree -L 3`,
  README files, manifest files, module docstrings, last 500 commit
  messages); (2) bucket into batches ≤ `cold_start_batch_max_input_tokens`
  (default 80k) — primary split on top-level deployable units, flat-repo
  fallback is alphabetical directory partition; (3) aggregate all
  `artifacts[]` into a commit on branch
  `cold-start/<utc-date>-<short-sha-of-code-ref>`, later batches
  receiving earlier batches' accepted frontmatter + ids as context;
  (4) open PR titled `cold-start: <project>` with per-category counts,
  empty categories, low-confidence drops, and audit link.

- **`ingestion_provenance` frontmatter block.** Every cold-started
  artifact carries `{source_paths, source_commit, ingested_at,
  prompt_id, model, confidence, human_edited: false}`. Added as an
  optional field to `template/services/_TEMPLATE.md`,
  `template/designs/_TEMPLATE.md`, `template/adrs/_TEMPLATE.md`, and
  `template/glossary.md` so non-cold-started artifacts also validate.

- **`human_edited` flip GitHub Action.** `.github/workflows/
  flip-cold-start-provenance.yml` (distributed via `template/`) flips
  `human_edited: true` on any cold-started artifact whose body the
  merging commit edits. A one-time `seed_cold_start_action.py` sweep
  seeds the Action into all existing managed repos at release; runbook
  documents the sweep ordering (sweep must complete before any project
  invokes `coder project ingest`).

- **Low-confidence filter.** Artifacts with `confidence <
  cold_start_min_confidence` (default 60) are dropped before landing
  in the PR; one log line each; PR body summarises drops per category.
  Configurable per-project via `projects.cold_start_min_confidence`
  (migration 0051, nullable; NULL inherits fleet default).

- **Re-run safety.** A re-run skips any artifact with
  `human_edited: true` or absent `ingestion_provenance`. PR body lists
  skipped artifacts and skip reason. Later branch name:
  `cold-start-<N>/<utc-date>-<short-sha>`.

- **Cost ceiling.** Hard ceiling of `cold_start_max_tokens` (default
  2M input + 200k output) across all batches per run; exceeding fails
  the job with a structured error rather than continuing.

- **Feature flag.** Fleet-wide `CODER_COLD_START_ENABLED` (default off
  on first deploy). Per-project `projects.cold_start_enabled` (NULL =
  inherit fleet flag, true/false = explicit override) for pre-GA
  testing.

- **CLI.** `coder project ingest <slug> --from <repo-url> [--ref
  <sha|branch>]` enqueues the job and waits-then-prints the PR URL.
  `coder project ingest <slug> --status` shows the most recent run's
  state, batch progress, artifact counts, and PR URL. Uses the existing
  impersonation broker; no new auth surface.

## Invariants

- Every cold-start PR is `auto_approve_*_enabled=false` regardless of
  project policy. Cold-start output always requires a human merge.
- Cold-start never writes to `product-specs/active/` or
  `product-specs/wip/`. Specs describe intent; cold-start infers
  extant state only.
- Runbooks are not inferred — fabrication risk is too high.
- The architect SA used for cold-start tasks is the project's existing
  architect SA; no new auth surface.
- A single `coder project ingest` call ingests one code repo; multi-
  repo projects need multiple calls and produce multiple PRs.

## Interfaces

- Cloud Run Job: `coder-core-cold-start-ingest` (oneshot, not
  scheduled).
- CLI: `coder project ingest <slug> --from <repo-url> [--ref <sha|branch>]`
  (enqueue + wait + print PR URL); `coder project ingest <slug> --status`
  (latest run state, batch progress, counts, PR URL).
- Env: `CODER_COLD_START_ENABLED` fleet flag, per-project
  `projects.cold_start_enabled` (NULL = inherit), per-project
  `projects.cold_start_min_confidence` (migration 0051).
- Templates: `ingestion_provenance` block optional on
  `template/services/_TEMPLATE.md`, `template/designs/_TEMPLATE.md`,
  `template/adrs/_TEMPLATE.md`, `template/glossary.md`.
- Workflow distribution: `flip-cold-start-provenance.yml` shipped via
  the [managed-workflows](./managed-workflows.md) registry.
- Runbooks: `system/runbooks/cold-start-review.md`,
  `system/runbooks/onboard-project.md` (Step 11).

## Dependencies

- [architect-worker](../workers/architect-worker.md) — runs the cold-start
  task with the swapped `architect_cold_start.json` schema.
- [knowledge-api](./knowledge-api.md) — receives the assembled PR.
- [onboarding](./onboarding.md) — `coder project onboard` is the
  prerequisite for `coder project ingest`.
- [managed-workflows](./managed-workflows.md) — distributes the
  `human_edited` flip workflow into every managed repo.
- [knowledge-freshness](./knowledge-freshness.md) — takes over once
  the cold-start PR merges; cold-start sets initial `last_verified_at`.

## Evolution

- 2026-05-06 — Initial ship: architect cold-start mode, oneshot
  Cloud Run Job, PR-per-run with per-category counts, provenance
  block, `human_edited` flip workflow, re-run skip-on-edited, low-
  confidence filter, token ceiling.

## Links

- Design: [cold-start-ingestion](../../../designs/wip/0045-cold-start-ingestion.md)
- Related specs: [onboarding](./onboarding.md),
  [architect-worker](../workers/architect-worker.md),
  [knowledge-api](./knowledge-api.md),
  [knowledge-freshness](./knowledge-freshness.md)

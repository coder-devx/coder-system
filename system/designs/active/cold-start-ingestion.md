---
id: cold-start-ingestion
title: Cold-start knowledge ingestion
type: design
status: active
owner: ro
created: '2026-04-19'
updated: '2026-05-06'
last_verified_at: '2026-05-06'
implements_specs: []
related_designs:
- architect-worker
- knowledge-write-api
- knowledge-repo-model
- worker-communication
- system-overview
affects_services:
- coder-core
- coder-admin
parent: knowledge-and-admin
---
# 0045 — Cold-start knowledge ingestion

## Context

Spec 0045 ships a one-shot bootstrap path that takes
`(project_id, code_repo_url, code_repo_ref)` and produces a single
PR against the project's knowledge repo. The PR contains
machine-inferred services, designs, ADRs, and glossary, each with
an `ingestion_provenance` block. Re-runs are safe because a
post-merge GitHub Action flips `human_edited: true` on artifacts a
human commit has touched, and a re-run skips anything flagged.

This design is the wiring: how the architect worker grows a third
mode, how the ingestion driver batches, how the cross-batch
context flows, and how the open-PR step composes with existing
git/PR helpers in `coder-core`.

## Goals

- Reuse the existing architect worker — no new role, no new SA, no
  new Anthropic key broker path. A new prompt header + a new
  output schema.
- Reuse the existing PR-opening path used by the developer worker
  (`open_pr`) — no new GitHub auth flow.
- Make re-runs idempotent at the artifact level (provenance flag),
  not at the run level (no run-cache lookup).
- Keep the ingestion driver simple: a Cloud Run Job, started once
  per `coder project ingest` invocation, that exits when the PR
  opens. No long-lived state on the box.

## Architecture

```mermaid
flowchart TB
  cli["coder project ingest CLI"] -->|enqueue| api["coder-core API"]
  api -->|create| job["Cloud Run Job<br/>coder-core-cold-start-ingest"]
  job -->|clone| code[(Code repo)]
  job -->|scan + bucket| batches["Per-scope batches"]
  batches -->|N tasks role=architect<br/>prompt header: # Knowledge cold start| disp["Dispatcher"]
  disp -->|each| arch["Architect worker<br/>cold-start mode"]
  arch -->|artifacts[]| agg["Aggregator"]
  agg -->|filter low-conf<br/>+ skip human-edited| commit["Single commit<br/>on cold-start/&lt;date&gt;-&lt;sha&gt; branch"]
  commit -->|open PR| gh[(GitHub: knowledge repo)]
  gh -. post-merge .-> action["Action:<br/>flip human_edited=true"]

  style action stroke-dasharray: 5 5
```

### Parts

- **`coder-core/cli/project_ingest.py`** — new CLI subcommand.
  Enqueues the cold-start job via the API, polls or returns
  immediately based on flags.
- **`coder-core/api/cold_start.py`** — new endpoint
  `POST /v1/projects/{id}/cold-start` that creates the Cloud Run
  Job execution and persists a row in `cold_start_runs` (migration
  0052) for status tracking.
- **`coder-core/cold_start/driver.py`** — entry point of the Cloud
  Run Job. Owns the clone, scan, batch, dispatch, aggregate,
  commit, open-PR sequence.
- **`coder-core/cold_start/scanner.py`** — pure functions that
  take a clone path and return a `ScanResult` (tree, manifests,
  docstrings, commit messages). Stateless.
- **`coder-core/cold_start/batcher.py`** — takes `ScanResult` and
  returns `list[Batch]`. Each `Batch` has a `scope_label` (e.g.
  top-level dir name), `source_paths`, and a token-budget-bounded
  excerpt. See "Batching strategy" below.
- **`coder-core/cold_start/aggregator.py`** — collects per-batch
  `artifacts[]` returns, applies the low-confidence filter, applies
  the human-edited skip, resolves id collisions, builds a single
  commit payload (Git Trees, atomic).
- **`coder-core/workers/architect.py`** — extended to recognise
  the `# Knowledge cold start` header and swap output schemas.
  Existing `validate_and_retry` (0025) covers the new schema.
- **`coder-core/workers/schemas/architect_cold_start.json`** — new
  schema describing the `artifacts[]` envelope.
- **GitHub Action template:**
  `template/.github/workflows/flip-cold-start-provenance.yml` —
  copied into every new project's knowledge repo at onboarding;
  one-time fleet sweep (script
  `scripts/seed_cold_start_action.py`) backfills it into existing
  knowledge repos.
- **Tables:**
  - `cold_start_runs` (migration 0052) — `id, project_id,
    code_repo_url, code_repo_ref, status, started_at, completed_at,
    pr_url, batches_total, batches_done, artifacts_proposed,
    artifacts_dropped_low_confidence, artifacts_skipped_human_edited,
    error_kind, error_detail`. One row per `coder project ingest`
    invocation.
  - `projects` columns (migration 0053):
    `cold_start_enabled BOOLEAN NULL`,
    `cold_start_min_confidence INTEGER NULL`. NULL = inherit fleet
    default.
- **Frontmatter:** `ingestion_provenance` block added to
  `template/services/_TEMPLATE.md`,
  `template/designs/_TEMPLATE.md`,
  `template/adrs/_TEMPLATE.md`,
  `template/glossary.md` as an _optional_ sub-mapping.

### Data flow

1. Operator runs `coder project ingest <slug> --from <url>
   --ref main`.
2. CLI calls `POST /v1/projects/{slug}/cold-start` with body
   `{code_repo_url, code_repo_ref}`. Endpoint validates the
   project's flags (`cold_start_enabled` not explicitly false +
   `CODER_COLD_START_ENABLED=true` fleet) and creates the Cloud
   Run Job execution; inserts a `cold_start_runs` row with
   `status='running'`. Returns the run id.
3. Job entry point (`cold_start/driver.py main`) reads the args,
   shallow-clones the code repo into `/tmp/<run_id>/`, runs the
   scanner (`scanner.scan_repo(path) -> ScanResult`), then the
   batcher (`batcher.into_batches(scan_result, budget)
   -> list[Batch]`).
4. For each batch, the driver enqueues a `role=architect` task
   with a prompt body assembled from the cold-start template:
   ```
   # Knowledge cold start

   Project: <slug>
   Source repo: <code_repo_url>@<ref>
   Source commit: <full sha>
   Scope: <batch.scope_label>
   Source paths: <batch.source_paths>

   ## Project template (the schemas your output must satisfy)

   <inlined template/services/_TEMPLATE.md, designs/, adrs/, glossary.md>

   ## Source material

   <batch excerpts>

   ## Prior batch output (artifacts already proposed in this run)

   <ids + frontmatter only of artifacts the aggregator has
   already accepted from earlier batches; bodies omitted to
   stay under cold_start_batch_max_input_tokens>
   ```
   Cross-batch reuse is one-way: later batches see earlier
   outputs (frontmatter + ids only, no bodies), so an inferred
   design can reference an inferred service from a previous batch
   without re-deriving it; the first batch sees no prior output.
5. The architect worker validates against
   `architect_cold_start.json` via `validate_and_retry`, returns
   `artifacts[]`. Output lands in the task's `output_json` column
   (existing path).
6. The driver polls the dispatched task ids until each is
   terminal (`completed` or `failed`). For each `completed` task,
   the driver pulls `output_json.artifacts` and feeds it to the
   aggregator.
7. **Aggregator** — for each artifact:
   - Skip if `artifact_type == 'service'` and
     `services/<id>.md` already exists in the knowledge repo with
     `ingestion_provenance.human_edited == true` OR with
     `ingestion_provenance` absent (= human-authored). Same check
     for `design`, `adr`, `glossary_entry`.
   - Drop if `confidence < project.cold_start_min_confidence`.
     Increment `artifacts_dropped_low_confidence`.
   - On id collision against another not-yet-committed artifact in
     this run (rare; same id proposed by two batches), keep the
     higher-confidence one and log; if confidences are equal, keep
     first-batch.
8. **Commit + PR.** Aggregator builds a single Git Trees commit
   (one tree, one parent = current `main`, message
   `cold-start: <scope_label_summary>`) on a new branch
   `cold-start/<utc-date>-<short-sha-of-code-ref>`. Author is the
   architect SA (existing). The driver then opens a PR via the
   existing `open_pr` helper (`developer_worker` already uses it),
   title `cold-start: <project>`, body summarising what was
   ingested + dropped + skipped + the per-category empty list.
9. Driver updates the `cold_start_runs` row with
   `status='completed'`, `pr_url`, counters; exits 0. CLI's
   `--wait` mode polls the row to that state and prints the URL.

### Batching strategy

The batcher produces one `Batch` per "logical scope," subject to
a per-batch input token budget
(`cold_start_batch_max_input_tokens`, default 80k input including
the inlined templates).

Heuristic order:
1. **Top-level directories** under the repo root that look like
   deployable units: presence of `pyproject.toml`,
   `package.json`, `Cargo.toml`, `Dockerfile`, `cmd/<name>/`,
   `cloudrun.yaml`, etc. Each becomes its own batch with
   `scope_label = "<dir>"`. Anything resembling `tests/`,
   `docs/`, `vendor/`, `node_modules/`, `target/`, `dist/`,
   `.venv/` is excluded from scope-level batching but its tree is
   still included for context in the parent batch.
2. **Top-level `src/<package>/` packages** if the repo is a flat
   `src/`-style layout. Each `src/<package>` is one batch.
3. **Repo-root catchall.** A final batch with the repo's
   `README*`, top-N markdown files, and the most recent
   `cold_start_commit_history_n` commit messages. This is the
   batch most likely to produce ADRs (commit-message decisions)
   and glossary entries (terms recurring across READMEs).

For each batch, the source-material payload is:
- The directory subtree as `tree -L 3` output.
- All `README*` files in the subtree (truncated at 8k chars
  each).
- All language-manifest files (`pyproject.toml`,
  `package.json`, etc.) verbatim.
- Top-N module-level docstrings (extracted by language-aware
  helpers in `scanner.py` — Python AST, JS/TS regex on
  `/** ... */` at top of file, Rust `//!` doc comments).
- For the catchall batch: last `cold_start_commit_history_n`
  commit messages, no diffs.

If the assembled payload exceeds the budget, the batcher
sub-splits by alphabetical directory partition until each
sub-batch fits. A run with > `cold_start_max_batches` (default
40) sub-batches fails fast — the repo is too large for v1.

### Invariants

- **Provenance presence is the human-vs-machine distinguishing
  feature.** A file with `ingestion_provenance` was machine-
  written; a file without it was human-authored. The post-merge
  Action's job is to flip `human_edited` to `true` whenever a
  commit modifies a file's body, never to remove the block.
- **No artifact lands in `main` without a human merge.** The
  driver always opens a PR. There is no "dry-run = silent
  commit" path.
- **Re-runs never overwrite human edits.** AC6 + the
  `ingestion_provenance.human_edited == true` skip enforce this
  pre-PR; even if a reviewer accidentally merges a re-run PR
  containing an overwrite, the pre-PR aggregator would have
  filtered it.
- **Cost ceiling is hard.** `cold_start_max_tokens` (AC10)
  bounds total spend; the driver sums returned-token counts per
  batch and aborts the run before enqueueing the next batch if
  the next batch's _estimated_ input would exceed the remaining
  budget. The aborted run still opens a partial PR with the
  artifacts collected so far + a body note saying the budget was
  hit.
- **Per-project flag overrides fleet flag in both directions.**
  `projects.cold_start_enabled = true` lets the project run
  cold-start even with the fleet flag off (early-adopter
  pattern); `false` disables it even with the fleet flag on. NULL
  = inherit fleet default. Same tri-state pattern as 0040 / 0041.

## Interfaces

- **API:**
  - `POST /v1/projects/{id}/cold-start`
    body: `{code_repo_url, code_repo_ref}` →
    `{run_id, status: 'running'}`. Auth: project admin token.
  - `GET /v1/projects/{id}/cold-start/runs[?limit=N]` —
    paginated list of past runs, latest first.
  - `GET /v1/projects/{id}/cold-start/runs/{run_id}` — single
    run with counters, status, PR URL, error detail.
- **CLI:**
  - `coder project ingest <slug> --from <url> [--ref <git_ref>]
    [--wait]` — enqueue + optionally poll until PR opens.
  - `coder project ingest <slug> --status` — print most recent
    run's row.
- **Cloud Run Job:** `coder-core-cold-start-ingest` (oneshot;
  invoked per `POST .../cold-start`). Args:
  `--project-id, --run-id, --code-repo-url, --code-repo-ref`.
- **Architect worker:** new prompt header `# Knowledge cold start`
  + new output schema `architect_cold_start.json`. Same task
  shape; same dispatch path; existing transient-retry +
  validate-and-retry compose unchanged.
- **GitHub Action:** template
  `template/.github/workflows/flip-cold-start-provenance.yml`
  triggered on `pull_request` merge into `main`; for each file
  changed, parses the frontmatter, and if
  `ingestion_provenance.human_edited == false` and the diff
  touches the body (not just the frontmatter), flips
  `human_edited: true` and commits the change as a follow-up
  commit attributed to `coder-system-bot`.
- **Audit:** every `cold_start_runs` row state change writes an
  `audit_events` row (`action='cold_start.started' |
  '.completed' | '.failed'`).

## Open questions

- **Cold-start-Action distribution timing.** AC5's per-repo
  Action depends on the workflow file existing. Onboarding +
  template/ covers new projects; existing projects need the
  one-time `seed_cold_start_action.py` sweep. Should the sweep
  be part of the 0045 ship, or a separate "fleet readiness"
  task that lands first? Leaning: ship 0045 with the sweep
  attached to the same release; document in the runbook that
  the sweep must run before any existing project can use cold-
  start. Spec to confirm.
- **Architect worker's confidence calibration.** The 0–100
  scale is shared with 0040 but measures something different
  ("this artifact is faithful to the source code") vs ("this
  output is faithful to the spec the gate is approving"). For
  the first 30 days of cold-start use, we should manually
  spot-check 50 artifacts at 60–70 confidence to see if 60 is
  the right cutoff. Open question for tuning.
- **Glossary across batches.** The aggregator dedupes
  `glossary_entry` by term name (lowercase exact match), keeps
  first-batch wins, logs collisions. Is this strict enough?
  Two batches might propose the same term with subtly different
  definitions; keeping first-batch silently is wrong if batch 2
  is more accurate. Two options:
  (a) keep both as `<term> (alt)` and let the reviewer collapse;
  (b) keep first-batch and log collision details for the
  reviewer.
  Leaning (a) — better for the reviewer to see both and pick.
  Implementation needs the merge step to detect duplicate slug
  in the glossary entries.
- **Should the driver enqueue all batches in parallel or
  sequentially?** Sequential gives later batches access to
  earlier outputs (the cross-batch context-passing wire);
  parallel finishes faster but loses the wire. Trade-off
  matters for time-to-PR.
  Leaning: sequential for v1 because the cross-batch context
  is the difference between a coherent vs incoherent design set,
  and time-to-PR is already in the "afternoon" goal not the
  "minute" goal.
- **What does "categories that came back empty" mean for the
  reviewer?** If `services` is empty, the operator should know.
  Should the PR body link to the cold-start runbook section on
  "what to do when a category is empty"? Leaning yes; runbook
  has a sub-section per category covering the most common
  reasons (services empty = repo isn't structured by service;
  ADRs empty = commit history doesn't have decision rationale,
  not abnormal).

## Rollout

- **Stage 0 — schemas + templates land (no behaviour).** Add
  `architect_cold_start.json`, the new prompt-header recognition
  to the architect worker, the optional `ingestion_provenance`
  block to the four `_TEMPLATE.md` files. No CLI, no Job, no
  endpoint. This is a no-op merge; the existing architect path
  doesn't change.

- **Stage 1 — driver + endpoint behind flag.** Add
  `cold_start_runs` table, the `cold_start/driver.py` module, the
  Cloud Run Job, and the `POST /v1/projects/{id}/cold-start`
  endpoint. `CODER_COLD_START_ENABLED=false` fleet-wide; the
  endpoint returns 503 unless the project explicitly opts in via
  `projects.cold_start_enabled = true`. `coder` opts in.

- **Stage 2 — first cold-start dry run on `coder`.** Run
  `coder project ingest coder --from coder-devx/coder-core --ref
  main` to validate end-to-end: clone works, scanner finds
  services, architect produces sane artifacts, PR opens. PR is
  reviewed but **not merged** (pure validation; the `coder`
  knowledge repo already exists and would be overwritten
  partially — this run is purely to walk the wire). Inspect the
  proposed PR carefully for confidence calibration.

- **Stage 3 — Action distribution sweep.** Run
  `scripts/seed_cold_start_action.py` to land
  `flip-cold-start-provenance.yml` in every existing knowledge
  repo. Verify the Action runs on a synthetic edit + flips
  `human_edited: true`.

- **Stage 4 — fleet flip + first real use.** Flip
  `CODER_COLD_START_ENABLED=true` fleet-wide. The first real
  ingest is the next new project onboarded; the operator follows
  the updated runbook (Step 11 + cold-start review).

- **Stage 5 — UI surface.** Admin `/admin/cold-start` page lists
  recent runs across the fleet (status, project, PR URL,
  counters); per-project `/projects/:id/cold-start` tab shows the
  project's runs. Behind `VITE_COLD_START_ENABLED`. Optional
  for v1 — the CLI + the PR are the primary interface.

## Backout plan

- **Disable a single project's cold-start:**
  `PATCH /v1/projects/{id}` with `cold_start_enabled=false`.
  Stops new runs immediately; running jobs continue (they're
  oneshot Cloud Run executions; killing mid-run leaves a
  partial-state `cold_start_runs` row + no PR).
- **Disable the fleet:** flip
  `CODER_COLD_START_ENABLED=false`. New API calls return 503.
  Existing oneshot jobs keep running; no new ones spawn.
- **Revert a bad cold-start PR:** standard GitHub revert. The
  reverted artifacts now exist in git history but not in the
  current `main`; a re-run will re-propose them (they have no
  `ingestion_provenance.human_edited` flip because they were
  never merged-and-edited). If this is the desired outcome, fine.
  If not, the reviewer should land a follow-up commit on `main`
  that creates empty placeholder versions of the unwanted
  artifacts with `human_edited: true` set, which will cause
  re-runs to skip them.
- **Roll back a schema bug.** If
  `architect_cold_start.json` has a bug, revert that file alone;
  the architect worker will fail-validate on the next cold-start
  task and the run will land in `failed` with `failure_kind=
  "schema"`. No partial PRs, no half-written artifacts (the
  aggregator only acts on completed tasks).
- **Disable the post-merge Action.** Disable the workflow file
  in the affected knowledge repo (Settings → Actions). Re-runs
  will then be unsafe (will overwrite human edits); the runbook
  warns operators to disable the cold-start ingest endpoint at
  the same time if they disable the Action.

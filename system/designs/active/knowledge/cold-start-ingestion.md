---
id: cold-start-ingestion
title: Cold-start knowledge ingestion
type: design
status: active
owner: ro
created: '2026-04-19'
updated: '2026-05-17'
last_verified_at: '2026-05-17'
summary: Bootstrap a new project's knowledge from existing repos.
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

# Cold-start knowledge ingestion

## What it does today

A one-shot, operator-initiated bootstrap path that scans a code repo,
generates machine-inferred services, designs, ADRs, and glossary
entries, and opens a single PR against the project's knowledge repo
with provenance metadata. Re-runs are idempotent at artifact level —
human-edited artifacts are skipped, so the system never overwrites a
human edit without an explicit merge gate.

## Architecture

```mermaid
flowchart TB
  cli["coder project ingest"] -->|enqueue| api["POST /v1/projects/{id}/cold-start"]
  api -->|insert cold_start_runs row<br/>+ enqueue Cloud Run Job| job["cold-start-ingest<br/>(Cloud Run Job)"]
  job -->|clone| code[(Code repo)]
  job --> scanner["scanner.py<br/>tree · manifests · docstrings · commit msgs"]
  scanner --> batcher["batcher.py<br/>per-scope, ≤80k tokens"]
  batcher -->|sequential dispatch<br/>(prior-batch frontmatter for context)| arch["Architect (cold-start mode)<br/>schema: architect_cold_start.json"]
  arch -->|artifacts[]| agg["aggregator.py<br/>(skip human-edited, filter low-conf)"]
  agg -->|atomic commit| branch["cold-start/{date}-{sha} branch"]
  branch --> pr[("PR → knowledge repo")]
  pr -.on merge.-> action["flip-cold-start-provenance.yml<br/>(human_edited=true)"]
```

### Parts

- **`coder_core/cold_start/driver.py`** — Cloud Run entry; orchestrates clone → scan → batch → dispatch → aggregate → commit → PR.
- **`coder_core/cold_start/scanner.py`** — extracts tree, manifests, docstrings, commit messages; stateless.
- **`coder_core/cold_start/batcher.py`** — partitions scan output into per-scope batches (top-level dirs, `src/` packages, repo-root catchall); enforces 80k-token-per-batch budget.
- **`coder_core/cold_start/aggregator.py`** — filters by confidence, skips human-edited, resolves id collisions, builds the atomic commit.
- **`coder_core/api/cold_start.py`** — `POST /v1/projects/{id}/cold-start`; validates `cold_start_enabled`, enqueues job, inserts `cold_start_runs`.
- **`coder_core/workers/architect.py`** (existing, extended) — recognises `# Knowledge cold start` prompt header; swaps to `architect_cold_start.json` output schema.
- **`coder-system/template/.github/workflows/flip-cold-start-provenance.yml`** — post-merge Action distributed via [managed-repo-action-distribution](./managed-repo-action-distribution.md); flips `human_edited=true` on first body diff after merge.

### Data flow

Operator runs `coder project ingest <slug> --from <url> --ref <ref>`.
CLI calls the endpoint; coder-core validates the flag and creates a
Cloud Run Job. Job clones the repo, scans for tree / manifests /
docstrings / commits, batches by scope. For each batch, dispatcher
enqueues an architect task with inlined templates + prior-batch
artifact frontmatter (ids only, for cross-batch context). Architect
outputs `artifacts[]`; aggregator collects, filters by confidence,
dedupes, and builds one commit on a `cold-start/<date>-<sha>` branch.
Driver opens a PR; updates `cold_start_runs` with final status, PR
URL, and counters.

### Invariants

- **Provenance is the human-vs-machine gate.** Files with an `ingestion_provenance` block are machine-written; absent = human-authored. Aggregator skips artifacts when the target file exists with `human_edited: true` or lacks a provenance block.
- **No auto-commit to `main`.** Every run opens a PR; there is no silent-commit or dry-run path.
- **Cost ceiling enforced.** `cold_start_max_tokens` hard-stops the run mid-batch if the next batch's estimated input exceeds the remaining budget; the partial PR opens with a note.
- **Re-runs are idempotent at artifact level, not run level.** No run-cache; provenance flags + skips prevent overwrites.
- **Per-project flag overrides fleet flag bi-directionally.** `cold_start_enabled` tri-state (`true` opts in, `false` opts out, `NULL` inherits fleet).
- **Sequential batch dispatch.** Later batches see earlier artifact frontmatter for cross-batch context; parallel would lose coherence.

## Interfaces

| Surface | Effect |
|---|---|
| `POST /v1/projects/{id}/cold-start` `{url, ref}` | Enqueue Cloud Run Job; returns `{run_id, status: running}` |
| `GET /v1/projects/{id}/cold-start/runs[?limit=N]` | Paginated list (latest first) |
| `GET /v1/projects/{id}/cold-start/runs/{run_id}` | Single run: status, PR URL, counters, error |
| `coder project ingest <slug> --from <url> [--ref] [--wait]` | CLI; `--wait` polls until PR opens |
| `coder project ingest <slug> --status` | Most recent run |
| Architect prompt header `# Knowledge cold start` + `architect_cold_start.json` schema | Worker swaps to cold-start output envelope |
| `flip-cold-start-provenance.yml` (GitHub Action) | On PR merge: flips `human_edited=true` on diff |
| `projects.cold_start_enabled` (tri-state), `projects.cold_start_min_confidence` (float), `cold_start_max_tokens` (env) | Per-project + fleet gates |

## Where in code

- `src/coder_core/cold_start/driver.py` — Cloud Run entry (`run`)
- `src/coder_core/cold_start/scanner.py` — `scan` (pure)
- `src/coder_core/cold_start/batcher.py` — `batch_by_scope`
- `src/coder_core/cold_start/aggregator.py` — `aggregate` (provenance + confidence filter)
- `src/coder_core/api/cold_start.py` — HTTP router
- `src/coder_core/workers/architect.py` — cold-start mode detection + schema swap
- `migrations/0052-cold_start_runs.sql`, `0053-cold_start_settings.sql`

## Evolution

Builds on existing architect-worker (spec 0025 `validate_and_retry`)
and developer worker's `open_pr` helper (no new GitHub auth). Extends
knowledge-repo-model templates with an optional `ingestion_provenance`
block. Distributes its post-merge Action via [managed-repo-action-distribution](./managed-repo-action-distribution.md).

## Links

- Spec: [0045-cold-start-ingestion](../../../product-specs/wip/0045-cold-start-ingestion.md)
- Designs: [architect-worker](../workers/architect-worker.md), [knowledge-write-api](./knowledge-write-api.md), [knowledge-repo-model](./knowledge-repo-model.md), [managed-repo-action-distribution](./managed-repo-action-distribution.md)
- Repos: coder-core, coder-admin, coder-system

---
id: '0045'
title: Cold-start knowledge ingestion
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ['0045']
related_specs:
  - onboarding
  - knowledge-api
  - architect-worker
  - knowledge-freshness
---

# 0045 — Cold-start knowledge ingestion

## Problem

Today onboarding (see `onboarding` spec) gets a new project to "the
knowledge repo exists" — Terraform applied, secrets bound, repo
copied from `template/`, project registered, one developer task
through to merge. What it doesn't do is _populate_ the repo. The
operator is dropped in front of empty `services/`, `repos/`,
`designs/active/`, `adrs/` and asked to author the architectural
truth of an existing codebase by hand. This takes a week per
project — long enough that the realistic outcome is a half-filled
repo with the operator's first guess, then incremental growth as
WIPs ship and trigger the write-through hooks from 0044.

The codebase + git history already encode most of what the empty
repo is supposed to describe: the directory layout names the
services, top-level modules + their docstrings sketch the designs,
README files name the dependencies, and a meaningful fraction of
the commit history has decision rationale (`why ...`, `decided to
...`, `chose X over Y`). Today none of that is harvested.

0045 makes onboarding produce a _populated_ knowledge repo: a Coder
pipeline run that ingests an existing codebase into a single PR
against the new project's knowledge repo, structured the same way
the architect worker writes WIP designs today. The PR is reviewed
by a human — never a silent commit — but the work the human does
is _correct/edit_, not _author from blank_.

## Users

- **Onboarding operator** — wants to onboard a project in an
  afternoon. After running `coder project onboard <slug>` and
  `coder project ingest <slug> --from <repo>`, the operator opens
  one PR titled `cold-start: <project>` against the new knowledge
  repo containing inferred services, designs, ADRs, and glossary.
  The operator's work is review + correction, not authoring from
  empty files.
- **Architect worker** (existing role) — gains a new `cold-start`
  prompt mode (see design) so the same JSON-schema-validated output
  shape is reused. No new role.
- **Reviewer worker** (existing role) — reviews the cold-start PR
  the same way it reviews any other knowledge-write PR: against the
  project's `template/` schemas, frontmatter required fields,
  cross-link integrity. No new gate.

## Goals

- A new project goes from `coder project onboard` to a reviewed
  cold-start PR in **one afternoon (≤ 4h wall clock)** for a code
  repo of < 50 kLoC with < 1000 commits. Larger repos scale
  linearly with batch count, not exponentially.
- The resulting PR contains, _at minimum_:
  - One `services/<slug>.md` per top-level deployable unit detected
    (Cloud Run service, library package, CLI binary, web app).
  - One `designs/active/<subject>.md` per "logical component" the
    architect worker can defend from the code (typically 3–8).
  - 0–N `adrs/00NN-<slug>.md` for commit-history-extracted
    decisions; **N may be zero** — fabricating ADRs from thin
    evidence is worse than no ADR at all.
  - A seeded `glossary.md` with the project-specific nouns the
    architect worker found repeated in the codebase / docstrings.
- **The ingester never writes silently to `main`.** Output is
  always a PR titled `cold-start: <project>` with the architect
  worker named as commit author — same actor shape as every other
  worker write — but landing always requires a human merge.
- Each artifact carries an `ingestion_provenance` frontmatter block
  (path: source path(s) in code repo it was inferred from, commit:
  HEAD sha at ingest time, prompt_id, model). Lets reviewer + future
  freshness scans tell "machine-inferred / never human-edited" from
  "human-curated."
- Re-running the ingester is safe: a second run against the same
  knowledge repo opens a _new_ PR named `cold-start-<N>:` and only
  proposes additions or updates to artifacts whose
  `ingestion_provenance.commit` is older than the new HEAD; nothing
  human-edited (provenance gone or marked `human_edited: true`) is
  overwritten.

## Non-goals

- **Inferring product specs.** Specs describe _intent_ ("we want X
  because Y") not extant code. Cold-start can't truthfully infer
  product intent from a codebase. The PM worker (existing) authors
  specs after onboarding the normal way. We deliberately leave
  `product-specs/active/` empty post-ingest.
- **Inferring runbooks.** Runbooks describe operator procedure.
  Inferring a runbook from "we found a `restart.sh`" is a
  fabrication risk. Runbooks come from the team, not the codebase.
- **Auto-merging the cold-start PR.** Even on a high architect
  `self_confidence` (see 0040), a cold-start PR is
  `auto_approve_*_enabled=false` regardless of project policy.
  Cold-start is the foundation everything else is built on; an
  unreviewed foundation is worse than a slow one.
- **Cross-repo ingestion.** v1 ingests one code repo per call
  (`coder project ingest <slug> --from <repo>`). A multi-repo
  project (e.g. backend + frontend + infra) needs three calls and
  three PRs. v2 may collapse this.
- **Live-syncing inferred state to changes in the code repo.**
  Cold-start is a one-shot bootstrap. The ongoing
  knowledge-stays-in-sync-with-code job is `0044` (write-through on
  ship) + `0043` (freshness signals). 0045 is the _initial_ load.
- **Migrating a project _between_ knowledge repos.** Cold-start
  ingests a code repo, not another knowledge repo. Migrating is a
  separate operation outside this spec.

## Scope

### In scope — architect worker `cold-start` mode

The architect worker (`workers/architect.py`) already has two
modes (default design-authoring, ship-draft from 0044). Cold-start
is a third: when a task's prompt begins with `# Knowledge cold start`,
the worker swaps in `architect_cold_start.json` as its output
schema and emits an `artifacts[]` array (one entry per knowledge
file proposed) instead of a single design envelope.

Each `artifacts[]` entry carries:
- `artifact_type` ∈ {`service`, `design`, `adr`, `glossary_entry`}
- `artifact_id` (kebab slug for service/design/adr;
  `glossary_entry` has no id, body is appended)
- `body` (markdown, with required frontmatter front-loaded)
- `ingestion_provenance` (paths, commit sha, prompt id, model)
- `confidence` (0–100; same scale as 0040's `self_confidence`)

Artifacts with `confidence < cold_start_min_confidence`
(default 60) are filtered out _before_ landing in the PR — better
to omit than to land low-confidence noise the operator has to
delete. The architect worker is allowed to emit fewer artifacts
than expected; the ingest job logs which categories came back
empty so the operator knows where to author from scratch.

### In scope — ingestion driver

A new Cloud Run Job `coder-core-cold-start-ingest` (oneshot, not
scheduled) takes `(project_id, code_repo_url, code_repo_ref)` and
runs the cold-start pipeline:

1. **Clone + scan.** Shallow-clone the code repo at `code_repo_ref`
   into a temp dir. Extract: directory tree (`tree -L 3`), top-N
   `README*` files, top-N `pyproject.toml` / `package.json` /
   `Cargo.toml`, top-N module-level docstrings, last
   `cold_start_commit_history_n` (default 500) commit messages.
2. **Bucket into batches.** Split scanned material into bounded
   batches: one architect task per "logical scope" (a top-level
   directory subtree). Each task runs the architect worker in
   `cold-start` mode against its batch with the full project
   `template/` schemas inlined as system context. Bound: each task
   ≤ `cold_start_batch_max_input_tokens` (default 80k) so the
   worker's context budget never overruns.
3. **Aggregate.** Merge all `artifacts[]` returns into a single
   commit on a new branch
   `cold-start/<utc-date>-<short-sha-of-code-ref>`. Resolve
   id collisions by suffixing (`<id>-<n>`); log them to the
   ingest summary.
4. **Open the PR.** Title `cold-start: <project>`, body summarises
   what was ingested per category + which categories came back
   empty + which artifacts were filtered for low confidence + a
   link to the cold-start audit run.

### In scope — `ingestion_provenance` frontmatter

Every cold-started artifact carries:

```yaml
ingestion_provenance:
  source_paths: ["src/coder_core/api/", "README.md"]
  source_commit: "1311290abc..."
  ingested_at: "2026-04-19T14:00:00Z"
  prompt_id: "cold_start_v1"
  model: "claude-sonnet-4-6"
  confidence: 78
  human_edited: false
```

The `human_edited: false` flag is flipped to `true` by a
post-merge GitHub Action (or by the next freshness audit) the
first time a human-authored commit touches the file body. After
flip, **no future cold-start re-run will overwrite the
artifact.** This is the safety property that makes re-runs safe.

### In scope — CLI

- `coder project ingest <slug> --from <repo-url> [--ref <sha|branch>]`
  enqueues the cold-start ingest task and prints the PR URL when
  ready (or polls and exits once the PR opens). Uses the existing
  impersonation broker; the SA used for the architect tasks is
  the project's existing architect SA. No new auth.
- `coder project ingest <slug> --status` shows the most recent
  cold-start run for the project: state, batches done/total,
  artifacts proposed, low-confidence filtered, PR URL.

### In scope — onboarding runbook update

`system/runbooks/onboard-project.md` (already 10 steps) gains a new
**Step 11: Cold-start ingestion**: "Run `coder project ingest
<slug> --from <repo-url> --ref main`. Wait for the PR to open
(typically 30–90 min for a < 50 kLoC repo). Review the PR per the
cold-start review checklist (`system/runbooks/cold-start-review.md`,
new). Merge. Project knowledge repo is now populated."

A new runbook `system/runbooks/cold-start-review.md` walks the
operator through the review specifically: which categories to
sanity-check first (services & designs), how to read
`ingestion_provenance` to spot fabrication, when to drop an ADR vs
edit it, and how to interpret the "categories that came back empty"
section of the PR body.

### Out of scope

- Auto-detecting which existing branch to ingest from. Always the
  caller-supplied `--ref` (default `main`).
- Inferring `repos.yaml` from anything other than the explicitly-
  passed code repo URL. (We won't crawl GitHub orgs.)
- Reading + ingesting from existing per-project documentation
  sites or wikis.
- Dispatching cold-start automatically as part of `coder project
  onboard`. Two reasons: (a) operator may want to ingest
  multiple repos in sequence; (b) the cold-start review is
  meaningful and shouldn't be hidden inside another command's
  output.

## Acceptance criteria

- **AC1.** Architect worker recognises `# Knowledge cold start` as
  a prompt header and swaps in `architect_cold_start.json` as the
  output schema. Schema validation re-prompts on failure (reuses
  0025's `validate_and_retry`); exhaustion lands `failure_kind=
  "schema"` with the per-batch detail.

- **AC2.** New JSON schema
  `coder_core/workers/schemas/architect_cold_start.json` defines
  `artifacts[]` with `{artifact_type, artifact_id, body,
  ingestion_provenance, confidence}` per entry; required fields
  per type enforced in-schema.

- **AC3.** Cloud Run Job `coder-core-cold-start-ingest` oneshot
  takes `{project_id, code_repo_url, code_repo_ref}` from its
  command-line args; the entry-point clones, scans, batches,
  enqueues architect tasks, aggregates, commits to a new branch,
  opens a PR titled `cold-start: <project>`.

- **AC4.** `ingestion_provenance` frontmatter block lands on every
  artifact written by cold-start; the field is added to
  `template/services/_TEMPLATE.md`, `template/designs/_TEMPLATE.md`,
  `template/adrs/_TEMPLATE.md`, `template/glossary.md` as an
  optional block (not required) so cold-started + non-cold-started
  artifacts both validate.

- **AC5.** A post-merge GitHub Action
  `.github/workflows/flip-cold-start-provenance.yml` (in each
  managed knowledge repo, distributed via `template/`) flips
  `human_edited: true` on any cold-started artifact whose body the
  merging commit edited.

- **AC6.** Cold-start re-run skips any artifact with
  `human_edited: true` (or with `ingestion_provenance` absent =
  human-authored). The PR body lists which artifacts were skipped
  and why ("human-edited" / "no provenance — assumed human").

- **AC7.** Low-confidence filter: artifacts with `confidence <
  cold_start_min_confidence` (default 60) are dropped from the PR
  with one log line each; the PR body summarises drops per
  category. The filter is configurable per-project via a new
  `projects.cold_start_min_confidence` column (migration 0051,
  nullable; NULL = inherit fleet default).

- **AC8.** CLI: `coder project ingest <slug> --from <repo-url>
  [--ref <sha|branch>]` enqueues the job and waits-or-prints the
  PR URL. `coder project ingest <slug> --status` lists the most
  recent run.

- **AC9.** Runbook `system/runbooks/onboard-project.md` adds Step
  11 (cold-start ingestion). New runbook
  `system/runbooks/cold-start-review.md` documents the review
  workflow, what to look for in `ingestion_provenance`, and the
  "categories that came back empty" interpretation.

- **AC10.** Cost budget per cold-start run: hard ceiling of
  `cold_start_max_tokens` (default 2M input + 200k output) across
  all batches in the run. Exceeding fails the job with a structured
  error rather than continuing — operators want a definite stop,
  not a silent multi-x bill.

- **AC11.** Flag-gated fleet-wide on
  `CODER_COLD_START_ENABLED` (default off on first deploy).
  Per-project escape hatch
  `projects.cold_start_enabled` (NULL = inherit, true/false =
  explicit) so a fleet-disabled rollout can still test on `coder`.

## Metrics

- **Time-to-populated** — wall clock from
  `coder project ingest` invocation to PR opened, per project.
  Headline KPI; target ≤ 90 min for a < 50 kLoC repo.
- **Per-category artifact counts** — per cold-start run, count
  of {services, designs, ADRs, glossary entries} produced (post-
  filter). Watch for runs where a category is consistently 0 across
  projects — signals a prompt or scope problem.
- **Low-confidence drop rate** — `dropped / proposed` per category
  per project. > 30% sustained → filter is too strict OR the
  worker's `confidence` calibration is off. Both worth investigating.
- **Re-run overwrite collisions** — count of artifacts a re-run
  _wanted_ to overwrite but didn't because `human_edited: true`.
  High count is healthy (means humans are curating); zero count
  on a long-lived project is suspicious (nobody's editing? or the
  Action isn't flipping?).
- **Token spend per cold-start run** — total input + output tokens
  per run, observed against the `cold_start_max_tokens` ceiling.

## Decisions

Resolved 2026-04-27 ahead of architect dispatch.

- **"Logical scope" batch fallback for flat repos —
  char-budget-bounded alphabetical chunks.** Primary path
  remains top-level deployable units (`pyproject.toml`,
  `package.json`, `cmd/<name>/`, etc.). Fallback when the repo
  is flat (everything under `src/`, no top-level deployable
  signals): split by `cold_start_batch_max_input_tokens`
  budget along alphabetical directory partition. Final
  catchall batch handles repo-root + commit history as before.
- **Cross-batch context-passing — yes, frontmatter+ids only,
  no bodies.** Later batches see earlier batches' accepted
  `artifacts[]` frontmatter + ids in the prompt's "Prior
  batch output" section. Bodies omitted to stay under
  `cold_start_batch_max_input_tokens`. Batch ordering: top-
  level dirs first (services likely), then `src/<package>`
  (designs), then catchall (ADRs + glossary). The aggregator
  filters low-confidence + human-edited *before* exposing to
  next batch — later batches only see the high-confidence
  accepted set.
- **`ingestion_provenance.confidence` vs 0040
  `self_confidence` — independent schemas.** 0040 measures
  per-envelope gate-decision faithfulness; cold-start measures
  per-artifact source-faithfulness. Different units, different
  calibration loops. Sharing a schema would couple two
  unrelated tuning surfaces.
- **Glossary aggregation — lowercase-exact dedupe, first-batch
  wins, log conflicts.** The aggregator dedupes
  `glossary_entry` by `term.lower()`; keeps first-batch's
  proposal; logs collisions to the run summary so the operator
  can spot subtly-different surface forms ("build pipeline"
  vs "CI pipeline") in review. v2 may fold semantically-
  similar entries; v1 is structural.
- **Cold-start-Action distribution — sweep ships with 0045
  release.** The `flip-cold-start-provenance.yml` workflow
  lands in `template/.github/workflows/` (for new projects)
  AND a one-time `seed_cold_start_action.py` sweep runs in
  the same release to seed it into existing managed repos
  (`coder`, `vibetrade`). Runbook documents the sweep
  ordering: sweep must complete before any project can
  invoke `coder project ingest`. **See 0052** —
  shared "managed-repo Action distribution" helper landing as
  pre-work; 0045's seed script consumes that helper.

## Open questions

_None — all resolved. See Decisions above._

## Links

- Related specs:
  [onboarding](../active/onboarding.md),
  [knowledge-api](../active/knowledge-api.md),
  [architect-worker](../active/architect-worker.md),
  [knowledge-freshness](../active/knowledge-freshness.md)
- Design: [0045](../../designs/wip/0045-cold-start-ingestion.md)
- Roadmap entry: [ROADMAP.md](../ROADMAP.md) → Phase 8 / 0045

---
id: "0052"
title: Managed-repo GitHub Action distribution
type: spec
status: wip
owner: ro
created: 2026-04-27
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ["0052"]
related_specs:
  - knowledge-api
  - onboarding
  - audit-log
  - admin-panel
parent: knowledge-and-admin
---

# 0052 — Managed-repo GitHub Action distribution

## Problem

0045 (cold-start ingestion) and 0047 (template schema migration)
both need the same operational primitive: a per-managed-repo
GitHub Action that POSTs back to coder-core when something happens
in the project's knowledge repo. 0045 needs
`flip-cold-start-provenance.yml` (post-merge → flip
`human_edited: true` on cold-started artifacts whose body the
merging commit edited). 0047 needs
`record-template-migration.yml` (PR-merge on a
`template-migration/*` branch → POST to flip the
`template_migrations` row to `merged`).

Two specs encoding the same machinery independently is the
classic shape that produces two divergent implementations: two
GitHub-App permission models, two HMAC-signature shapes, two
seed-script patterns, two failure modes when the App's scopes
drift. Both specs ship "ship 0045 with the sweep attached" and
"ship 0047 with the sweep attached" as their distribution path.
Done twice, that's two scripts, two App permission audits, two
runbooks.

This spec extracts the shared primitive once: a reusable helper
for "install / seed / verify a GitHub Action workflow in every
managed knowledge repo" plus a common receiver-endpoint pattern
on coder-core. 0045 and 0047 then consume it; future
managed-repo-callback features inherit it for free.

## Users

- **Schema/feature author** (operator shipping 0045, 0047, or a
  future feature that needs a managed-repo callback) — writes one
  workflow file in `template/.github/workflows/`, registers an
  endpoint handler with the receiver router, and the
  per-managed-repo distribution + verification is automated.
  No bespoke seed script per feature.
- **Managed-repo reviewer** — sees the workflow PR land via the
  same shape every time; the workflow file is small and
  formulaic so review cost is minimal.
- **Operator** — has one place to check fleet-wide workflow
  installation state (admin matrix at `/admin/managed-workflows`)
  and one runbook for "the App's permissions drifted, here's how
  to recover."

## Goals

- One helper, N workflows. Each managed-repo workflow lands in
  `template/.github/workflows/` once and seeds into the fleet
  via a single command-line tool, not a feature-specific script.
- One receiver-endpoint pattern. HMAC signature verification,
  project-id derivation from the calling repo, dispatch to the
  feature handler — written once, not duplicated across
  `flip-cold-start-provenance` and `record-template-migration`
  and every future caller.
- Fleet manifest. `coder-system/system/managed-workflows.yaml`
  enumerates the workflows expected to be installed in every
  managed knowledge repo. Drift (workflow expected but missing,
  or installed but not in the manifest) shows up on the admin
  matrix.
- Idempotent install. Running the seed sweep twice doesn't open
  duplicate PRs; the helper checks `template/.github/workflows/`
  contents in the target repo first.

## Non-goals

- **Workflow content.** This spec ships the *distribution*
  mechanism; the workflows themselves are owned by the consuming
  spec (0045's flip-provenance, 0047's record-migration, etc.).
- **Replacing GitHub App management.** App installation,
  per-repo grants, and scope auditing remain operator work;
  this spec consumes the existing App, not redesigns it.
- **Cross-org distribution.** The fleet is single-org for v1.
  A future multi-org tenant gets a follow-up.
- **Workflow execution monitoring beyond install state.** This
  spec tracks "is the workflow file present at the expected
  path?" — not "did the last run succeed?" Per-feature handlers
  surface their own success/failure metrics.

## Scope

### In scope — fleet manifest

`coder-system/system/managed-workflows.yaml` lists every
workflow the fleet expects, by `id` + `template_path` +
`receiver_endpoint`:

```yaml
workflows:
  - id: flip-cold-start-provenance
    template_path: template/.github/workflows/flip-cold-start-provenance.yml
    receiver_endpoint: /v1/projects/{project_id}/cold-start/provenance-flipped
    consuming_spec: "0045"
    introduced: "2026-05-15"  # date the workflow first ships
  - id: record-template-migration
    template_path: template/.github/workflows/record-template-migration.yml
    receiver_endpoint: /v1/_admin/template/migrations/{project_id}/{migration_number}/{batch_index}/merged
    consuming_spec: "0047"
    introduced: "2026-06-01"
```

The manifest is the source of truth. Adding a workflow = PR that
adds a row + the workflow file + the receiver handler.

### In scope — common helper

`coder_core/integrations/managed_repo_workflows.py` exposes:

- `install_workflow(project_id, workflow_id) -> InstallResult` —
  opens a PR titled
  `managed-workflow: install <workflow_id>` against the
  project's knowledge repo, adding the workflow file and a
  `.github/managed-workflows.txt` entry recording the install.
  Idempotent: returns `Skipped(reason="already_installed")` if
  the workflow file already exists at the expected path with
  matching content.
- `verify_workflow(project_id, workflow_id) -> VerifyResult` —
  fetches the project's `.github/workflows/<id>.yml`, compares
  to `template_path` content. Returns
  `Match | Drift(diff) | Missing`.
- `iter_managed_workflows() -> list[WorkflowSpec]` — reads the
  fleet manifest.

### In scope — seed CLI

`coder managed-workflows sync [--workflow <id>]
[--projects <slug,...>]` runs the sweep:

1. Loads the manifest.
2. For each `(project, workflow)` pair (filter by args), calls
   `install_workflow`.
3. Prints a summary: opened PRs, skipped (already installed),
   errors.

Default (no args) is full fleet × full manifest.

### In scope — receiver endpoint shape

A common middleware
`coder_core/integrations/managed_repo_callbacks.py`:

- Verifies the inbound POST's HMAC signature against the
  GitHub App's webhook secret.
- Derives `project_id` from the calling repo (using the
  existing `projects` table's `github_org` + `github_repo`
  lookup).
- Routes to the registered feature handler by `workflow_id`
  in the path or header.
- Audit-log row written for every successful callback
  (`action='managed_workflow.callback'` with workflow_id +
  project_id + handler outcome).

Each consuming spec registers its handler at module import time:

```python
from coder_core.integrations.managed_repo_callbacks import register_handler

register_handler(
    workflow_id="flip-cold-start-provenance",
    handler=cold_start.handle_provenance_flip,
)
```

### In scope — admin matrix

`/admin/managed-workflows` page shows the fleet × workflow grid:
one row per project, one column per workflow in the manifest.
Cell shows status pill: `✓ installed` / `⚠ drift` /
`✗ missing` / `… installing` (PR open). Click cell → PR URL or
diff view. Behind `VITE_MANAGED_WORKFLOWS_ENABLED`.

Backed by `GET /v1/_admin/managed-workflows` which calls
`verify_workflow` for every cell (cached 5 min).

### In scope — runbook

`system/runbooks/managed-workflows.md` (new): how to add a new
managed workflow (manifest row + workflow file + handler
registration); how to run the sweep; how to recover from
GitHub-App-permission drift; how to interpret the admin matrix.

### Out of scope

- Workflow execution log surfacing (each consuming spec owns
  its own success/failure metrics).
- Auto-removing workflows that fall off the manifest (operator
  closes the loop manually for v1; the admin matrix flags
  "installed but not in manifest" as drift).
- Cross-org distribution (single-org fleet for v1).
- Workflow templating beyond literal file copy (no per-project
  variable substitution; if a workflow needs project-specific
  values, it reads them from coder-core via the receiver
  endpoint at runtime).

## Acceptance criteria

- **AC1.** `coder-system/system/managed-workflows.yaml` exists
  with the schema in scope. CI validates: unique `id`,
  `template_path` exists in `template/.github/workflows/`,
  `receiver_endpoint` is a valid path string.

- **AC2.** `install_workflow(project_id, workflow_id)` opens a
  PR titled `managed-workflow: install <workflow_id>` against
  the project's knowledge repo. Idempotent: a second call with
  the workflow already installed returns
  `Skipped(reason="already_installed")` and opens no PR.

- **AC3.** `verify_workflow(project_id, workflow_id)` returns
  `Match` when contents are byte-identical, `Drift(diff)` when
  the file exists but differs, `Missing` when absent.

- **AC4.** `coder managed-workflows sync` runs the sweep with
  optional filters; prints opened/skipped/error summary; exits
  0 on partial success (any errors reported in the summary).

- **AC5.** Receiver-endpoint middleware verifies HMAC against
  the GitHub App webhook secret; rejects 401 on signature
  mismatch; derives `project_id` from the calling repo; routes
  to the registered handler; writes
  `audit_events.action='managed_workflow.callback'` on success.

- **AC6.** Handler registration via `register_handler()` is
  module-import-time. A managed workflow whose handler is not
  registered returns 404 with `reason="handler_not_registered"`
  on inbound callback.

- **AC7.** Admin endpoint `GET /v1/_admin/managed-workflows`
  returns the fleet × workflow matrix with verify-status per
  cell. Cached 5 min (so the admin page doesn't re-walk every
  managed repo on every render).

- **AC8.** Admin page `/admin/managed-workflows` renders the
  matrix behind `VITE_MANAGED_WORKFLOWS_ENABLED`. Cell click
  shows PR URL (if installing), drift diff (if drift), or
  workflow source (if installed).

- **AC9.** Runbook `system/runbooks/managed-workflows.md`
  documents adding workflows, running the sweep, recovering
  from App-permission drift, interpreting the admin matrix.

- **AC10.** Flag-gated fleet-wide on
  `CODER_MANAGED_WORKFLOWS_ENABLED` (default off on first
  deploy). When off, the receiver middleware returns 503 and
  the admin endpoint returns 404. The seed CLI still works
  locally for dry-runs.

## Metrics

- **Workflows-installed-vs-expected** — per project, count of
  workflows installed (from `verify_workflow` Match results)
  vs. manifest size. Headline KPI for fleet readiness.
- **Drift count** — per workflow, count of projects in
  `Drift` state. > 0 sustained = either a workflow update needs
  re-distribution or a project edited the file locally (the
  latter shouldn't happen but signals an investigation).
- **Sweep duration** — wall-clock for `coder
  managed-workflows sync` against the full fleet. Target ≤ 2
  min for fleet=10; informs whether per-project parallelism is
  needed.
- **Callback latency** — receiver handler p95 wall-clock,
  per workflow. Outliers signal a slow downstream handler.
- **Callback failure rate** — % of inbound callbacks that
  return non-2xx, per workflow. Per-handler bug indicator.

## Decisions

Resolved 2026-04-27 at spec creation.

- **Manifest format YAML, not Python.** Schema authors don't
  need to run a Python file to know what's installed; YAML is
  reviewable, diffable, and CI-validatable.
- **Idempotency check is content match, not file existence
  alone.** A workflow file present but stale (different
  content from `template_path`) is `Drift`, not "installed."
  Catches the case where the workflow's template was updated
  but the fleet sweep wasn't re-run.
- **Per-project handler, not per-workflow handler.** The
  receiver routes by `workflow_id`; if a future workflow needs
  per-project conditional logic (project A handles differently
  from project B), the handler queries the project state.
  Avoids the explosion of N×M handler registrations.
- **PR title format `managed-workflow: install <workflow_id>`.**
  Mirrors `template-migration: 00NN-<slug>` shape (0047) so
  reviewers see a uniform "machine-opened workflow PR" prefix.
- **5-min cache on `verify_workflow` for the admin matrix.**
  Walking every managed repo on every admin-page render costs
  more than the freshness gain. 5 min is the same TTL the
  knowledge-API single-read uses.

## Open questions

- **GitHub App webhook secret rotation.** When 0038 rotates
  the GitHub App's webhook secret, the receiver middleware's
  HMAC verifier needs the same dual-value window machinery
  (accept old + new for the rotation gap). Should this spec
  add it explicitly, or inherit from the existing admin-JWT
  dual-value pattern? Leaning: inherit, but document the
  expected behaviour in the runbook so an operator
  troubleshooting failed callbacks during rotation has a
  pointer.

- **Should removed workflows auto-uninstall?** If a workflow
  is removed from the manifest (consuming feature deprecated),
  do existing project repos retain the workflow file? Leaning:
  yes, retain — automatic deletion of workflow files in
  reviewed-by-default repos feels too aggressive. The admin
  matrix flags "installed but not in manifest" as drift; the
  operator opens a removal PR per project.

## Links

- Designs: [0052](../../designs/wip/0052-managed-repo-action-distribution.md) (to be drafted by architect)
- Related specs:
  [knowledge-api](../active/knowledge-api.md),
  [onboarding](../active/onboarding.md),
  [audit-log](../active/audit-log.md),
  [admin-panel](../active/admin-panel.md)
- Consumed by: [0045](./0045-cold-start-ingestion.md) (flip-cold-start-provenance), [0047](./0047-template-schema-migration.md) (record-template-migration)

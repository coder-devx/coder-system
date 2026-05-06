---
id: managed-workflows
title: Managed-repo workflow distribution
type: spec
status: active
owner: ro
created: 2026-05-06
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: []
related_specs: [knowledge-api, onboarding, audit-log, admin-panel]
parent: knowledge-and-admin
---

# Managed-repo workflow distribution

## What it is

A shared primitive for installing, verifying, and receiving callbacks
from GitHub Action workflows across every managed knowledge repo.

Multiple features (0045 cold-start ingestion, 0047 template schema
migration) need the same machinery: a per-managed-repo workflow that
POSTs back to coder-core on a project event. This spec extracts that
machinery once — manifest, install helper, seed CLI, receiver
middleware — so future features inherit it at no per-feature cost.

## Capabilities

- **Fleet manifest.** `coder-system/system/managed-workflows.yaml`
  enumerates every workflow the fleet expects: `id` +
  `template_path` + `receiver_endpoint` + `consuming_spec` +
  `introduced`. CI validates: unique `id`, `template_path` exists
  in `template/.github/workflows/`, `receiver_endpoint` is a valid
  path string.

- **Install helper.** `coder_core/integrations/managed_repo_workflows.py`
  exposes `install_workflow(project_id, workflow_id) -> InstallResult`:
  opens a PR titled `managed-workflow: install <workflow_id>` against
  the project's knowledge repo. Idempotent — returns
  `Skipped(reason="already_installed")` if the workflow file already
  exists at the expected path with matching content.

- **Verify helper.** `verify_workflow(project_id, workflow_id) ->
  VerifyResult` fetches the project's workflow file and compares it
  to the `template_path` content. Returns `Match | Drift(diff) |
  Missing`. Idempotency check is content-match, not file-existence
  alone — a stale file is `Drift`, not "installed".

- **Seed CLI.** `coder managed-workflows sync [--workflow <id>]
  [--projects <slug,...>]` runs the fleet sweep: loads the manifest,
  calls `install_workflow` for each `(project, workflow)` pair
  (filtered by args), prints opened/skipped/error summary, exits 0
  on partial success. Default (no args) = full fleet × full manifest.

- **Receiver endpoint middleware.**
  `coder_core/integrations/managed_repo_callbacks.py` verifies the
  inbound POST's HMAC signature against the GitHub App webhook
  secret, derives `project_id` from the calling repo (via `projects`
  table `github_org` + `github_repo` lookup), routes to the
  registered handler by `workflow_id`, and writes an
  `audit_events.action='managed_workflow.callback'` row on success.
  Signature mismatch → 401. No registered handler → 404 with
  `reason="handler_not_registered"`.

- **Handler registration.** Each consuming spec registers at
  module-import time:
  `register_handler(workflow_id, handler)` from
  `coder_core.integrations.managed_repo_callbacks`.

- **Feature flag.** `CODER_MANAGED_WORKFLOWS_ENABLED` (default off
  on first deploy). When off, the receiver middleware returns 503
  and the admin endpoint returns 404. The seed CLI works locally for
  dry-runs regardless of the flag.

## Interfaces

- `coder-system/system/managed-workflows.yaml` — fleet manifest;
  a PR adding a row + workflow file + handler registration is the
  protocol for shipping a new managed workflow.
- `coder_core/integrations/managed_repo_workflows.py` —
  `install_workflow`, `verify_workflow`, `iter_managed_workflows`.
- `coder managed-workflows sync` — CLI sweep.
- `coder_core/integrations/managed_repo_callbacks.py` — receiver
  middleware + `register_handler`.
- `GET /v1/_admin/managed-workflows` — fleet × workflow verify-status
  matrix; `verify_workflow` per cell; cached 5 min.
- `system/runbooks/managed-workflows.md` — operator runbook: adding
  workflows, running the sweep, recovering from GitHub-App-permission
  drift, interpreting the admin matrix.

## Dependencies

- GitHub App with write access to managed knowledge repos (existing).
- `projects` table `github_org` + `github_repo` columns for
  `project_id` derivation on inbound callbacks.
- audit-log — `managed_workflow.callback` events on every successful
  callback dispatch.
- admin-panel — `/admin/managed-workflows` matrix page renders the
  fleet × workflow grid (see [admin-panel](./admin-panel.md)).

## Non-goals

- Workflow content — owned by the consuming spec (0045, 0047, etc.).
- GitHub App management, per-repo grants, scope auditing — operator
  work; this spec consumes the existing App.
- Cross-org distribution — single-org fleet for v1.
- Workflow execution monitoring beyond install-state — per-feature
  handlers surface their own success/failure metrics.
- Auto-removing workflows that fall off the manifest — admin matrix
  flags "installed but not in manifest" as drift; operator closes
  the loop manually per project.

## Evolution

- 0052 Initial ship (2026-05-06) — extracted from 0045/0047 which
  independently encoded the same per-managed-repo callback primitive.
  Ships: fleet manifest, install helper, verify helper, seed CLI,
  receiver middleware, handler-registration API, feature flag, runbook.

## Links

- Related specs: [knowledge-api](./knowledge-api.md),
  [onboarding](./onboarding.md), [audit-log](./audit-log.md),
  [admin-panel](./admin-panel.md)
- Consumed by: 0045 (flip-cold-start-provenance workflow),
  0047 (record-template-migration workflow)

---
id: managed-workflows
title: Managed-repo GitHub Action distribution — operate the matrix
type: runbook
status: active
owner: ro
created: 2026-05-10
updated: 2026-05-10
last_verified_at: 2026-05-10
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [github]
---

# Managed-workflows operations

The fleet manifest at `system/managed-workflows.yaml` lists every
GitHub Action coder-core expects to find installed in every managed
knowledge repo. Three things keep the matrix coherent:

1. The manifest itself.
2. The `coder managed-workflows {status,install,diff}` CLI that opens
   a PR per `(project, workflow)` pair.
3. The admin matrix at `/admin/managed-workflows` (admin JWT, behind
   `VITE_MANAGED_WORKFLOWS_ENABLED`) backed by
   `GET /v1/_admin/managed-workflows`.

This runbook is the operator playbook for those three surfaces. The
spec is design 0052; the architectural decisions are
[ADR 0018](../adrs/0018-managed-workflows-divergent-file-policy.md).

## Add a new managed workflow

Adding a workflow is a four-file change:

1. **Workflow template.** Drop the YAML at
   `template/.github/workflows/<id>.yml`. The path is exactly what
   ends up at `.github/workflows/<id>.yml` inside every managed repo;
   templating beyond literal copy is **out of scope** (a workflow that
   needs per-project values reads them from coder-core via the
   receiver endpoint at runtime).
2. **Manifest row.** Add an entry to `system/managed-workflows.yaml`:

   ```yaml
   - id: my-workflow
     template_path: template/.github/workflows/my-workflow.yml
     receiver_endpoint: /v1/projects/{project_id}/my-feature/event
     consuming_spec: "00NN"
     introduced: YYYY-MM-DD
   ```

3. **Receiver handler.** In coder-core, register the handler at
   module-import time:

   ```python
   from coder_core.integrations.managed_repo_callbacks import register_handler

   register_handler(workflow_id="my-workflow", handler=my_feature.handle_event)
   ```

   Make sure the module is imported by `coder_core.main` so the
   registration runs at app startup (the spec-0053 `ci_watcher`
   import is the existing precedent).

4. **Tests.** Cover the handler the way `tests/test_ci_watcher.py`
   covers `check-run-ci-fixup` — HMAC happy path + signature
   mismatch + handler not registered.

Both the `template/` file and the manifest row land in the same PR
against `coder-system`; the receiver handler lands in coder-core in
its own PR.

## Run the install sweep

Once the manifest carries a new row, install it across the fleet:

```sh
# Dry-run (status only, no PRs):
coder managed-workflows status

# Open install PRs across the fleet:
coder managed-workflows install

# Filter to one workflow / one project for canary rollout:
coder managed-workflows install --workflow my-workflow --project coder
```

The CLI is idempotent — a second run with the file already installed
returns `UpdatedExisting` (no PR opened). When the file exists but
its contents diverge from the template, the default behaviour is
`SkippedDivergent`; pass `--force` to open an overwrite PR.

`CODER_SYSTEM_DIR` (or `--manifest-dir`) tells the CLI where to find
the checkout. `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY` (same Secret
Manager values coder-core uses) are required to mint the per-repo
installation token.

## Read the admin matrix

`/admin/managed-workflows` (admin JWT) renders the same data shape
the CLI's `status` subcommand prints, served by
`GET /v1/_admin/managed-workflows`. One row per non-archived project,
one cell per manifest entry; pill colour reflects status:

- `installed` (emerald) — file present, blob SHA matches the template.
- `drift` (amber) — file present, blob SHA differs. Click the cell
  for the observed/expected SHA pair; `coder managed-workflows diff`
  prints the unified diff.
- `missing` (rose) — file absent. Run
  `coder managed-workflows install --workflow <id> --project <slug>`.
- `error` (deeper rose) — `verify_workflow` raised. Click for the
  error string (most often a missing template file in the local
  checkout).

The matrix endpoint caches its snapshot for 5 minutes — repeated
renders within that window don't re-walk the fleet. The `generated_at`
timestamp on the response shows when the snapshot was built.

The endpoint **404s** when `coder_managed_workflows_enabled` is False
on the coder-core service; the SPA route 404s likewise when
`VITE_MANAGED_WORKFLOWS_ENABLED` is unset. Both default off so the
fleet ramp can stay quiet until a workflow is actually shipping.

## Recover from GitHub-App permission drift

The HMAC receiver verifies callbacks against the GitHub App webhook
secret mounted as `GITHUB_APP_WEBHOOK_SECRET`. When that drifts (App
re-installed against a tenant, secret rotated without a Cloud Run
redeploy, App scopes narrowed) the symptoms are:

- `coder managed-workflows status` prints `error` rows for every
  project — the Contents API call gets a 403.
- The admin matrix turns rose-error across the board with
  `error: 403 …` strings.
- Inbound callbacks from already-installed workflows return
  `signature_mismatch` in the audit log.

Recovery:

1. Re-confirm the App installation in GitHub for the affected
   tenant (Settings → Integrations → coder-core App → Configure).
2. If the webhook secret was rotated, mint a fresh value and update
   the `GITHUB_APP_WEBHOOK_SECRET` Secret Manager version. The
   coder-core service picks it up on the next Cloud Run revision —
   redeploy with `make deploy-coder-core`.
3. If the App's `contents:read` scope was removed, re-grant it
   per-repo from the App's installation page; the verify path needs
   read access to `.github/workflows/*.yml`.
4. Re-run `coder managed-workflows status` — every cell should flip
   back to `installed` within the cache TTL (or immediately after
   `clear_matrix_cache()` in a debug shell).

Until the App is healthy, the receiver returns 503
`managed_workflows_disabled` to managed repos that try to POST in;
the workflow's `Retry on failure` step keeps the event in flight
until the next successful POST. No backfill is needed for short
outages.

## Decommission a workflow

The matrix flags drift "installed but not in manifest" — a workflow
file present in a managed repo but absent from the manifest. v1 does
**not** auto-uninstall (per spec 0052 §Open questions); the operator
opens a removal PR per project. Workflow:

1. Remove the manifest row in coder-system.
2. Open per-project removal PRs by hand: branch
   `managed-workflow/uninstall-<id>`, delete
   `.github/workflows/<id>.yml`, PR title
   `managed-workflow: uninstall <id>`.
3. The next admin matrix render shows the cell as missing for the
   uninstalled project; once every project is missing, the column
   itself drops on the next deploy that picks up the manifest change.

## Links

- **Active design:** [managed-repo-action-distribution](../designs/active/knowledge/managed-repo-action-distribution.md)
- **ADR:** [0018](../adrs/0018-managed-workflows-divergent-file-policy.md)
- **PHASES.md entry:** spec 0052
- **Manifest:** [`system/managed-workflows.yaml`](../managed-workflows.yaml)

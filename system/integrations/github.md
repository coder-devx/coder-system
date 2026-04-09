---
id: github
name: GitHub
type: integration
status: active
owner: ro
auth: github-app
secret_storage: gcp-secret-manager
used_by_services: [coder-core]
used_by_roles: [software-architect, developer, reviewer, release-manager]
---

# GitHub

## What it is

Source of truth for all code — Coder itself and every managed project.

Like GCP, the topology is **two layers**:

| Layer | GitHub org | Holds |
|---|---|---|
| **Coder itself** | [`coder-devx`](https://github.com/coder-devx) | `coder-core`, `coder-admin`, `coder-system`, future `coder-worker-*` repos. |
| **Each managed project** | its own GitHub org (e.g. `ViberTrade`) | The managed product's own repos: services, frontends, infrastructure-as-code, and the project's own `coder-system` knowledge repo. |

A **new project onboarded to Coder gets a brand new GitHub org**. No
managed project shares an org with another, and no managed project shares
an org with Coder itself. See [ADR 0009](../adrs/0009-per-managed-project-cloud-account-and-github-org.md).

## Auth model

- **GitHub App** is the planned long-term mechanism (PATs don't scale to
  per-project installation). The Coder GitHub App will be installed once
  into the `coder-devx` org and again into each managed project's org.
- The app's installation token is short-lived; Coder Core will mint a
  fresh one per request, scoped to the relevant installation (i.e., the
  managed project being acted on).

### Current state (as of 2026-04-09)

- **Fine-grained PAT** — `coder-coder-github-pat` in `vibedevx` Secret Manager, mounted into `coder-core` as env var `GITHUB_TOKEN` via `--update-secrets=GITHUB_TOKEN=coder-coder-github-pat:N`. Cloud Run is **pinned to a specific version**, not `:latest`, because Cloud Run doesn't re-read `:latest` on running instances — pinning makes each rotation force a fresh revision.
- The runtime service account `coder-core-sa@vibedevx.iam` has `roles/secretmanager.secretAccessor` **scoped only to `coder-coder-github-pat`** (not project-wide).
- A legacy secret `GITHUB_TOKEN` from `coder-agent` days still exists in Secret Manager but is orphaned — Cloud Run doesn't reference it and the runtime SA no longer has access to it. Safe to delete once the new secret is proven.
- **Current scopes** (version 4, rotated 2026-04-09): fine-grained PAT scoped to `coder-devx/{coder-core,coder-admin,coder-system}` with `Contents: Read and write`, `Pull requests: Read and write`, `Metadata: Read`. Earlier read-only scopes were broadened so the developer worker can push branches and open PRs from a per-task clone — see [coder-core dispatcher workspace path](../services/coder-core.md). Earlier broad classic scopes (`admin:org`, `repo`, `workflow`) were retired in the same rotation.
- **Used by two callers in the same service:**
  - The **knowledge API** in `coder-core` (`src/coder_core/integrations/github.py`) reads repo file contents via the `Accept: application/vnd.github.raw` trick on `GET /repos/{org}/{repo}/contents/{path}`. Only ever issues GETs; doesn't need the write scopes but inherits them.
  - The **developer worker** in `coder-core` (`src/coder_core/workers/workspace.py`) writes the same token into a per-task `.netrc` so `git clone`, `git push`, and `gh pr create` (via `GH_TOKEN`) authenticate without ever putting the token on a command line.
- **Single-secret follow-up**: Sharing one PAT between the knowledge API (read-only need) and the developer worker (write need) means the knowledge API runs with broader scopes than it uses. Cleaner split is two secrets — `coder-coder-github-pat-readonly` for the knowledge API, `coder-coder-github-pat-worker` for the dispatcher — keyed off two different settings in `coder_core.config`. Worth doing before we onboard any managed project beyond the `coder` project itself, since each managed project will already be minting its own `coder-{project_id}-github-pat` secret via the per-project template.

### Rotating the PAT

The repo ships `coder-core/scripts/rotate-github-pat.sh`. It:

1. Reads the new PAT from stdin (never touches disk)
2. Sanity-checks it against `GET /repos/coder-devx/coder-system` before touching GCP
3. Adds a new version to `coder-coder-github-pat`
4. Pins Cloud Run to the new version via `gcloud run services update --update-secrets=...` (forces a fresh revision)
5. Smoke-tests the knowledge endpoint end-to-end
6. Prints the active version + revision, plus a one-liner to disable older versions

```sh
# Paste + Ctrl-D
scripts/rotate-github-pat.sh

# Or from a file
scripts/rotate-github-pat.sh < new-pat.txt

# Or from a password manager
op read 'op://Coder/github-pat/token' | scripts/rotate-github-pat.sh
```

Older versions stay enabled until you explicitly disable them, so you can roll back in seconds.

## Surface used

- Repo browse: list trees, read files, search code.
- Mutations: create/update files, open PRs, open issues, review PRs.
- Workflows: trigger Actions runs, read run results.
- Org admin (System Admin role only): create new repos, set branch
  protection, configure CI secrets.

## Permissions / scopes (GitHub App)

- Per installation:
  - Repository: `contents: write`, `pull_requests: write`, `issues: write`, `actions: write`, `metadata: read`, `checks: write`
  - Organization: `members: read`, `administration: write` (System Admin only)

## Limits

- 5000 req/h per PAT; 15000 req/h per GitHub App installation. Comfortably
  under for current workload, but per-installation limits apply once we
  fan out across managed projects.

## Notes

- A new managed-project onboarding flow MUST create the GitHub org (or
  use one provided by the user), install the Coder GitHub App, and create
  the project's `{project}-coder-system` knowledge repo from the
  [`template/`](../../template/) blueprint before any worker acts on it.
- Coder's own repos NEVER live under a managed project's org, and vice
  versa. The boundary is strict.

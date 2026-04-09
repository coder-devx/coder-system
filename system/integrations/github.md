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

The two callers inside `coder-core` now hold tokens in **two separate secrets**, even though they currently share the same underlying PAT value.

| Secret | Loaded by | How | Current scopes |
|---|---|---|---|
| `coder-coder-github-pat` | knowledge API (`src/coder_core/integrations/github.py`) | Cloud Run env var `GITHUB_TOKEN` mounted via `--update-secrets=GITHUB_TOKEN=coder-coder-github-pat:N`. Pinned to a specific version because Cloud Run doesn't re-read `:latest` on running instances; pinning makes each rotation force a fresh revision. | Fine-grained, `coder-devx/{coder-core,coder-admin,coder-system}`, `Contents: Read and write`, `Pull requests: Read and write`, `Metadata: Read`. Inherits write scopes from the worker rotation pending the narrow-PAT follow-up below. |
| `coder-coder-github-pat-worker` | developer worker / dispatcher (`src/coder_core/workers/workspace.py`) | Loaded at task pickup time via `gcloud secrets versions access latest` through the Secret Manager API (no env-var mount, no pinning needed — every task fetches latest). The token is then written into a per-task `$HOME/.netrc` and `$GH_TOKEN`, so `git clone`, `git push`, and `gh pr create` authenticate without ever putting the token on a command line. | Same fine-grained PAT (Contents + PRs read/write) — populated from `coder-coder-github-pat:4` on 2026-04-09 to bootstrap the split. |

- The runtime service account `coder-core-sa@vibedevx.iam` has `roles/secretmanager.secretAccessor` **scoped only to those two secrets** (not project-wide).
- Earlier broad classic scopes (`admin:org`, `repo`, `workflow`, …) — a holdover from `coder-agent` days — were retired in the 2026-04-09 rotation.
- **Narrow-rotation follow-up:** The knowledge-API secret (`coder-coder-github-pat`) doesn't actually need write scopes — only the worker does. Once a fine-grained read-only PAT is minted (`Contents: Read`, `Metadata: Read`, same three repos), pipe it through `scripts/rotate-github-pat.sh` to rotate `coder-coder-github-pat` down to read-only. The worker secret is unaffected. After that, the knowledge API runs with the principle of least privilege and worker compromise can no longer leak read access from a different code path.
- The convention `coder-{project_id}-github-pat-worker` is the new default for the per-project secret template (`coder_core.config.project_github_token_secret_template`). When we onboard a second managed project, its worker secret will follow the same `…-worker` suffix and get its own `…-github-pat` (read-only) for the same reasons.

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

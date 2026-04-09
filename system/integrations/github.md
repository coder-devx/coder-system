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

### Current state (as of commit #4 · 2026-04-08)

- **Classic PAT fallback** — `coder-coder-github-pat` in `vibedevx` Secret Manager, mounted into `coder-core` as env var `GITHUB_TOKEN` via `--update-secrets=GITHUB_TOKEN=coder-coder-github-pat:N`. Cloud Run is **pinned to a specific version**, not `:latest`, because Cloud Run doesn't re-read `:latest` on running instances — pinning makes each rotation force a fresh revision.
- The runtime service account `coder-core-sa@vibedevx.iam` has `roles/secretmanager.secretAccessor` **scoped only to `coder-coder-github-pat`** (not project-wide).
- A legacy secret `GITHUB_TOKEN` from `coder-agent` days still exists in Secret Manager but is orphaned — Cloud Run doesn't reference it and the runtime SA no longer has access to it. Safe to delete once the new secret is proven.
- **Scope problem**: the PAT currently stored has extremely broad classic scopes (`admin:org`, `repo`, `workflow`, `admin:repo_hook`, …). This is a holdover from `coder-agent`. **Security follow-up:** rotate it to a fine-grained PAT scoped to `coder-devx/coder-system:contents:read` before we onboard any managed project that isn't VibeTrade. The mechanics are already in place — see the rotation workflow below.
- Used by: the knowledge API in `coder-core` (`src/coder_core/integrations/github.py`) reads repo file contents via the `Accept: application/vnd.github.raw` trick on `GET /repos/{org}/{repo}/contents/{path}`.

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

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

- **Classic PAT fallback** — `GITHUB_TOKEN` in `vibedevx` Secret Manager, mounted into `coder-core` via `--set-secrets=GITHUB_TOKEN=GITHUB_TOKEN:latest` at deploy time.
- The runtime service account `coder-core-sa@vibedevx.iam` has `roles/secretmanager.secretAccessor` **scoped only to the `GITHUB_TOKEN` secret** (not project-wide).
- **Scope problem**: the current PAT has extremely broad classic scopes (`admin:org`, `repo`, `workflow`, `admin:repo_hook`, …). This is a holdover from `coder-agent`. **Security follow-up:** rotate it to a fine-grained PAT scoped to `coder-devx/coder-system:contents:read` before we onboard any managed project that isn't VibeTrade. Best moment is the GitHub App migration — same change, same test cycle.
- Used by: the knowledge API in `coder-core` (`src/coder_core/integrations/github.py`) reads repo file contents via the `Accept: application/vnd.github.raw` trick on `GET /repos/{org}/{repo}/contents/{path}`.

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

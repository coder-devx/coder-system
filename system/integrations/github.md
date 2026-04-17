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
last_verified_at: 2026-04-09
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

Coder Core authenticates to GitHub as a **GitHub App**. There are no
PATs anywhere in the system. The same app identity covers both
read paths (knowledge API fetching files from a project's knowledge
repo) and write paths (developer worker cloning, pushing branches,
opening PRs).

The app is owned by the `@coder-devx` user account on github.com. App
ID: `3325027`. Source of truth for app config is GitHub's app settings
page; this doc records the operational facts you need to reason about
the running system.

### Token lifecycle

  1. Coder Core holds the app's RSA private key in
     `coder-github-app-private-key` (vibedevx Secret Manager). Mounted
     into Cloud Run as the `GITHUB_APP_PRIVATE_KEY` env var alongside
     `GITHUB_APP_ID=3325027`.
  2. When the knowledge API or the developer worker needs to call
     GitHub for an `(owner, repo)`, `coder_core.integrations.github_app.GitHubAppTokenProvider`:
     - signs an "app JWT" with the private key (RS256, 9-minute expiry,
       `iss=app_id`),
     - looks up the installation id for `owner` via
       `GET /repos/{owner}/{repo}/installation` (cached per-owner for
       the process lifetime; installation ids are stable),
     - exchanges the JWT for an **installation token** via
       `POST /app/installations/{id}/access_tokens` (cached per
       installation until ~5 minutes before its ~1h expiry).
  3. The knowledge API uses the installation token in an
     `Authorization: Bearer …` header on a per-request basis. The
     developer worker writes the same token into a per-task
     `$HOME/.netrc` and `$GH_TOKEN` so `git clone`, `git push`, and
     `gh pr create` authenticate without ever putting the token on a
     command line.

There is **no rotation chore**. The only credential is the app private
key, which has no expiry. If the key is ever compromised, generate a
new one from the app's settings page, replace
`coder-github-app-private-key` with `gcloud secrets versions add`, and
Cloud Run picks it up on the next revision (or immediately on a
restart, since the secret is mounted from `:latest`).

### Installations

The app currently has three installations, all minted automatically
the first time `get_token_for_repo` was called for each owner:

| Installation | Account | Type | Scope |
|---|---|---|---|
| 122610957 | `coder-devx` | User | All repos |
| 122611031 | `acordly` | Organization | All repos |
| 122611051 | `ViberTrade` | Organization | Selected repos |

Onboarding a new managed project = ask the operator to install the
Coder DevX app on their GitHub account/org and grant access to the
project's repos. There is no per-project secret to mint, no env var to
add, no Cloud Run redeploy. Coder Core discovers the new installation
on its first API call to that owner.

### Permissions

Set on the app itself in github.com → Settings → Developer settings →
GitHub Apps → Coder DevX. Current per-installation permissions:

  * Repository: `contents: read+write`, `pull_requests: read+write`,
    `issues: read+write`, `metadata: read`.

Adding a new permission requires editing the app and then **each
installation must accept the permission update** before the new scope
is granted — GitHub holds installations at the version they were
installed at until the operator clicks "Review request".

### Rate limits

Per-installation: 15,000 requests/hour, vs. 5,000/hour for a single
PAT. Each installation gets its own bucket, so fanning out across
managed projects scales linearly with no per-app coordination needed.

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

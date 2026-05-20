---
id: github-branch-protection
title: GitHub branch protection — enforce, verify, and restore
type: runbook
status: active
owner: ro
created: 2026-05-20
updated: 2026-05-20
applies_to_services: []
applies_to_integrations: [github]
last_verified_at: 2026-05-20
---

# GitHub branch protection — enforce, verify, and restore

## Purpose

Documents the branch-protection enforcement for coder-core/main,
coder-admin/main, and coder-system/main per spec 0089. The sync workflow
in `coder-core/.github/workflows/branch-protection-sync.yml` applies these
rules automatically on every push to coder-core/main.

Required rules on each repo's `main` branch:

- At least 1 approving pull-request review
- `enforce_admins: true` (admins cannot bypass)
- No direct-push bypass actors (empty `restrictions`)

## When to run this

- **Bootstrap**: first-time wiring of branch protection on a new or restored repo.
- **Emergency restore**: live protection rules are found to be missing or
  weakened (e.g. the sync workflow lost its token, an admin manually loosened
  a rule).
- **Verification**: routine AC1/AC3 spot-checks, or after any change to
  `.github/branch-protection.yml` in coder-core.

## Who can run this

Org admin (or anyone with `administration: write` on the target repos).

## Prerequisites

### Required GitHub Actions secrets

An org admin must provision these before the automated sync workflow can function:

| Secret | Value | Where to set |
|---|---|---|
| `BRANCH_PROTECTION_ADMIN_TOKEN` | Fine-grained PAT with `administration: write` on coder-core, coder-admin, coder-system | **coder-core** repo secrets (where the sync workflow lives) |
| `WORKER_BOT_TOKEN` | The `coder-coder@vibedevx.com` bot's PAT (same credential as `coder-coder-github-pat` in Secret Manager) | **Each of** coder-core, coder-admin, coder-system repo secrets |

## Steps

### Applying protection manually (bootstrap or emergency restore)

For each of coder-core, coder-admin, coder-system — substitute `{repo}` with the repo name:

```bash
gh api repos/coder-devx/{repo}/branches/main/protection --method PUT --input - << 'EOF'
{"required_pull_request_reviews":{"required_approving_review_count":1,"dismiss_stale_reviews":false,"require_code_owner_reviews":false},"enforce_admins":true,"restrictions":{"users":[],"teams":[],"apps":[]},"required_status_checks":null}
EOF
```

Run for each repo:

```bash
for repo in coder-core coder-admin coder-system; do
  echo "=== $repo ==="
  gh api repos/coder-devx/$repo/branches/main/protection --method PUT --input - << 'EOF'
{"required_pull_request_reviews":{"required_approving_review_count":1,"dismiss_stale_reviews":false,"require_code_owner_reviews":false},"enforce_admins":true,"restrictions":{"users":[],"teams":[],"apps":[]},"required_status_checks":null}
EOF
done
```

### Verifying live state (AC1)

```bash
for repo in coder-core coder-admin coder-system; do
  echo "=== $repo ==="
  gh api repos/coder-devx/$repo/branches/main/protection \
    | jq '{enforce_admins: .enforce_admins.enabled, required_reviews: .required_pull_request_reviews.required_approving_review_count}'
done
```

Expected output for each repo:

```json
{
  "enforce_admins": true,
  "required_reviews": 1
}
```

### Checking bypass actors (AC3)

```bash
for repo in coder-core coder-admin coder-system; do
  echo "=== $repo ==="
  gh api repos/coder-devx/$repo/branches/main/protection | jq '.restrictions'
done
```

Must return `{"url":"...","users":[],"teams":[],"apps":[]}` (all lists empty) for each repo. Any non-empty list is a bypass actor that must be removed.

## Drift detection

The sync workflow in coder-core emits `::warning::` on PRs if live settings
differ from `.github/branch-protection.yml`. If drift warnings appear in CI
but the workflow has the correct token, re-apply the protection rules manually
(see above) and re-trigger the sync workflow.

## Success condition

`verify live state` returns `enforce_admins: true` and `required_reviews: 1`
for all three repos; `check bypass actors` returns empty lists for all three repos.

## If something goes wrong

- **`gh api` returns 404**: the caller lacks `administration: read` — confirm
  the PAT scope or switch to an org admin token.
- **`gh api` PUT returns 422**: the payload is malformed or a required field is
  missing. Validate the JSON and retry.
- **Sync workflow fails with "Bad credentials"**: `BRANCH_PROTECTION_ADMIN_TOKEN`
  is expired or was rotated. Replace it in coder-core repo secrets and re-run
  the workflow.
- **Bypass actor list is non-empty after PUT**: GitHub occasionally preserves
  app entries from previous configurations. Re-issue the PUT with the explicit
  empty `restrictions` payload above to clear them.

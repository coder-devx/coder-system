---
id: github-branch-protection
title: GitHub branch-protection — provision, verify, and restore
type: runbook
status: active
owner: ro
created: 2026-05-20
updated: 2026-05-20
last_verified_at: 2026-05-20
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [github]
---

# GitHub branch-protection — provision, verify, and restore

Documents the branch-protection enforcement for coder-core/main,
coder-admin/main, and coder-system/main per spec 0089. The sync
workflow in `coder-core/.github/workflows/branch-protection-sync.yml`
applies these rules automatically on every push to coder-core/main;
this runbook covers the secrets that workflow needs, how to apply
rules manually (bootstrap or emergency restore), and how to verify
the live state.

## When to run this

- First-time provisioning of branch-protection rules on a new repo.
- Emergency restore after rules are accidentally removed or relaxed.
- After a repo transfer or settings reset wipes the rules.

## Who can run this

Org admin with `administration: write` on coder-core, coder-admin,
and coder-system (or a fine-grained PAT with that scope).

## Prerequisites

- GitHub CLI (`gh`) authenticated as an org admin.
- The two secrets listed below provisioned in the relevant repos.

## Required GitHub Actions secrets

An org admin must provision these once; the sync workflow reads them
at runtime.

**`BRANCH_PROTECTION_ADMIN_TOKEN`** — fine-grained PAT with
`administration: write` on coder-core, coder-admin, and coder-system.
Set as a secret in the **coder-core** repo only (that is where the
sync workflow lives).

**`WORKER_BOT_TOKEN`** — the `coder-coder@vibedevx.com` bot's PAT
(same credential as `coder-coder-github-pat` in Secret Manager). Set
as a GitHub Actions secret in **each of** coder-core, coder-admin,
and coder-system, so any per-repo workflow can reference it.

## Steps

### 1. Apply protection (bootstrap or emergency restore)

Run the following for each of the three repos (`coder-core`,
`coder-admin`, `coder-system`):

```bash
gh api repos/coder-devx/{repo}/branches/main/protection --method PUT --input - << 'EOF'
{"required_pull_request_reviews":{"required_approving_review_count":1,"dismiss_stale_reviews":false,"require_code_owner_reviews":false},"enforce_admins":true,"restrictions":{"users":[],"teams":[],"apps":[]},"required_status_checks":null}
EOF
```

Replace `{repo}` with `coder-core`, `coder-admin`, and `coder-system`
in turn. The call is idempotent — safe to re-run at any time.

### 2. Verify live state (AC1)

```bash
gh api repos/coder-devx/{repo}/branches/main/protection \
  | jq '{enforce_admins: .enforce_admins.enabled, required_reviews: .required_pull_request_reviews.required_approving_review_count}'
```

Expected output:

```json
{
  "enforce_admins": true,
  "required_reviews": 1
}
```

### 3. Check bypass actors (AC3)

```bash
gh api repos/coder-devx/{repo}/branches/main/protection | jq '.restrictions'
```

Must return empty lists:

```json
{
  "url": "...",
  "users": [],
  "teams": [],
  "apps": []
}
```

Any non-empty list means an actor can push directly to main without
a PR — investigate and remove before closing the incident.

## Drift detection

The sync workflow in coder-core (`branch-protection-sync.yml`) emits
`::warning::` annotations on PRs when the live settings differ from
the rules declared in `.github/branch-protection.yml`. If those
warnings appear in CI, run Step 1 above to restore the canonical
settings.

## Success condition

- `gh api repos/coder-devx/{repo}/branches/main/protection` returns
  `enforce_admins.enabled: true` and
  `required_pull_request_reviews.required_approving_review_count: 1`
  for all three repos.
- `.restrictions.users`, `.restrictions.teams`, and
  `.restrictions.apps` are all empty lists on all three repos.

## If something goes wrong

- **`gh api` returns 404** — you are not authenticated as an org
  admin. Run `gh auth login` with the right account or pass
  `--token` with the admin PAT.
- **PUT succeeds but `enforce_admins` is still false** — the GitHub
  API silently ignores `enforce_admins` for non-admin callers. Use
  the admin PAT, not the worker bot token.
- **Restrictions show a non-empty user or app list** — a previous
  bypass exception was added. Remove it via
  `gh api repos/coder-devx/{repo}/branches/main/protection/restrictions/users --method DELETE`
  (or `apps` / `teams` as appropriate).
- **Sync workflow emits warnings on every PR** — the
  `branch-protection.yml` config in coder-core is out of sync with
  what was applied manually. Update `branch-protection.yml` to
  match, or re-apply Step 1 to bring the live state back to the
  config file.

## Related

- Spec: [0089 — branch-protection enforcement on coder-core/main](../product-specs/wip/0089-branch-protection-enforcement-on-coder-core-main.md)

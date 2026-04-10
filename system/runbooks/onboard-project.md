---
id: onboard-project
title: Onboard a new project to coder-core
type: runbook
status: active
owner: ro
created: 2026-04-10
updated: 2026-04-10
applies_to_services: [coder-core]
applies_to_integrations: [gcp, github]
---

# Onboard a new project to coder-core

## When to run this

A new project needs to run developer tasks through coder-core. This
runbook creates the GCP secrets, registers the project in the API,
wires up the knowledge repo, and verifies the full loop.

## Who can run this

- **GCP**: `coder@vibedevx.com` with `secretmanager.admin` on `vibedevx`
  and `tofu apply` access to the Terraform state bucket.
- **GitHub**: an owner of the target GitHub org (to install/configure the
  Coder DevX GitHub App).
- **coder-core**: anyone with network access (project creation is
  unauthenticated in v1).

## Prerequisites

- OpenTofu installed (`brew install opentofu`).
- `gcloud` authed as `coder@vibedevx.com`.
- `gh` CLI authed with access to the target org.
- An Anthropic API key for the project (can share the org-wide key).
- The Coder DevX GitHub App installed on the target GitHub org.

## Steps

### 1. Add the project to Terraform

Edit `coder-core/infra/terraform/variables.tf` and append the project
id (kebab-case) to `var.projects`:

```hcl
default = ["vibetrade", "coder", "new-project"]
```

Preview and apply:

```sh
cd coder-core/infra/terraform
tofu plan    # expect: 2 new resources (secret + IAM binding)
tofu apply
```

This creates:
- `coder-{project}-developer-anthropic-api-key` in Secret Manager
- Per-secret `secretAccessor` binding for `coder-developer@`

### 2. Upload the Anthropic API key

```sh
gcloud secrets versions access latest --secret=ANTHROPIC_API_KEY \
  --project=vibedevx \
  | gcloud secrets versions add coder-{project}-developer-anthropic-api-key \
      --data-file=- --project=vibedevx
```

Or from a local file / clipboard:

```sh
gcloud secrets versions add coder-{project}-developer-anthropic-api-key \
  --data-file=<(pbpaste) --project=vibedevx
```

### 3. Register the project in coder-core

```sh
PROD=https://coder-core-ql732k45va-ew.a.run.app

curl -s -X POST "$PROD/v1/projects" \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "{project}",
    "name": "Human-Readable Name",
    "github_org": "{GitHubOrg}",
    "knowledge_repo": "{project}-coder-system",
    "gcp_project": "vibedevx",
    "owner": "ro@vibedevx.com"
  }' | python3 -m json.tool
```

**Save the `api_key` from the response** — it's shown once. Store it in
Secret Manager for persistence:

```sh
echo -n "ck_..." | gcloud secrets create coder-{project}-api-key \
  --data-file=- --project=vibedevx
```

Also save it locally for CLI impersonation:

```sh
mkdir -p ~/.config/coder/projects
echo "ck_..." > ~/.config/coder/projects/{project}.key
chmod 600 ~/.config/coder/projects/{project}.key
```

### 4. Create the knowledge repo

```sh
gh repo create {GitHubOrg}/{project}-coder-system --private \
  --description "{Project} knowledge base for Coder agents"

# Clone and populate from the template
git clone git@github.com:{GitHubOrg}/{project}-coder-system.git /tmp/{project}-coder-system
cp -r coder-system/template/* /tmp/{project}-coder-system/
cp -r coder-system/template/.cursor /tmp/{project}-coder-system/
cd /tmp/{project}-coder-system
git add -A && git commit -m "Initial knowledge base from template" && git push -u origin main
```

### 5. Add the repo to the GitHub App

Go to: `https://github.com/organizations/{GitHubOrg}/settings/installations`

Click **Coder DevX** → add `{project}-coder-system` to the selected
repositories (or switch to "All repositories" if appropriate).

### 6. Verify the knowledge API

```sh
API_KEY="ck_..."
curl -s "$PROD/v1/projects/{project}/knowledge/specs" \
  -H "X-Api-Key: $API_KEY" | python3 -m json.tool
```

Should return the empty-but-valid registry from the template.

### 7. Test a developer task

```sh
curl -s -X POST "$PROD/v1/projects/{project}/tasks" \
  -H "X-Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "developer",
    "repo": "{repo-name}",
    "prompt": "Add a one-line comment to README.md saying this repo is managed by Coder."
  }' | python3 -m json.tool
```

Poll until the task reaches `succeeded`:

```sh
TASK_ID="..."
curl -s "$PROD/v1/projects/{project}/tasks/$TASK_ID" \
  -H "X-Api-Key: $API_KEY" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(f'status={d[\"status\"]} commit={d.get(\"commit_sha\",\"—\")}')"
```

### 8. Verify in the admin panel

Open `https://coder-admin.vibedevx.com` (or local dev), navigate to the
project, and confirm the task appears in the pipeline view with status,
logs, and commit link.

### 9. Test impersonation (spec 0007)

```sh
coder impersonate developer --project={project} \
  --base-url=https://coder-core-ql732k45va-ew.a.run.app

coder status   # should show role, project, expiry
```

### 10. Commit the Terraform changes

```sh
cd coder-core
python3 infra/terraform/capability_matrix.py --write
git add infra/terraform/variables.tf infra/terraform/CAPABILITY_MATRIX.md
git commit -m "infra: onboard {project} to var.projects"
git push
```

## Success condition

- `GET /v1/projects/{project}` returns the project.
- `GET /v1/projects/{project}/knowledge/specs` returns registry entries.
- A developer task runs to `succeeded` with a commit SHA.
- The task appears in the admin pipeline view.
- `coder impersonate developer --project={project}` mints a token.

## If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `tofu apply` fails with "secret already exists" | Project was partially onboarded before | `tofu import google_secret_manager_secret.project_anthropic_key["{project}"] projects/vibedevx/secrets/coder-{project}-developer-anthropic-api-key` |
| Knowledge API returns `github_auth` error | GitHub App not installed or repo not in selected list | Add the repo at `https://github.com/organizations/{Org}/settings/installations` |
| Task stays `queued` forever | Dispatcher not running or Anthropic key missing | Check Cloud Run logs: `gcloud run services logs read coder-core --project=vibedevx --region=europe-west1 --limit=50` |
| Task fails with `SecretReadError` | Anthropic key version not uploaded | `gcloud secrets versions list coder-{project}-developer-anthropic-api-key --project=vibedevx` — if 0 versions, upload one per step 2 |
| 500 on task endpoints | Missing DB migration | Run `alembic upgrade head` per [`run-migration-coder-core.md`](./run-migration-coder-core.md) |
| Impersonation returns 422 "unknown_role" | Role not in dispatcher's `_RUNNERS` | Only `developer` is supported in v1 |

## Notes

- **First onboarded:** `coder` (2026-04-08, already existed), `vibetrade`
  (2026-04-10, this runbook was written during its onboarding).
- **API keys are shown once.** Store them in Secret Manager immediately.
- **GitHub App is already installed** on `coder-devx`, `ViberTrade`, and
  `acordly`. New orgs need the app installed first — go to the app's
  public page and click Install.

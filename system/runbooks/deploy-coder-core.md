---
id: deploy-coder-core
title: Deploy coder-core to Cloud Run
type: runbook
status: active
owner: ro
created: 2026-04-08
updated: 2026-04-11
last_verified_at: 2026-04-12
applies_to_services: [coder-core]
applies_to_integrations: [gcp, github]
---

# Deploy coder-core to Cloud Run

## When to run this

You want to ship a new revision of `coder-core`. **The normal path is to
merge to `main` and let CI deploy** — see [Automatic deploy](#automatic-deploy).
A manual escape hatch is documented at the bottom for break-glass cases when
GitHub Actions is unavailable.

## What gets deployed

| Thing | Value |
|---|---|
| Service name | `coder-core` |
| GCP project | `vibedevx` |
| Region | `europe-west1` |
| Runtime SA | `coder-core-sa@vibedevx.iam.gserviceaccount.com` |
| Image | `europe-west1-docker.pkg.dev/vibedevx/coder-core/coder-core:{git-sha}` (also tagged `:latest`) |
| Port | 8080 |
| Memory / CPU | 512 MiB / 1 vCPU |
| Min / max instances | 0 / 3 |
| Env vars | `ENVIRONMENT`, `CLOUD_SQL_INSTANCE`, `CLOUD_SQL_USER`, `CLOUD_SQL_DATABASE`, plus `GITHUB_TOKEN` from Secret Manager (`coder-coder-github-pat`) |
| Cloud SQL | `vibedevx:europe-west1:coder-core-db` |
| Ingress | `allow-unauthenticated` (knowledge endpoints gate themselves with `X-Api-Key`) |

CI only updates the **image**. Everything else (env vars, secret mounts,
Cloud SQL connection, scaling, runtime SA) is preserved by using
`gcloud run services update --image=…` rather than `gcloud run deploy`. If
you need to change one of those, do it manually with `gcloud run services
update` and document the change.

| Thing | Value |
|---|---|
| Migration job | `coder-core-migrate` (Cloud Run Job, same region/project) |
| Migration command | `alembic upgrade head` |
| Migration SA | `coder-core-sa` (reuses runtime SA with Cloud SQL IAM auth) |

## Automatic deploy

The pipeline lives in [`coder-core/.github/workflows/ci.yml`](https://github.com/coder-devx/coder-core/blob/main/.github/workflows/ci.yml).

Trigger:

```sh
# from the coder-core repo
git push origin main
```

Pipeline stages:

1. **check** — `ruff`, `ruff format --check`, `mypy`, `pytest`. Runs on
   every PR and every push.
2. **build** — builds the image with Buildx + GHA cache. On PRs the image
   is loaded but not pushed (smoke-checks the Dockerfile). On main pushes
   the image is pushed to Artifact Registry tagged with the 12-char git
   SHA and `:latest`.
3. **deploy** (main only) — canary pattern:
   1. Deploy the new image as a Cloud Run revision with **0% traffic**
      (`--no-traffic --tag=canary`).
   2. Health-check the canary revision via its tagged URL
      (`https://canary---coder-core-…/v1/health`), retrying up to 5 times.
   3. Run Alembic migrations via the `coder-core-migrate` Cloud Run Job
      (same image, runtime SA, Cloud SQL IAM auth).
   4. Shift 100% traffic to the canary revision, then normalise to
      "route to latest" and remove the canary tag.
   5. Send a Slack notification (success or failure) if the
      `SLACK_DEPLOY_WEBHOOK_URL` variable is set.

   If the health check or migration fails, the traffic-shift step never
   runs — the previous revision keeps serving with zero downtime.

GitHub auths to GCP via Workload Identity Federation:

| Thing | Value |
|---|---|
| Pool | `projects/8534948335/locations/global/workloadIdentityPools/github-pool` |
| Provider | `…/providers/github-provider` (OIDC, scoped to `coder-devx` org) |
| Deploy SA | `gha-deployer@vibedevx.iam.gserviceaccount.com` |
| Repo binding | `principalSet://…/attribute.repository/coder-devx/coder-core` → `roles/iam.workloadIdentityUser` on `gha-deployer` |
| Roles on `gha-deployer` | `roles/run.developer`, `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser` (on `coder-core-sa`), plus the legacy `cloudbuild.builds.editor`, `logging.logWriter`, `serviceusage.serviceUsageConsumer`, `storage.objectUser` |

There are **no long-lived deploy keys** anywhere — GitHub mints a
short-lived OIDC token per run and exchanges it for a GCP access token
via WIF.

### Watching a deploy

```sh
gh run list --limit 5
gh run watch <run-id>
```

Or in the browser: <https://github.com/coder-devx/coder-core/actions>.

### Success condition

The `Health check canary` step hits the tagged canary URL and prints:

```
{"ok":true,"service":"coder-core","version":"X.Y.Z","environment":"prod"}
```

The `Run database migrations` step completes without error. The
`Shift traffic to new revision` step moves 100% to the new revision.

Confirm in the Cloud Run console:
<https://console.cloud.google.com/run/detail/europe-west1/coder-core/metrics?project=vibedevx>

## Rollback

Revert to a previous revision (no rebuild needed):

```sh
# List revisions
gcloud run revisions list \
  --service=coder-core \
  --project=vibedevx \
  --region=europe-west1

# Route 100% traffic to a previous revision
gcloud run services update-traffic coder-core \
  --project=vibedevx \
  --region=europe-west1 \
  --to-revisions=coder-core-00006-qsr=100
```

If the bad revision came from a bad commit, also revert the commit on
`main` so the next push doesn't redeploy it.

## Manual escape hatch (`make deploy`)

Use this **only** when GitHub Actions is unavailable or you need to deploy
an uncommitted local image (debugging the runtime, not normal flow).

### Who can run it

- `coder@vibedevx.com` gcloud login with `roles/run.admin`,
  `roles/iam.serviceAccountUser` on `coder-core-sa`, and
  `roles/artifactregistry.writer` in `vibedevx`
- `uv` and `podman` installed locally

### Steps

```sh
# 1. Verify what you're shipping
git status
git log --oneline -5
make check

# 2. Authenticate podman against Artifact Registry (short-lived token)
make ar-login

# 3. Build, tag, push, deploy, smoke-test — all in one
make deploy
```

The exact flags are in the `deploy` target of [`Makefile`](https://github.com/coder-devx/coder-core/blob/main/Makefile).

> ⚠ `make deploy` uses `gcloud run deploy` with explicit env-var flags,
> which **replaces** the env-var set on the service. If you've changed
> env vars or secret mounts via `gcloud run services update` since the
> Makefile was last edited, `make deploy` will silently lose them.
> Reconcile by editing the Makefile target before using it.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| GitHub Action fails at "Authenticate to GCP" with `Permission 'iam.serviceAccounts.getAccessToken' denied` | The repo isn't bound to `gha-deployer` via WIF, or the binding is on a different repo path | `gcloud iam service-accounts get-iam-policy gha-deployer@vibedevx.iam.gserviceaccount.com` and confirm the principalSet for `coder-devx/coder-core` is present |
| `gcloud run services update` returns "Permission denied" on `iam.serviceAccounts.actAs` | `gha-deployer` lacks `iam.serviceAccountUser` on `coder-core-sa` | Re-grant: `gcloud iam service-accounts add-iam-policy-binding coder-core-sa@vibedevx.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser --member=serviceAccount:gha-deployer@vibedevx.iam.gserviceaccount.com` |
| Build push to AR returns 403 | `gha-deployer` lacks `roles/artifactregistry.writer` | Re-grant the role on `vibedevx` |
| Deploy succeeds but `/v1/health` returns 500 | App crashed at startup | `gcloud run services logs read coder-core --project=vibedevx --region=europe-west1 --limit=100` |
| `/v1/health` returns the OLD revision's output | Traffic didn't route to the new revision | `gcloud run services describe coder-core --project=vibedevx --region=europe-west1 --format='value(status.traffic)'` and route traffic with `update-traffic` |
| Manual `podman push` returns 403 | gcloud token expired | `make ar-login` again |
| Image pulled but container won't start ("manifest unknown") | Arch mismatch — image not built as `linux/amd64` | Rebuild with `--platform linux/amd64` (Makefile `build` target and CI both do this) |

## Notes

- **Canary deploy pattern:** added in spec 0011. Deploys with 0%
  traffic, health-checks, migrates, then shifts. See the workflow for
  details.
- **First deployment** (2026-04-08): `coder-core-00001-9lp` — v0.0.1
  walking skeleton, `GET /v1/health` only.
- **Runtime SA roles** (`coder-core-sa`): `roles/logging.logWriter`,
  `roles/monitoring.metricWriter`, `roles/cloudsql.client`,
  `roles/cloudsql.instanceUser`, plus
  `roles/secretmanager.secretAccessor` scoped to the
  `coder-coder-github-pat` secret only. Add roles in the same commit that
  adds the feature — never preemptively.

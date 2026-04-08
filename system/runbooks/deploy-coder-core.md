---
id: deploy-coder-core
title: Deploy coder-core to Cloud Run (manual)
type: runbook
status: active
owner: ro
created: 2026-04-08
updated: 2026-04-08
applies_to_services: [coder-core]
applies_to_integrations: [gcp]
---

# Deploy coder-core to Cloud Run (manual)

## When to run this

You want to ship a new revision of `coder-core`. This is the **manual**
deploy path, used until push-to-main CD lands (commit #5 of
[design 0004](../designs/wip/0001-generalize-coder-from-vibetrade.md)).

## Who can run this

Anyone with:

- `coder@vibedevx.com` gcloud login with the following roles in `vibedevx`:
  - `roles/run.admin`
  - `roles/iam.serviceAccountUser`
  - `roles/artifactregistry.writer`
- `uv` and `podman` installed locally
- This repo (`coder-core`) cloned

In practice today, that's the user (`ro`) or the Coder System Admin worker.

## Prerequisites

- Working tree is clean (or at least has no changes you don't want shipped).
- `make check` passes locally (lint, format, typecheck, tests).
- `gcloud auth list` shows `coder@vibedevx.com` as the active account.
- `podman machine` is running.

## What gets deployed

| Thing | Value |
|---|---|
| Service name | `coder-core` |
| GCP project | `vibedevx` |
| Region | `europe-west1` |
| Runtime SA | `coder-core-sa@vibedevx.iam.gserviceaccount.com` |
| Image | `europe-west1-docker.pkg.dev/vibedevx/coder-core/coder-core:{VERSION}` |
| Version | Read from `pyproject.toml` (`project.version`) |
| Port | 8080 |
| Memory / CPU | 512 MiB / 1 vCPU |
| Min / max instances | 0 / 3 |
| Env vars | `ENVIRONMENT=prod` |
| Ingress | `allow-unauthenticated` (for now — `/v1/health` is public; auth comes in commit #4) |

## Steps

From the `coder-core` repo root:

```sh
# 1. Verify you're about to ship what you think you are
git status
git log --oneline -5
make check

# 2. Authenticate podman against Artifact Registry (short-lived token)
make ar-login

# 3. Build, tag, push, deploy, smoke-test — all in one
make deploy
```

`make deploy` runs:

1. `podman build --platform linux/amd64 -t coder-core:dev .`
2. Tag the image as `europe-west1-docker.pkg.dev/vibedevx/coder-core/coder-core:{VERSION}` and `:latest`
3. Push both tags
4. `gcloud run deploy coder-core --image=...:{VERSION} --service-account=coder-core-sa@... ...`
5. `curl https://coder-core-…run.app/v1/health` to confirm 200

The exact flags are in the `deploy` target of [`Makefile`](https://github.com/coder-devx/coder-core/blob/main/Makefile).

## Success condition

The `make deploy` command finishes with:

```
{"ok":true,"service":"coder-core","version":"X.Y.Z","environment":"prod"}
```

Check the service in the Cloud Run console:
<https://console.cloud.google.com/run/detail/europe-west1/coder-core/metrics?project=vibedevx>

The new revision should be serving 100% of traffic within ~30s of the command finishing.

## If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `podman login` fails with "unauthorized" | gcloud token expired | `gcloud auth login --account=coder@vibedevx.com`, retry |
| `podman push` returns 403 | SA lacks `artifactregistry.writer` | Add the role to your user (not the runtime SA) |
| `gcloud run deploy` returns "Permission denied" on `iam.serviceAccounts.actAs` | Your user lacks `iam.serviceAccountUser` on `coder-core-sa` | Add the role or ask a project admin |
| Deploy succeeds but `/v1/health` returns 500 | Image pushed for wrong arch, or app crash at startup | Check `gcloud run services logs read coder-core --project=vibedevx --region=europe-west1 --limit=50` |
| Image pulled but container won't start ("manifest unknown") | Arch mismatch — the image wasn't built as `linux/amd64` | Rebuild with `--platform linux/amd64` (the Makefile's `build` target does this) |
| `/v1/health` returns the OLD revision's output | Traffic didn't route to the new revision | Check `gcloud run services describe coder-core --project=vibedevx --region=europe-west1 --format='value(status.traffic)'` |

## Rollback

Revert to the previous revision:

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
  --to-revisions=coder-core-00001-9lp=100
```

## Notes

- **This runbook will be retired** when push-to-main CD lands in commit #5 of design 0004. After that, `main` merges auto-deploy and this is reserved for break-glass rollbacks.
- **First deployment** (2026-04-08): `coder-core-00001-9lp` — v0.0.1 walking skeleton, `GET /v1/health` only.
- **Service account** `coder-core-sa@vibedevx.iam.gserviceaccount.com` has exactly `roles/logging.logWriter` and `roles/monitoring.metricWriter`. When the service needs Secret Manager, Cloud SQL, etc., add roles in the same commit that adds the feature — never preemptively.

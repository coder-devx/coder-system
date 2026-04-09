---
id: deploy-coder-admin
title: Deploy coder-admin to Cloud Run
type: runbook
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-09
applies_to_services: [coder-admin]
applies_to_integrations: [gcp, github]
---

# Deploy coder-admin to Cloud Run

## When to run this

You want to ship a new revision of `coder-admin`. **The normal path is
to merge to `main` and let CI deploy** — see [Automatic deploy](#automatic-deploy).
A manual escape hatch via the `Makefile` is documented at the bottom.

## What gets deployed

| Thing | Value |
|---|---|
| Service name | `coder-admin` |
| GCP project | `vibedevx` |
| Region | `europe-west1` |
| Runtime SA | `coder-admin-sa@vibedevx.iam.gserviceaccount.com` (no roles — browser-only app) |
| Image | `europe-west1-docker.pkg.dev/vibedevx/coder-admin/coder-admin:{git-sha}` (also tagged `:latest`) |
| Port | 8080 (nginx) |
| Memory / CPU | 256 MiB / 1 vCPU |
| Min / max instances | 0 / 3 |
| Build-time env | `VITE_API_BASE_URL` (baked into the JS bundle from `.env.production`) |
| Ingress | `allow-unauthenticated` (it's a browser app) |

CI uses `gcloud run deploy` (which creates the service on first run and
updates the image on subsequent runs). It passes the runtime SA, port,
memory/CPU, and scaling on every deploy — if you change those values
in the workflow they will take effect on the next push. Unspecified env
vars are preserved by `gcloud run deploy`, so the build-time-only
nature of `VITE_API_BASE_URL` makes this simpler than coder-core.

> ⚠ **`VITE_API_BASE_URL` is build-time, not runtime.** Vite inlines the
> value into the JS bundle at `npm run build`. You cannot change which
> coder-core a deployed bundle talks to by editing Cloud Run env vars —
> you have to rebuild. Per-env values live in `.env.development` and
> `.env.production` in the repo. Use `.env.local` to override locally.

## Automatic deploy

The pipeline lives in [`coder-admin/.github/workflows/ci.yml`](https://github.com/coder-devx/coder-admin/blob/main/.github/workflows/ci.yml).

Trigger:

```sh
# from the coder-admin repo
git push origin main
```

Pipeline stages:

1. **check** — `eslint`, `prettier --check`, `tsc --noEmit`, `vitest run`,
   `vite build`. Runs on every PR and every push.
2. **build** — multi-stage Docker build (`node:22-alpine` builds the
   bundle, `nginx:1.27-alpine` serves it). On PRs the image is loaded
   but not pushed (smoke-checks the Dockerfile). On main pushes the
   image is pushed to Artifact Registry tagged with the 12-char git
   SHA and `:latest`. `VITE_API_BASE_URL` is passed in as a build arg
   from `.env.production`.
3. **deploy** (main only) — `gcloud run deploy coder-admin --image=…:{sha}`,
   then `curl /healthz` and `curl / | grep "Coder Admin"`.

GitHub auths to GCP via Workload Identity Federation:

| Thing | Value |
|---|---|
| Pool | `projects/8534948335/locations/global/workloadIdentityPools/github-pool` |
| Provider | `…/providers/github-provider` (OIDC, scoped to `coder-devx` org) |
| Deploy SA | `gha-deployer@vibedevx.iam.gserviceaccount.com` |
| Repo binding | `principalSet://…/attribute.repository/coder-devx/coder-admin` → `roles/iam.workloadIdentityUser` on `gha-deployer` |
| Roles on `gha-deployer` | `roles/run.developer`, `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser` (on `coder-admin-sa`), shared with the coder-core deploy |

No long-lived deploy keys.

### Watching a deploy

```sh
gh run list --limit 5
gh run watch <run-id>
```

Or in the browser: <https://github.com/coder-devx/coder-admin/actions>.

### Success condition

The smoke-test step prints:

```
HTTP/2 200
ok
```

…and the `index.html` fetch contains `Coder Admin`. Confirm in the
Cloud Run console:
<https://console.cloud.google.com/run/detail/europe-west1/coder-admin/metrics?project=vibedevx>

Then open the service URL in a browser and verify the `coder-core
status` card renders the `service`/`version`/`environment` fields from
`coder-core`.

## Cross-origin gotcha

The browser hits `coder-core` directly. `coder-core` must include this
service's URL in its `CORS_ALLOWED_ORIGINS` env var. After the first
deploy, capture the URL from `gcloud run services describe coder-admin`
and run:

```sh
gcloud run services update coder-core \
  --project=vibedevx \
  --region=europe-west1 \
  --update-env-vars=CORS_ALLOWED_ORIGINS='http://localhost:5173,https://coder-admin-XXXX.europe-west1.run.app'
```

If the browser console shows `Access-Control-Allow-Origin` errors, the
URL probably isn't in that list.

## Rollback

Revert to a previous revision (no rebuild needed):

```sh
gcloud run revisions list \
  --service=coder-admin \
  --project=vibedevx \
  --region=europe-west1

gcloud run services update-traffic coder-admin \
  --project=vibedevx \
  --region=europe-west1 \
  --to-revisions=coder-admin-00003-abc=100
```

If the bad revision came from a bad commit, also revert the commit on
`main` so the next push doesn't redeploy it.

## Manual escape hatch (`make deploy`)

Use this **only** when GitHub Actions is unavailable or you need to
deploy a one-off build (debugging the runtime, not normal flow).

```sh
# 1. Verify what you're shipping
git status
make check

# 2. Authenticate podman/docker against Artifact Registry
make ar-login

# 3. Build, push, deploy, smoke-test
make deploy
```

The exact flags are in the `deploy` target of [`Makefile`](https://github.com/coder-devx/coder-admin/blob/main/Makefile).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| GitHub Action fails at "Authenticate to GCP" | Repo missing WIF binding | `gcloud iam service-accounts get-iam-policy gha-deployer@vibedevx.iam.gserviceaccount.com` and confirm `principalSet` for `coder-devx/coder-admin` |
| Browser shows CORS error talking to coder-core | Admin URL not in `CORS_ALLOWED_ORIGINS` | See [Cross-origin gotcha](#cross-origin-gotcha) |
| Deployed admin still talks to localhost:8080 | `.env.production` not picked up at build time, or build cache stale | Verify `.env.production` is committed; rerun the workflow with cache disabled |
| `nginx: [emerg] host not found in upstream` | The Dockerfile shipped with a stale `nginx.conf` referencing an upstream | The included nginx.conf is static-only — no upstreams. Check the Dockerfile copies `nginx.conf` from the repo |
| `/healthz` returns 200 but `/` is blank | SPA fallback misconfigured or `dist/index.html` missing | Inspect the build stage logs; ensure `npm run build` produced `dist/index.html` |
| Image pulled but container won't start ("manifest unknown") | Arch mismatch | Rebuild with `--platform linux/amd64` (CI does this) |

## Notes

- **First deployment** (2026-04-09): walking skeleton — single page that
  calls `coder-core` `/v1/health` and renders the result. Update this
  line with the revision name once it ships.
- **Runtime SA roles** (`coder-admin-sa`): none. nginx serving static
  files needs no GCP permissions. If we ever add server-side rendering
  or a backend-for-frontend, grant roles in the same commit that adds
  the feature.

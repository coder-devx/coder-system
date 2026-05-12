---
id: founder-calibration-turn-on
title: Founder calibration dogfood — env wiring + scheduler turn-on
type: runbook
status: active
owner: ro
created: 2026-05-12
updated: 2026-05-12
last_verified_at: 2026-05-12
applies_to_services: [coder-core]
applies_to_integrations: [gcp]
---

# Founder calibration dogfood — env wiring + scheduler turn-on

## When to run this

Phase A code is fully shipped (spec 0075/0077/0079/0080 all green on main) and the operator is ready to start the 12-cycle calibration dogfood that closes out Phase A. The Founder Cloud Run Job, its REST API, and the studio admin UI are all deployed but **inert**: `STUDIO_ENABLED=False`, no env vars for `github_org` / `cloudflare_*` / `posthog_*`, no Cloud Scheduler cron jobs.

This runbook flips the switches and verifies the first idea_cycle runs end-to-end. After 12 successful cycles where the operator's approve/kill decisions consistently match the Founder's top picks, Phase B starts.

## Who can run this

`ro` (operator). The steps need:

- `gcloud` auth with `roles/run.admin` + `roles/secretmanager.admin` + `roles/cloudscheduler.admin` on the `vibedevx` GCP project.
- A GitHub admin-JWT in `localStorage['coder-admin:token']` from a fresh Google OAuth login at the admin URL.

## Prerequisites

1. `coder-product-template` repo exists on GitHub (created 2026-05-12 via `gh repo create coder-devx/coder-product-template --private` + `gh api -X PATCH repos/coder-devx/coder-product-template -F is_template=true`).
2. The five scaffold PRs in that repo have merged (PR #1–#5, all on `main` as of 2026-05-12).
3. `coder-core` main has the bootstrap admin endpoint wired (coder-core#233 merged) and the real acknowledge endpoint (coder-core#234 merged).

## Steps

### 1. Provision the Secret Manager secrets

```bash
# Cloudflare API token with DNS:Edit scope on the studio.coder.dev zone.
gcloud secrets create coder-core-cloudflare-api-token --project=vibedevx \
  --replication-policy=automatic --data-file=- < cloudflare-token.txt

# Stripe Connect platform secret key (sk_live_… or sk_test_… for the dogfood).
gcloud secrets create coder-core-stripe-secret-key --project=vibedevx \
  --replication-policy=automatic --data-file=- < stripe-key.txt

# Stripe webhook signing secret (whsec_…).
gcloud secrets create coder-core-stripe-webhook-secret --project=vibedevx \
  --replication-policy=automatic --data-file=- < stripe-webhook-secret.txt
```

Grant the Cloud Run runtime SA `roles/secretmanager.secretAccessor` on each:

```bash
for s in coder-core-cloudflare-api-token coder-core-stripe-secret-key \
         coder-core-stripe-webhook-secret; do
  gcloud secrets add-iam-policy-binding $s --project=vibedevx \
    --member=serviceAccount:coder-core-sa@vibedevx.iam.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
done
```

### 2. Update the `coder-core` Cloud Run service env

```bash
gcloud run services update coder-core --region=europe-west1 --project=vibedevx \
  --update-env-vars=\
STUDIO_ENABLED=true,\
GITHUB_ORG=coder-devx,\
GCP_PROJECT=vibedevx,\
CLOUDFLARE_ZONE_ID=<zone-id-for-studio.coder.dev>,\
POSTHOG_POLL_ENABLED=true \
  --update-secrets=\
CLOUDFLARE_API_TOKEN=coder-core-cloudflare-api-token:latest,\
STRIPE_SECRET_KEY=coder-core-stripe-secret-key:latest,\
STRIPE_WEBHOOK_SECRET=coder-core-stripe-webhook-secret:latest
```

This redeploys with the studio gate open. The new revision serves once the rollout completes (`gcloud run services describe coder-core --region=europe-west1 --format='value(status.latestReadyRevisionName)'`).

### 3. Wire Cloud Scheduler

Two cron jobs trigger the Founder via HTTP POST to the admin endpoint. The scheduler SA needs an admin JWT or a service-account OIDC token that the `_require_admin` helper accepts.

```bash
# Daily idea_cycle at 06:00 UTC.
gcloud scheduler jobs create http coder-core-founder-idea-cycle \
  --location=europe-west1 --project=vibedevx \
  --schedule="0 6 * * *" \
  --time-zone=UTC \
  --uri="https://coder-core-ql732k45va-ew.a.run.app/v1/projects/coder/studio/founder/run?mode=idea_scan" \
  --http-method=POST \
  --oidc-service-account-email=coder-core-scheduler-sa@vibedevx.iam.gserviceaccount.com

# Weekly weekly_review at Sun 18:00 UTC.
gcloud scheduler jobs create http coder-core-founder-weekly-review \
  --location=europe-west1 --project=vibedevx \
  --schedule="0 18 * * 0" \
  --time-zone=UTC \
  --uri="https://coder-core-ql732k45va-ew.a.run.app/v1/projects/coder/studio/founder/run?mode=weekly_review" \
  --http-method=POST \
  --oidc-service-account-email=coder-core-scheduler-sa@vibedevx.iam.gserviceaccount.com
```

If the admin endpoint's `_require_admin` doesn't accept OIDC tokens (current state — it only takes broker-signed admin JWTs), either:

- Add an `iap_audience` claim check to `_require_admin` so OIDC works (small follow-up PR), or
- Issue a long-lived admin JWT and store it in Secret Manager; have a tiny Cloud Function wrapper exchange the scheduler's OIDC for that JWT and forward.

The simpler path for the dogfood is to **kick the cycles manually from the admin UI** via the Founder's `Run cycle now` button. Real scheduler-driven runs are a Phase B concern.

### 4. Kick a manual idea_cycle

From the admin UI: open `https://coder-admin-ql732k45va-ew.a.run.app/projects/coder/studio`, click `Run cycle now → idea_cycle`. Expect HTTP 202 with `{"job_run_id": "...", "status": "started"}`.

Equivalent curl (using the admin JWT from `localStorage['coder-admin:token']`):

```bash
curl -X POST \
  -H "Authorization: Bearer $ADMIN_JWT" \
  "https://coder-core-ql732k45va-ew.a.run.app/v1/projects/coder/studio/founder/run?mode=idea_scan"
```

### 5. Verify the loop

Within ~2 minutes of the kick, the admin panel's Studio mode should show:

- A new row in `founder_job_runs` with `status='succeeded'` and `report_uri` populated.
- New rows in `idea_queue_entries` from the placeholder candidate scorer (3 rows on the first run; subsequent runs are mostly absorbed as duplicates until the real scorer ships).
- The Studio sidebar's `IdeaQueue` component renders the new rows.

If no new rows appear, check the Cloud Run logs:

```bash
gcloud logging read 'resource.labels.service_name="coder-core" AND jsonPayload.logger="coder_core.founder.watch"' \
  --project=vibedevx --limit=50 --freshness=10m
```

## Success condition

12 calibration cycles complete with the operator's `approve` decisions consistently matching the Founder's top-scored idea (≥ 9 of 12 matches). The charter calls this "the Founder agent's idea selection has earned the operator's trust."

## If something goes wrong

| Symptom | Action |
|---|---|
| HTTP 403 `studio_disabled` on `/founder/run` | Step 2 wasn't applied — verify `STUDIO_ENABLED=true` on the latest revision. |
| HTTP 503 `bootstrap_unconfigured` on `/studio/bootstrap` | Step 1+2 missed one of `github_org`, `gcp_project`, `cloudflare_api_token`, `cloudflare_zone_id`. |
| Founder run returns 202 but no `founder_job_runs` row appears | Check the Cloud Run logs for `founder.run_auth_failed` or `founder.run_api_error`. Common causes: missing `coder-core-sa` permissions on `iamcredentials.googleapis.com`, or the `coder-core-founder` job hasn't been deployed yet. |
| `idea_queue_entries` rows always absorbed as duplicates | The placeholder scorer in `coder_core.workers.founder._PLACEHOLDER_IDEAS` has 3 fixed strings; their hashes collide on second run by design. This is the expected behaviour until the real scorer lands. |
| Founder report mentions no b2c_product projects | No `projects` row has `project_kind='b2c_product'`. Create one via the admin panel or `POST /v1/projects` with `project_kind=b2c_product`. |
| Operator approve decisions diverge from Founder picks | Calibration is working as intended — that's what the dogfood measures. Document the divergence in the project_studio_phase_a memory note. Phase B does not start until ≥9 of 12 match. |

---
id: oauth-mcp-clients-rollout
title: OAuth 2.1 for MCP clients — staged rollout
type: runbook
status: active
owner: ro
created: 2026-04-25
updated: 2026-04-25
last_verified_at: 2026-04-25
applies_to_services: [coder-core]
applies_to_integrations: [gcp]
---

# OAuth-for-MCP-clients rollout

The OAuth 2.1 surface for MCP clients (spec 0050) is deployed on
`coder-core` and flag-gated on `MCP_OAUTH_ENABLED`. This runbook
covers the operator setup that has to land **before** the flag flip
(Google OAuth client + secret), the staged rollout itself, and the
manual claude.ai end-to-end smoke that closes out AC10.

Product view:
[spec 0050](../product-specs/wip/0050-oauth-for-mcp-clients.md).
Design: [design 0050](../designs/wip/0050-oauth-for-mcp-clients.md).
This runbook is the OAuth-equivalent of
[mcp-agent-interface-rollout](./mcp-agent-interface-rollout.md) —
same fleet-flag-then-canary pattern, with the extra wrinkle that
0050 also needs Google Cloud Console setup before the flag does
anything useful.

## What's wired on prod today (as of 2026-04-25)

- `coder-core` ships the `/oauth/*` and `/v1/admin/oauth/*` routes
  conditionally on `settings.mcp_oauth_enabled`. Off → every
  endpoint 404s (AC9). The 4th branch in
  `coder_core.mcp.auth.resolve_caller` recognises OAuth bearer
  tokens once they're issued.
- `MCP_OAUTH_ENABLED` env var is unset (→ `false`) on the Cloud
  Run service. `/.well-known/oauth-authorization-server` 404s.
- `GOOGLE_OAUTH_CLIENT_SECRET` is **not** mounted yet. The current
  admin login flow (spec 0012) only verifies pre-minted Google ID
  tokens; it doesn't need a client_secret. The OAuth-for-MCP flow
  does the auth-code → ID token exchange server-side and **does**
  need it. This runbook's prereqs add it.
- Zero registered OAuth clients. Once the flag flips, clients are
  registered admin-side via `POST /v1/admin/oauth/clients`.

## When to run this

- **Prerequisite** for flipping: an actual external client lined
  up (claude.ai web on an operator's laptop is the canonical first
  case). Don't flip speculatively — unlike the bearer-token MCP
  surface, OAuth widens the public attack surface (the auth-code
  endpoints accept unauthenticated traffic by design), and there's
  no value to leaving it on without a real user.
- The Google Cloud Console setup (Steps 1–2) can land days before
  the flag flip; it's a no-op until the flag is on.

## Who can run this

Operator with `run.admin` on the `vibedevx` GCP project (env
flips), `Editor` (or finer-grained equivalent) on the OAuth Client
config in the Cloud Console, and an admin JWT for the
`/v1/admin/oauth/*` endpoints once the flag is on. Stage gating
is a **product decision** — approval for each flag flip sits with
the project owner.

## Prerequisites

- [coder-core#21](https://github.com/coder-devx/coder-core/pull/21)
  merged to `main`, image promoted via the standard push-to-main
  CI deploy (see
  [deploy-coder-core](./deploy-coder-core.md)).
- `coder-core` migration `0052_oauth_tables` applied (the three
  OAuth tables exist). Auto-applied on the next deploy that runs
  the migration job; verify with:
  ```sh
  gcloud sql connect coder-core-db --project=vibedevx --user=postgres \
    --database=coder_core --quiet \
    -c "\dt oauth_*"
  # Expect: oauth_clients, oauth_codes, oauth_sessions
  ```
- An admin JWT in hand for the new admin endpoints (mint via the
  existing `POST /v1/admin/login` flow).

## Steps

### 1. Set up the Google OAuth client (one-time)

Open the [Google Cloud Console → APIs & Services →
Credentials](https://console.cloud.google.com/apis/credentials?project=vibedevx)
page.

If the existing **`coder-admin Web Client`** (used by the admin
panel today, per spec 0012) is set to "Web Application" type and
already has the relevant scopes enabled, **reuse it** — add a new
redirect URI to the same client. Otherwise create a fresh one:

1. Click **Create Credentials → OAuth Client ID**.
2. Application type: **Web Application**.
3. Name: `coder-core MCP OAuth`.
4. **Authorized redirect URIs** — add:
   ```
   https://coder-core-ql732k45va-ew.a.run.app/oauth/google-callback
   ```
   (Replace with the canonical Cloud Run URL of the prod service.
   Custom-domain users substitute the custom domain here AND in
   `MCP_OAUTH_PUBLIC_URL` in step 3.)
5. **Authorized JavaScript origins** — leave blank (server-side
   flow only).
6. Save. The Console shows the **Client ID** and **Client
   secret** — copy both.

### 2. Mount the client_secret in Secret Manager

```sh
echo -n 'PASTE-CLIENT-SECRET-HERE' | \
  gcloud secrets create coder-core-google-oauth-client-secret \
    --project=vibedevx --replication-policy=automatic --data-file=-

# Grant coder-core-sa read access (mirrors spec 0038 grant pattern).
gcloud secrets add-iam-policy-binding coder-core-google-oauth-client-secret \
  --project=vibedevx \
  --member=serviceAccount:coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

If you reused the existing `coder-admin Web Client` from step 1,
the secret value is the same one currently lacking a Secret
Manager mount — see
[secret-rotation-scheduler](./secret-rotation-scheduler.md) for
the rotation pattern; fresh secrets are fine to land directly.

### 3. Update the Cloud Run service env to mount the secret + the public URL

Three env additions (`GOOGLE_OAUTH_CLIENT_ID` likely already mounted
from spec 0012's admin login setup; verify and add if missing):

```sh
PUBLIC_URL='https://coder-core-ql732k45va-ew.a.run.app'

gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-secrets=GOOGLE_OAUTH_CLIENT_SECRET=coder-core-google-oauth-client-secret:latest \
  --update-env-vars=MCP_OAUTH_PUBLIC_URL="$PUBLIC_URL"
```

Verify both are present (and `MCP_OAUTH_ENABLED` is still off):

```sh
gcloud run services describe coder-core \
  --project=vibedevx --region=europe-west1 \
  --format='value(spec.template.spec.containers[0].env)' | tr ',' '\n' | \
  grep -E 'OAUTH|MCP_OAUTH'
# Expect: GOOGLE_OAUTH_CLIENT_ID, MCP_OAUTH_PUBLIC_URL
# (GOOGLE_OAUTH_CLIENT_SECRET is mounted from secret, shows differently)
```

`/.well-known/oauth-authorization-server` should still 404 because
`MCP_OAUTH_ENABLED` is unset — this is good, you're not exposing
the surface yet.

### 4. Stage 3 — flip `MCP_OAUTH_ENABLED=true`

```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=MCP_OAUTH_ENABLED=true
```

Verify the metadata endpoint, the dance endpoints, and the admin
endpoints all respond:

```sh
# Metadata: 200 + an issuer field matching MCP_OAUTH_PUBLIC_URL.
curl -sS "$PUBLIC_URL/.well-known/oauth-authorization-server" | jq

# Admin endpoint without a JWT: 401.
curl -sS -o /dev/null -w '%{http_code}\n' \
  "$PUBLIC_URL/v1/admin/oauth/clients" -X POST -d '{}' \
  -H 'Content-Type: application/json'
# Expect 401.

# /oauth/authorize without params: 400 (invalid_request, no code_challenge).
curl -sS -o /dev/null -w '%{http_code}\n' "$PUBLIC_URL/oauth/authorize"
# Expect 400.
```

**Watch for 24–72 h** before registering the first real client.
Tail the audit log for any `oauth.*` action — you should see zero
rows since no client is registered yet. Red flag: any 5xx on
`/oauth/*` (almost certainly traces to a misconfigured Google
client; check the Cloud Run logs and the redirect_uri in the
Console).

### 5. Stage 4 — register the first real client (claude.ai web)

```sh
ADMIN_JWT='...'  # mint via POST /v1/admin/login first
REDIRECT_URI='https://claude.ai/api/organizations/<org-id>/mcp/callback'
# (Get the exact redirect URI from claude.ai's "Add custom connector"
# flow — it's project-scoped to the operator's claude.ai org. Paste
# whatever claude.ai's UI shows you.)

curl -sS -X POST "$PUBLIC_URL/v1/admin/oauth/clients" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H 'Content-Type: application/json' \
  -d "{
    \"client_name\": \"claude.ai web\",
    \"redirect_uris\": [\"$REDIRECT_URI\"],
    \"software_id\": \"claude-ai\",
    \"software_version\": \"$(date +%Y.%m)\"
  }" | jq
# Returns: {"client_id": "...", "client_id_issued_at": ...}
```

Take the `client_id` to claude.ai's
**Settings → Customize → Connectors → Add custom connector**:

- **Server URL**: `<PUBLIC_URL>/.well-known/oauth-authorization-server`
  (or `<PUBLIC_URL>/mcp` — claude.ai will discover the metadata
  doc).
- **OAuth Client ID** (Advanced): paste the `client_id` from the
  curl above.
- **OAuth Client Secret** (Advanced): leave blank — we don't
  issue one (PKCE-only public clients per design OQ4-equivalent).

Click **Connect**. claude.ai redirects you to Google sign-in →
Google sends you to `coder-core/oauth/google-callback` → we mint
a code → claude.ai exchanges for a token → claude.ai stores it
and lists Coder's tools in the chat sidebar.

**This completes AC10.** Verify in a chat session that
`list_pipeline_runs` (or any other 0049 v1 tool) returns real
data for the `coder` project.

### 6. Stage 5 — soak

Watch for a week:

- **Audit-log flow**: every OAuth chat session should produce one
  `oauth.code_issued` row at consent and one `oauth.token_issued`
  row at exchange. Operator can trace an active session back to
  its Google sign-in moment via `correlation_id`.
- **Tool-call latency**: piggybacks on the existing 0049 metrics
  (admin-equivalent in v1). No separate watchpoint vs. admin-JWT
  callers.
- **Error rate on `/oauth/token`**: a sustained `invalid_grant`
  spike usually means a clock-skew between coder-core and Google,
  or a PKCE implementation bug in a new client. `invalid_client`
  spike means stale `client_id` (the operator revoked but the
  client cached).

After a week of clean metrics, fold the spec + design into
`active/` (per AGENTS.md rule 5).

## Rollback

**Fleet rollback** — flip the flag off:

```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=MCP_OAUTH_ENABLED=false
```

All `/oauth/*` and `/v1/admin/oauth/*` routes unbind on next
revision roll. Already-issued OAuth tokens **remain valid** until
their natural expiry (24 h) because the resolver still finds them
in `oauth_sessions`. To kill them too:

```sh
# Revoke every active OAuth client; the cascade kills sessions.
ADMIN_JWT='...'
for cid in $(curl -sS "$PUBLIC_URL/v1/admin/oauth/clients" \
              -H "Authorization: Bearer $ADMIN_JWT" | jq -r '.[].id'); do
  curl -sS -X POST "$PUBLIC_URL/v1/admin/oauth/clients/$cid/revoke" \
    -H "Authorization: Bearer $ADMIN_JWT"
done
```

(Note: this assumes the flag is still on for the revoke endpoint
to work. If it's already off, the cleanest path is to flip it
back on briefly, run the revoke loop, then flip off.)

**Per-client rollback** — leave the fleet flag on, kill one
misbehaving client:

```sh
curl -sS -X POST "$PUBLIC_URL/v1/admin/oauth/clients/$CLIENT_ID/revoke" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

Cascades to every active session bearing that `client_id`.

## Success condition

- `/.well-known/oauth-authorization-server` returns 200 with the
  expected metadata (issuer + authorization_endpoint +
  token_endpoint + `code_challenge_methods_supported=["S256"]`).
- One or more rows in `oauth_clients` (registered clients) and
  `oauth_sessions` (active tokens). Audit log carries
  `oauth.client_registered`, `oauth.code_issued`, and
  `oauth.token_issued` rows.
- claude.ai chat session can call any 0049 v1 tool against any
  project (admin-equivalent surface).
- `oauth.code_issued` and `oauth.token_issued` audit rows for the
  operator's email tie back to the same `correlation_id`.

## If something goes wrong

- **`/.well-known/oauth-authorization-server` returns 503
  `oauth_public_url_unset`** — `MCP_OAUTH_PUBLIC_URL` env var is
  missing. Step 3 wasn't run or didn't take. Verify with the
  `gcloud run services describe ... | grep MCP_OAUTH` from
  Step 3.
- **`/.well-known/...` returns 404** — `MCP_OAUTH_ENABLED` is off
  or unset. Same env-var-name gotcha as 0049: pydantic-settings has
  no prefix, so it's `MCP_OAUTH_ENABLED` (not
  `CODER_MCP_OAUTH_ENABLED`). Verify with the same
  `gcloud run services describe` line.
- **Google callback errors with
  `redirect_uri_mismatch`** — the redirect URI in the Cloud
  Console doesn't match what coder-core sends. Coder-core sends
  `<MCP_OAUTH_PUBLIC_URL>/oauth/google-callback` exactly; the
  Console value must be character-identical (including trailing
  slashes — there should be none).
- **Google callback errors with `email is not on the admin
  allowlist`** — the email completing Google sign-in is not in
  `settings.admin_allowed_emails`. Add it via the existing
  Cloud Run env mechanism, or have the operator sign in with an
  allowlisted account.
- **claude.ai's "Connect" button errors with
  `invalid_grant`** — almost always PKCE drift. The most common
  cause is a clock skew on either side; check the timestamps on
  recent `oauth.token_issued` audit rows vs.
  `oauth.code_issued`. If clean, suspect a claude.ai client bug
  and capture the request payload.
- **Token works but MCP returns -32004 not_found for every
  project** — check that the OAuth caller's email survives the
  admin-equivalence in `authorise_for_project`. The 4th branch in
  `mcp.auth.resolve_caller` should yield
  `MCPCaller(method=OAUTH_USER, ...)`; admin-equivalence then
  bypasses the per-project gate. If it's failing, check the
  `audit_events` row's `actor_method` — should be `oauth_user`,
  not `unknown`.

## Related

- Runbook:
  [mcp-agent-interface-rollout](./mcp-agent-interface-rollout.md) —
  the bearer-token MCP rollout this builds on.
- Runbook:
  [secret-rotation-scheduler](./secret-rotation-scheduler.md) —
  the
  `coder-core-google-oauth-client-secret` rotates the same way
  the broker signing key does.
- Runbook: [deploy-coder-core](./deploy-coder-core.md) — image
  promotion that gates these prereqs.
- ROADMAP entry: Phase 7 / 0050 (tag-along with 0049).
- AGENTS.md rule 5 — fold spec + design into `active/` after
  ≥ 30 days of clean prod soak.

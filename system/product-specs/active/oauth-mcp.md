---
id: oauth-mcp
title: OAuth 2.1 for MCP clients
type: spec
status: active
owner: ro
created: 2026-04-23
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: ['0050']
related_specs: [impersonation, audit-log, admin-panel]
parent: tenancy-and-access
---

# OAuth 2.1 for MCP clients

## What it is

An OAuth 2.1 authorisation-server layer on `coder-core` that lets MCP
clients authenticate as admin users via a standard code+PKCE flow. This
unlocks the "Add custom connector" UI in claude.ai web, which accepts
only OAuth — not static bearer headers. Operator Claude Code and Claude
Desktop sessions are unaffected; they continue to use the existing bearer
token paths (admin JWT, broker JWT, project API key).

## Capabilities

- **RFC 8414 discovery.** `GET /.well-known/oauth-authorization-server`
  returns the standard metadata document: `issuer`,
  `authorization_endpoint`, `token_endpoint`,
  `code_challenge_methods_supported=["S256"]`,
  `grant_types_supported=["authorization_code"]`,
  `token_endpoint_auth_methods_supported=["none"]`,
  `scopes_supported=["mcp"]`. No `registration_endpoint` — client
  registration is admin-only, not public DCR.
- **Admin-only client registration.** `POST /v1/admin/oauth/clients`
  (admin JWT required) accepts `{client_name, redirect_uris[],
  software_id?, software_version?}` and returns `{client_id,
  client_id_issued_at}`. Stored in `oauth_clients`. No client secret —
  public PKCE clients only. Operators register each MCP client (e.g.
  claude.ai web) in the admin panel; the resulting `client_id` is pasted
  into the connector's OAuth form. RFC 7591 public DCR is intentionally
  not exposed — every email that can complete the flow is already on the
  admin allowlist, so a public endpoint adds no capability.
- **Authorisation endpoint + PKCE.** `GET /oauth/authorize` validates
  `client_id`, `redirect_uri` (exact match against registered set),
  `code_challenge` (S256), `state`, `scope=mcp`. Redirects the browser
  to Google sign-in. The callback at `/oauth/google-callback` verifies
  the Google ID token against `settings.admin_allowed_emails` (same
  allowlist as admin login) and mints a 5-minute one-shot authorisation
  code, then redirects back to the client's `redirect_uri`.
- **Token endpoint.** `POST /oauth/token` with
  `grant_type=authorization_code, code, code_verifier, client_id,
  redirect_uri`. Verifies PKCE `code_verifier` matches the stored
  `code_challenge`. Issues an HS256 access token (24 h) signed with the
  existing `broker_signing_key`. Claims: `iss="coder-core/oauth"`,
  `aud="coder-core/mcp"`, `type="oauth_user"`, `sub=email`,
  `client_id`, `jti=session_id`. Returns RFC 6749
  `400 invalid_grant` on tampered verifier or redeemed code.
- **MCP auth resolution.** `resolve_caller` gains a fourth branch for
  OAuth tokens, returning `MCPCaller(method=OAUTH_USER,
  actor="oauth:{email}", admin_email=email, token_id=jti)`. Admin-equivalent
  access for v1 — all MCP tools, every project resolves. Existing bearer
  paths (admin JWT → broker JWT → project API key) are unchanged.
- **Session storage + revocation.** Each issued access token writes a
  row to `oauth_sessions` (`token_id, client_id, email, issued_at,
  expires_at, revoked_at`). Per-request revocation check < 5 s latency,
  identical in shape to admin-session revocation. Admin panel exposes:
  "Revoke OAuth session" (per-token) and "Revoke OAuth client" (cascades
  `revoked_at` to all active sessions for that `client_id`; subsequent
  `/oauth/token` calls with that `client_id` return `400 invalid_client`).
- **Audit trail.** Three action strings wired to `record_audit_event`:
  `oauth.client_registered` (actor=registering admin,
  `actor_method=admin_token`), `oauth.code_issued` (actor=user email,
  `actor_method=oauth_authorize`), `oauth.token_issued` (actor=user
  email, `actor_method=oauth_token`). `correlation_id` chains code →
  token so an operator can trace any session back to its consent moment.
  See [audit-log](./audit-log.md).
- **Fleet flag.** `MCP_OAUTH_ENABLED` (default `false`) gates all OAuth
  routes. Off → `/.well-known/oauth-authorization-server`,
  `/v1/admin/oauth/clients`, `/oauth/authorize`,
  `/oauth/google-callback`, `/oauth/token` all return 404; no routes
  register on the FastAPI app. Backout = one env flip.

## Interfaces

- `GET /.well-known/oauth-authorization-server` — RFC 8414 metadata.
- `POST /v1/admin/oauth/clients` — admin-JWT client creation; 201 +
  `{client_id, client_id_issued_at}`.
- `GET /v1/admin/oauth/clients` — list registered clients.
- `DELETE /v1/admin/oauth/clients/{client_id}` — revoke client +
  cascade all active sessions.
- `GET /v1/admin/oauth/sessions` — list active OAuth sessions.
- `POST /v1/admin/oauth/sessions/{token_id}/revoke` — revoke one session.
- `GET /oauth/authorize`, `GET /oauth/google-callback`,
  `POST /oauth/token` — standard OAuth 2.1 code + PKCE flow.
- DB: `oauth_clients`, `oauth_codes`, `oauth_sessions`
  (migration `0052_oauth_tables`).
- Env: `MCP_OAUTH_ENABLED`, `MCP_OAUTH_PUBLIC_URL`,
  `GOOGLE_OAUTH_CLIENT_SECRET`.

## Dependencies

- impersonation — `broker_signing_key` for HS256 issuance; the
  dual-key rotation window (2 h) extends transparently to OAuth tokens
  (same HS256 verifier path).
- audit-log — `oauth.client_registered`, `oauth.code_issued`,
  `oauth.token_issued` action strings.
- admin-panel — OAuth client management card and session revocation UI;
  `/admin/oauth-clients` route.
- Google OAuth — upstream IdP; reuses the existing Google OAuth client
  configuration and admin allowlist from admin login.
- MCP server (spec 0049) — `resolve_caller` extension point.

## Evolution

- 0050 OAuth 2.1 for MCP clients (shipped 2026-04-25) — 9 OAuth routes
  registered conditionally on `MCP_OAUTH_ENABLED` (RFC 8414 metadata,
  admin-only client create/list/revoke, session list/revoke,
  `/oauth/authorize`, `/oauth/google-callback`, `/oauth/token`).
  `resolve_caller` fourth branch in `coder_core.mcp.auth`.
  Migration `0052_oauth_tables` adds `oauth_clients`, `oauth_codes`,
  `oauth_sessions`. 13 automated tests cover AC1–AC9. AC10 (claude.ai
  web end-to-end smoke) verified 2026-04-25: first OAuth session from
  `coder@vibedevx.com` at 08:31 UTC; `oauth.code_issued` →
  `oauth.token_issued` → `mcp.session_opened` chain confirmed in prod.
  `MCP_OAUTH_ENABLED=true` in the Cloud Run revision deployed
  2026-04-25T08:48Z.

## Links

- Design: [0050](../../designs/wip/0050-oauth-for-mcp-clients.md)
- Related: [impersonation](./impersonation.md),
  [audit-log](./audit-log.md), [admin-panel](./admin-panel.md)
- Runbook: [oauth-mcp-clients-rollout](../../runbooks/oauth-mcp-clients-rollout.md)

---
id: '0050'
title: OAuth 2.1 for MCP clients — let claude.ai web (and other OAuth-only clients) connect
type: spec
status: wip
owner: ro
created: 2026-04-25
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ['0050']
related_specs:
  - impersonation
  - service-accounts
  - audit-log
  - admin-panel
  - multi-tenancy
parent: tenancy-and-access
---

# 0050 — OAuth 2.1 for MCP clients

## Problem

[0049](./0049-mcp-agent-interface.md) shipped the MCP server with
three bearer-token auth paths (admin JWT, broker JWT, project API
key). D2 of 0049 explicitly punted OAuth 2.1 on the grounds that
"we already have three working token types; re-using them is less
work." That decision now has a concrete cost.

When we tried to wire the prod MCP endpoint into **claude.ai
web** (the actual web app, not Claude Code or Claude Desktop), the
"Custom Connectors" UI flow at *Settings → Customize → Connectors
→ Add custom connector* only exposes OAuth 2.1 fields. There is no
field for a static `Authorization: Bearer <token>` header. Anthropic's
support page on remote MCP and the public issue tracker confirm
this is intentional — the web UI requires OAuth, with optional
Dynamic Client Registration (DCR, [RFC
7591](https://datatracker.ietf.org/doc/html/rfc7591)).

Result: the most accessible Claude surface — the one a casual user
or an operator browsing on their laptop will reach for first — is
the one our server can't speak to. Claude Desktop and Claude Code
work fine via the bearer-header escape hatches in their config
files, but those are operator-onboarding paths, not "open the
sidebar and chat."

The MCP authorisation spec (revision 2025-03-26) defines a clean
shape for this: the MCP server acts as an OAuth 2.1 **resource
server**, paired with an authorisation server (which may be the
same service or a separate one). PKCE is required for all flows.
DCR is recommended so clients don't need pre-registration. We
already have most of the building blocks — Google as an upstream
identity provider for admins (spec 0012), HS256 JWT issuance and
verification with a rotatable signing key (specs 0007 + 0038),
session storage with a `revoked_at` column for revocation latency
under 5 s — but no inbound OAuth surface tying them together.

This spec adds that surface, scoped to "let claude.ai web
authenticate as an admin user." Project-scoped OAuth (an OAuth
client representing one project's API key) is deferred — the v1
goal is parity-with-admin-via-OAuth, not a new permission model.

## Users

- **An admin opening claude.ai web** wants to add Coder as a
  custom connector and chat with it ("show me failing pipeline runs
  this week", "approve plan X"). Today they can't connect at all.
- **An external agent vendor** (a hypothetical third-party agent
  service that integrates with multiple MCP servers) wants to
  register their client via DCR and authenticate users through a
  standard OAuth code flow. Today they'd have to ask each Coder
  operator for a long-lived bearer.
- **A future browser-based developer dashboard** (not built; the
  admin panel is JWT-based today) would benefit from the same
  endpoints if we ever surface MCP capabilities to non-admin users.
- **Operators using Claude Code or Claude Desktop** are explicitly
  *not* in this spec's user list — they have a working path
  already and their tokens shouldn't be invalidated.

## Goals

- **claude.ai web's "Add custom connector" flow completes**
  end-to-end for an admin user, ending with the user able to call
  every tool an admin-JWT caller can call today.
- **OAuth 2.1 + PKCE + DCR** per [RFC
  6749](https://datatracker.ietf.org/doc/html/rfc6749) +
  [RFC 7636](https://datatracker.ietf.org/doc/html/rfc7636) +
  [RFC 7591](https://datatracker.ietf.org/doc/html/rfc7591) and
  the MCP authorisation revision 2025-03-26. Compliance with the
  spec is an end goal, not "OAuth-ish."
- **Reuse the existing identity backbone.** Google ID-token
  verification + the admin allowlist + the existing signing-key
  rotator should all carry over unchanged. Add OAuth as a
  *protocol layer* on top, not a parallel identity store.
- **No regression to existing token paths.** Admin JWT, broker
  JWT, and project API key continue to work via
  `Authorization: Bearer` exactly as today. OAuth-issued tokens
  resolve into the same `MCPCaller` shape so all downstream code
  is unchanged.
- **Audit parity.** Every OAuth grant + token issuance writes an
  `audit_events` row attributing the human user (email from the
  upstream Google ID token) plus the OAuth client name. A revoked
  client cannot resume.
- **Discoverable + flag-gated.** A
  `.well-known/oauth-authorization-server` doc lives on
  `coder-core` only when an `MCP_OAUTH_ENABLED` flag is on. Default
  off. Backout = one env flip.

## Non-goals

- **Project-scoped OAuth tokens in v1.** An OAuth-issued token
  carries admin-equivalent access. Adding scope claims that map to
  per-project broker-equivalent tokens is a phase-2 expansion and
  needs its own consent-screen design. Not v1.
- **A first-party consent screen UI in `coder-admin`.** v1 piggybacks
  on Google's consent screen — the user proves they're an
  allowlisted admin by completing a Google sign-in. The OAuth
  client (claude.ai) sees us as an OAuth server; we see Google as
  the actual identity verifier. A native consent screen ("App X
  wants permission to act as you on Coder, [Allow]") is nicer UX
  but not required for v1.
- **RS256 / JWKS publication.** Symmetric HS256 with the existing
  `broker_signing_key` is enough for v1: we're both the issuer
  *and* the resource server, no third party needs to verify our
  tokens. Move to RS256 + a `.well-known/jwks.json` only when we
  add a second resource server that needs to validate our tokens
  (e.g. a future `coder-admin` API).
- **Token introspection (RFC 7662).** Skip for v1. Same reason as
  JWKS: there's no separate validator that needs it. Deferred.
- **Refresh tokens with rotation + reuse-detection.** v1 issues a
  long-lived (24 h) access token and skips refresh tokens. Add
  refresh tokens in phase 2 if 24 h proves too short for real
  agents.
- **Fine-grained per-tool consent.** OAuth scopes in v1 are
  effectively binary: `mcp` (everything an admin can do via MCP).
  Per-tool scopes (`mcp.read`, `mcp.write`, `mcp.impersonate`) are
  a phase-2 nicety once we have signal on what real clients need.
- **Token revocation endpoint as a public OAuth surface.**
  Revocation works internally via the existing
  `AdminSessionRow.revoked_at` mechanism (admins click "revoke" in
  the admin panel). RFC 7009 endpoint comes later if a client
  asks.
- **Replacing Google as the identity provider.** Google stays the
  upstream IdP. If a self-hosted IdP (Authentik, etc.) is ever
  needed, that's its own spec.

## Scope

### In scope

1. **Authorisation-server metadata endpoint.** `GET
   /.well-known/oauth-authorization-server` returns the JSON
   document defined by [RFC
   8414](https://datatracker.ietf.org/doc/html/rfc8414): issuer,
   `authorization_endpoint`, `token_endpoint`,
   `registration_endpoint`,
   `code_challenge_methods_supported: ["S256"]`,
   `grant_types_supported: ["authorization_code"]`,
   `response_types_supported: ["code"]`,
   `token_endpoint_auth_methods_supported: ["none"]` (PKCE-only
   public clients). Served on the same `coder-core` service.

2. **Admin-authenticated client registration.** `POST
   /v1/admin/oauth/clients` (admin JWT required) accepts a JSON
   body `{client_name, redirect_uris, software_id?,
   software_version?}` and returns `{client_id,
   client_id_issued_at}`. `client_secret` is not issued — public
   clients use PKCE. The registration is stored in a new
   `oauth_clients` table for audit + revocation. RFC 7591
   public-DCR style (`POST /oauth/register` with no auth) is
   intentionally **not** exposed: every email that could complete
   the flow is already on the admin allowlist, so a public DCR
   endpoint adds zero capability and one spam surface. The
   metadata document at
   `/.well-known/oauth-authorization-server` accordingly omits
   `registration_endpoint`. Operators register a new MCP client
   (e.g. claude.ai) by clicking "Register OAuth client" in the
   admin panel; the resulting `client_id` is pasted into the MCP
   client's connector form.

3. **Authorisation endpoint with PKCE.** `GET /oauth/authorize`
   accepts `client_id, redirect_uri, code_challenge,
   code_challenge_method=S256, state, scope=mcp`. Validates the
   client_id against `oauth_clients`, redirect_uri against the
   registered set, then redirects the browser to **Google's
   sign-in page** with a state parameter that carries our session
   key. The Google callback lands at `/oauth/google-callback`,
   which verifies the Google ID token, checks the email against
   `settings.admin_allowed_emails` (same allowlist the admin login
   uses), then mints an authorisation code and redirects the
   browser back to the OAuth client's `redirect_uri`.

4. **Token endpoint.** `POST /oauth/token` with
   `grant_type=authorization_code, code, code_verifier, client_id,
   redirect_uri`. Validates the code against the issued
   authorisation code, verifies the PKCE code_verifier matches the
   stored code_challenge, then issues an HS256 access token signed
   with the existing `broker_signing_key`. Token claims:
   `iss="coder-core/oauth"`, `aud="coder-core/mcp"`,
   `type="oauth_user"`, `sub=email`, `client_id`,
   `jti=session_id`, plus `iat/nbf/exp` (24 h).

5. **MCP auth adapter extension.** `coder_core.mcp.auth.resolve_caller`
   gains a fourth branch (after admin JWT → broker JWT → project
   API key): try OAuth token. On match, returns an `MCPCaller`
   with `method=AuthMethod.OAUTH_USER, actor="oauth:{email}",
   admin_email=email, token_id=jti`. The new `OAUTH_USER` method
   has the same authorisation surface as `ADMIN_TOKEN` for v1 —
   `tools/list` returns all 13 tools, every project resolves.

6. **Session storage + revocation.** Each issued OAuth access
   token writes a row to `oauth_sessions` (`token_id, client_id,
   email, issued_at, expires_at, revoked_at`). Per-request
   revocation check identical in shape to the admin session
   check. Admin panel grows a "Revoke OAuth session" action and a
   "Revoke OAuth client" action (the latter cascades — every
   active session for that client is `revoked_at`-stamped).

7. **Audit integration.** Three new action strings on
   `audit_events`:
   - `oauth.client_registered` (one per admin-driven client
     creation) — `actor=admin_email`, `actor_method=admin_token`,
     `target_type=oauth_client`, `target_id=client_id`.
   - `oauth.code_issued` (one per successful Google-callback
     code mint) — `actor=email`, `actor_method=oauth_authorize`.
   - `oauth.token_issued` (one per successful token-endpoint
     call) — `actor=email`, `actor_method=oauth_token`. The
     `correlation_id` chains code → token so an operator can trace
     a session to its consent moment.

8. **Fleet flag.** `MCP_OAUTH_ENABLED` (default `false`) gates
   every endpoint added by this spec. When `false`,
   `/.well-known/oauth-authorization-server`,
   `/v1/admin/oauth/clients`, `/oauth/authorize`,
   `/oauth/google-callback`, and `/oauth/token` all return 404 —
   no routes register. Backout = one env flip.

### Out of scope

- Project-scoped OAuth, per-tool scopes, refresh tokens with
  rotation, token introspection, RS256/JWKS, native consent
  screen, alternative IdPs.
- claude.ai's first-party connector ("Anthropic-managed Coder
  connector"). Not a v1 concern; that's a partnership, not an
  engineering spec.
- Migrating the existing admin login flow off Google ID tokens.
  Admin login keeps its current shape; OAuth shares the upstream
  Google verifier but is its own protocol surface.

## Acceptance criteria

- **AC1.** With `MCP_OAUTH_ENABLED=true`, `GET
  /.well-known/oauth-authorization-server` returns the RFC 8414
  metadata document with `authorization_endpoint`,
  `token_endpoint`, and
  `code_challenge_methods_supported=["S256"]`. The
  `registration_endpoint` field is **absent** (admin-only
  registration; not part of the public discovery surface). With
  the flag off, the same path returns 404.

- **AC2.** `POST /v1/admin/oauth/clients` with a valid admin
  JWT and a body `{client_name, redirect_uris[]}` returns 201
  with `{client_id, client_id_issued_at}`. The row in
  `oauth_clients` carries the `client_name`, registered
  `redirect_uris`, and the registering admin's email. The same
  call without an admin JWT returns 401.

- **AC3.** A full auth-code+PKCE flow ending at `POST
  /oauth/token` returns a JWT whose decoded claims include
  `iss="coder-core/oauth"`, `aud="coder-core/mcp"`,
  `type="oauth_user"`, `sub=<email>`, `client_id=<id from
  registration>`, `exp` ~24 h ahead.

- **AC4.** `POST /mcp` with the OAuth token in `Authorization:
  Bearer` succeeds for `initialize`, `tools/list` (returns all 13
  tools — admin parity), and `tools/call` against any project.
  `actor_method='oauth_user'` appears on the resulting
  `audit_events` rows.

- **AC5.** Calling `POST /oauth/token` with a tampered
  `code_verifier` returns RFC-6749 `400 invalid_grant` with no
  token issued.

- **AC6.** Calling `POST /oauth/token` with a code that has
  already been redeemed returns `400 invalid_grant`. Codes are
  one-shot.

- **AC7.** Revoking an OAuth session (setting
  `oauth_sessions.revoked_at`) causes the next MCP call carrying
  that token to return `-32001 unauthenticated` within 5 s. Same
  shape as the existing admin-session revocation guarantee.

- **AC8.** Revoking an OAuth client cascades — every active
  session bearing that `client_id` is invalidated; subsequent
  `/oauth/token` calls with that `client_id` return `400
  invalid_client`.

- **AC9.** `MCP_OAUTH_ENABLED=false`: every OAuth endpoint
  returns 404. No OAuth-related routes register on the FastAPI
  app. Backout verified.

- **AC10.** End-to-end smoke: claude.ai's "Add custom
  connector" flow against a deployed canary completes — the
  client is registered, the user signs in via Google, the token
  exchanges, and the user can run an MCP tool from a claude.ai
  chat session. Recorded as a manual checklist in the rollout
  runbook (no CI test for this; claude.ai is third-party).

## Metrics

- **OAuth client registrations / week.** Sustained > 0 means at
  least one third party is integrating; 0 for 30 days post-launch
  is a "did anyone notice" signal.
- **Code-to-token latency p95.** Target < 1 s for the auth-code
  redemption — this is on the hot path of every claude.ai chat
  session start.
- **Token issuance error rate by error code.** `invalid_grant`
  spikes signal PKCE drift or client implementation bugs;
  `invalid_client` spikes signal stale client registrations.
- **OAuth-attributed audit events / day** (`actor_method='oauth_user'`).
  A leading indicator of actual OAuth-driven MCP usage,
  separable from operator-driven (admin JWT) traffic.
- **Active OAuth sessions** (count of `oauth_sessions` with
  `revoked_at IS NULL AND expires_at > now()`). Capacity-planning
  signal — if this grows unbounded, we'll need refresh tokens
  sooner than phase 2.

## Decisions

OQ6 was decided 2026-04-25 (admin-only DCR — see below). OQ1–5
resolved 2026-04-27 ahead of fold-to-active.

- **OQ1 — Public hostname: pin to current Cloud Run URL for
  now; custom domain (`mcp.coder.<your-domain>`) tracked as
  a follow-up.** The Cloud Run URL is brittle if the service
  is recreated, but no current operational work is forcing
  recreation. Custom domain requires DNS + cert work; defer
  until a triggering need (recreation, multi-region, or
  branding) shows up. Document the recreation risk in the
  runbook so an operator about to recreate the service knows
  the issuer-field URL changes.
- **OQ2 — Authorisation code TTL: 5 minutes.** Long enough
  to absorb a slow Google callback; short enough that
  long-lived codes don't sit around. RFC ≤ 10 min ceiling
  preserved as an upper bound; 1 min was tighter than needed.
- **OQ3 — `redirect_uri` matching: exact.** Strict exact
  match across registered URIs. Clients with multiple
  subpaths register each one explicitly. Safer surface; the
  ergonomics cost is small in practice.
- **OQ4 — OAuth scope claim: `mcp` only.** Reject any other
  requested scope (including `mcp impersonate`) with
  `invalid_scope`. Defensive — scope claims are aspirational
  for v1 and admin-parity isn't a requested use case yet.
- **OQ5 — broker rotation interaction with OAuth tokens —
  needs explicit test.** The dual-key verifier already
  handles admin tokens during the 2h rotation window and
  *should* extend transparently to OAuth tokens (same HS256
  key). Add an explicit test in the implementation's test
  suite: rotate `broker_signing_key`, verify both pre- and
  post-rotation OAuth tokens decode within the 2h window.
- **OQ6 — Public DCR or admin-only client registration:
  admin-only.** (Decided 2026-04-25.) Public DCR (RFC 7591)
  is the MCP-spec recommendation but adds zero capability
  when the admin allowlist already gates who can complete
  the flow. Operationally, an admin pre-registers each MCP
  client via `POST /v1/admin/oauth/clients` and pastes the
  resulting `client_id` into the client's connector form. If
  a future MCP client is DCR-only, revisit by re-exposing
  the public endpoint behind a separate flag.

## Open questions

_None — all resolved. See Decisions above._

## Links

- Design: [0050](../../designs/wip/0050-oauth-for-mcp-clients.md)
- Related specs:
  [impersonation](../active/impersonation.md),
  [service-accounts](../active/service-accounts.md),
  [audit-log](../active/audit-log.md),
  [admin-panel](../active/admin-panel.md)
- Supersedes (decision): [0049](./0049-mcp-agent-interface.md) D2
  ("OAuth 2.1 dynamic client registration") — D2 was scoped out
  of 0049 v1; this spec re-opens it as its own work item.
- Roadmap: Phase 7 — Trusted Autonomy (OAuth-for-MCP makes the
  agent surface reachable from the most-used Claude UI).
- Rollout runbook:
  [oauth-mcp-clients-rollout](../../runbooks/oauth-mcp-clients-rollout.md) —
  Google OAuth client setup, fleet-flag flip, claude.ai
  end-to-end smoke (AC10), rollback.
- MCP authorisation spec:
  [https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization](https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization)
- claude.ai connector docs:
  [https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)

## Working log

In-flight notes to bridge sessions. Deleted when this WIP folds into
`active/`.

### Session handoff — 2026-04-25 (later)

**Stages 1+2 shipped.** Full OAuth surface merged via
[coder-core#21](https://github.com/coder-devx/coder-core/pull/21)
(commit `d70f913`):

- 9 routes registered conditionally on `MCP_OAUTH_ENABLED`
  (RFC 8414 metadata, admin-only DCR, list/revoke clients, list/
  revoke sessions, `/oauth/authorize`, `/oauth/google-callback`,
  `/oauth/token`).
- 4th `resolve_caller` branch in `coder_core.mcp.auth` —
  OAuth-issued tokens are admin-equivalent in v1.
- Migration `0052_oauth_tables` adds `oauth_clients`,
  `oauth_codes`, `oauth_sessions`.
- 13 tests covering AC1–AC9. AC10 is a manual claude.ai-vs-prod
  smoke (Stage 4 below).

**Stage 3 — flag flip done.** Same Cloud Run revision (deploy
`2026-04-25T08:48Z`) sets `MCP_OAUTH_ENABLED=true`,
`MCP_OAUTH_PUBLIC_URL=https://coder-core-ql732k45va-ew.a.run.app`,
and mounts `GOOGLE_OAUTH_CLIENT_SECRET` from Secret Manager.
`MCP_ENABLED=true` flipped at the same time (see 0049 working
log). Verified live:

```sh
curl -sS https://coder-core-8534948335.europe-west1.run.app/.well-known/oauth-authorization-server
# → 200 RFC 8414 doc with issuer, authorization_endpoint,
#   token_endpoint, code_challenge_methods_supported=["S256"],
#   token_endpoint_auth_methods_supported=["none"], scopes=["mcp"];
#   registration_endpoint absent (admin-only DCR per OQ6).
```

**Stage 4 — first client onboarded ✓ AC10 satisfied.** Operator
completed the registration + claude.ai sign-in flow on 2026-04-25:

```
08:18:48  oauth.client_registered  client_name="claude.ai web"
                                   redirect_uri=https://claude.ai/api/mcp/auth_callback
                                   software_id=claude-ai
                                   registered_by=coder@vibedevx.com
08:31:30  oauth.code_issued        actor=coder@vibedevx.com
08:31:30  oauth.token_issued       actor=coder@vibedevx.com
08:31:30  mcp.session_opened       actor=oauth:coder@vibedevx.com
                                   method=oauth_user
… 4 additional mcp.session_opened from the same OAuth identity
  through 11:25 UTC (claude.ai web reconnecting per chat session).
```

The `oauth.code_issued` → `oauth.token_issued` → `mcp.session_opened`
chain shipping in the same minute confirms AC1–AC4 + AC10 working
end-to-end against prod. One active session sits in
`oauth_sessions` (`token_id=6d6b4f66...`, `expires_at=2026-04-26T08:31`).

**Remaining for fold-to-active** (per AGENTS.md rule 5, ≥30 days
clean prod soak):

1. Watch token-issuance error rate (`invalid_grant`
   /`invalid_client` spikes on `/oauth/token`) — claude.ai's
   client is the only registered consumer today, so any spike
   would point at our side.
2. After ~2026-05-25, fold spec + design into `active/`. New
   active component name: `oauth-mcp` (or merge into a single
   `mcp-agent-interface` active component alongside 0049 — TBD
   at fold time per AGENTS.md "single component per concern"
   guidance).

**Open question OQ1 — hostname pinning.** The metadata doc's
`issuer` is the current Cloud Run hash URL
(`coder-core-ql732k45va-ew.a.run.app`). Fine for now;
re-evaluate if/when a custom domain lands. Not blocking.

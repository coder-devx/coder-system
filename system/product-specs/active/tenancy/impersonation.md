---
id: impersonation
title: Local agent impersonation
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-19
last_verified_at: 2026-04-19
summary: Short-lived role-scoped bearer tokens for worker actions.
served_by_designs: [impersonation]
related_specs: [admin-panel, audit-log, multi-tenancy, service-accounts]
parent: tenancy-and-access
---

# Local agent impersonation

## What it is

Local agents — Claude Code or Cursor running on a human's laptop —
act inside Coder as first-class role workers via short-lived,
role-scoped bearer tokens issued by the SysAdmin broker. Every action
taken with a broker token is attributed to the authorising human in
the audit log and surfaced in the admin pipeline view. Revocation is
immediate: flipping `revoked_at` in the sessions table kills in-flight
tokens within seconds with no cache in the path.

## Capabilities

- Dual authentication on `require_project_auth`: `X-Api-Key` (admin
  and project keys) or `Authorization: Bearer <jwt>` (broker tokens).
- Bearer verification cross-checks the token's `project_id` claim
  against the path's project, rejecting cross-tenant reuse.
- `CallerIdentity` (method, actor, role, token_id) flows into tasks
  via nullable `actor`, `actor_type`, `actor_token_id` columns.
- `impersonation_sessions` table records every issuance with
  `token_id`, `project_id`, `role`, `issued_at`, `expires_at`,
  `revoked_at`.
- Admin panel: violet badge for `broker_token` tasks in pipeline list
  and detail views; actor name shown alongside task metadata.
- Session admin endpoints: `GET /sessions`, `POST /sessions/{token_id}/revoke`.
- `coder` CLI: `impersonate <role> --project=<slug>` mints and caches
  a token at `~/.config/coder/token.json` (0600); `token` prints it;
  `status` shows role / project / expiry. `project onboard` and
  `project doctor` wrap the runbook and health-check paths.

## Interfaces

- HTTP: broker `POST /v1/projects/{project_id}/impersonate/{role}`;
  admin `GET /sessions`, `POST /sessions/{token_id}/revoke`.
- Auth headers: `X-Api-Key` or `Authorization: Bearer`.
- CLI: `coder impersonate | token | status | project onboard | project doctor`.
- Storage: `~/.config/coder/projects/{slug}.key`, `~/.config/coder/token.json`.
- Config: `CODER_API_KEY`, `CODER_BASE_URL` env vars.

## Dependencies

- Per-role service accounts (broker + role SAs).
- Multi-tenant project CRUD (`project_id` guard).
- Pipeline UI in admin (for actor badge surfacing).
- Postgres (`impersonation_sessions`, `tasks.actor*` columns).

## Evolution

- `0007-local-agent-impersonation` — bearer auth, actor tracking,
  session table + revoke, CLI, admin actor badges. Migrations
  `0007_tasks_actor`, `0008_impersonation_sessions`.
- `7c07ba6` — DX follow-ups: `coder project onboard` and
  `coder project doctor` (181 tests).
- `0037` — audit log wiring (shipped 2026-04-19):
  `impersonate.issue_token` and `sessions.revoke` each write an
  `audit_events` row (action-only, `after.role` carries the
  impersonated role on issuance; revoke records the `token_id`).
  `CallerIdentity.actor` / `actor_method` are the authorship fields
  on every audit row fleet-wide so a broker-issued token's actions
  resolve back to the authorising human. See
  [audit-log](./audit-log.md).

## Links

- Designs: [impersonation](../../../designs/active/tenancy/impersonation.md)
- Related components: [audit-log](./audit-log.md),
  [service-accounts](./service-accounts.md),
  [multi-tenancy](./multi-tenancy.md), [admin-panel](../knowledge/admin-panel.md)

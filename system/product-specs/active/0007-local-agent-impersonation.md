---
id: "0007"
title: Local agent impersonation
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0001", "0005", "0006"]
---

# Local agent impersonation

**Phase:** Shipped
**Progress:** 6 / 6 acceptance criteria ✅

## Problem

A lot of real work will happen through local agents on Ro's laptop —
Claude Code acting as "Architect for project X", Cursor acting as
"Developer for project Y". Today those agents have no way to talk to
`coder-core` as a role, and the per-role service accounts from spec
`0005` are cloud-only. Without impersonation, every piece of work that
happens locally is invisible to Core's audit log and sits outside the
per-role permission model. This spec gives local agents a
short-lived, role-scoped token so they can act inside the system
without bypassing it.

## Users / personas

- **Ro (human owner)** — runs a local agent, wants it to be a
  first-class actor with the same boundaries as a remote worker.
- **Claude Code / Cursor** (the local agent) — needs to request a token,
  use it to call Core APIs, and refresh it before expiry.
- **Software Architect** — needs assurance that a local agent can't
  exceed the role it impersonated.
- **SysAdmin broker** (from spec `0005`) — issues these tokens, logs
  every issuance, and ties them back to the human who authorised them.

## Goals

- An authenticated human can request impersonation of a specific role
  for a specific project from the broker.
- The resulting token is short-lived, role-scoped, and identical in
  permission surface to what a cloud worker of that role would hold.
- A local agent using the token shows up in the admin panel's pipeline
  view (spec `0006`) as a first-class actor with `role=X, actor=human`.
- Revocation works immediately — pulling the plug on a session kills
  in-flight tokens.
- The audit trail links every impersonated action back to the human
  who authorised the session.

## Non-goals

- Cross-project impersonation in one session — one token, one project.
- Turning local agents into fully remote workers; they remain
  user-initiated.
- Replacing the SysAdmin broker — this spec extends it, not rewrites it.
- Implementing an OAuth provider from scratch — piggyback on the
  existing identity layer.

## Scope

- `POST /impersonate/{role}?project_id=...` on the broker, gated on
  the human's identity.
- A small CLI (`coder impersonate <role> --project=<slug>`) that local
  agents and Ro can invoke to get a token written to a well-known local
  path.
- Token introspection endpoint so a local agent can ask "what am I
  allowed to do with this?".
- Audit records: `(human_id, role, project_id, issued_at, expires_at,
  revoked_at)`.
- Admin panel surfacing: pipeline view labels runs authored by an
  impersonated actor distinctly.
- Emergency revoke button in the admin panel.

## Acceptance criteria

- [x] Ro can run the CLI and get back a valid role-scoped token for a
      chosen project.
- [x] A local agent using the token can list that project's tasks and
      enqueue a developer task.
- [x] The same token cannot read or enqueue against a different project.
- [x] An expired token is rejected and the CLI prompts for refresh.
- [x] Revoking a session in the admin panel causes subsequent calls
      using that token to fail within 5 seconds.
- [x] The pipeline view shows the impersonation actor (human + role)
      for any task they enqueued.

## Metrics

- **Auditability:** 100% of local-agent actions tied to a human actor
  in the audit log.
- **Revocation latency:** under 5 seconds from revoke click to token
  rejection in practice.
- **Adoption:** Ro's local Claude Code runs exclusively via
  impersonation — 0 direct-DB or direct-GitHub bypasses.

## What shipped

Four stages, all landed in coder-core `7d1a14a` and coder-admin `0a31bc8`:

1. **Bearer auth + actor tracking** — `require_project_auth` in `auth.py`
   accepts both `X-Api-Key` and `Authorization: Bearer <jwt>`. Bearer
   tokens are verified via the broker, cross-checked against project_id
   (AC3), and carry `CallerIdentity` with method, actor, role, and
   token_id. Three new nullable columns on `tasks` (`actor`,
   `actor_type`, `actor_token_id`) stamp every task with its creator
   (migration `0007_tasks_actor`).

2. **Impersonation sessions + revocation** — new `impersonation_sessions`
   table (migration `0008_impersonation_sessions`) records every broker
   token issuance with `token_id` (PK), `project_id`, `role`,
   `issued_at`, `expires_at`, `revoked_at`. New session admin endpoints
   (`GET /sessions`, `POST /sessions/{token_id}/revoke`) gated by
   `X-Api-Key` (admin-only). Bearer auth checks `revoked_at IS NOT NULL`
   on every request — no cache, immediate effect (AC5 < 5s).

3. **CLI tool** — `coder impersonate <role> --project=<slug>` reads the
   API key from `CODER_API_KEY` env var or
   `~/.config/coder/projects/{slug}.key`, calls the broker's
   impersonate endpoint, and writes the token to
   `~/.config/coder/token.json` (0600 permissions) with `expires_at`
   so agents can detect stale tokens. `coder token` prints the cached
   JWT; `coder status` shows role, project, expiry, and GCP token
   presence. Entry point registered in pyproject.toml.

4. **Pipeline view actor display** — `coder-admin` Task interface
   extended with `actor`, `actor_type`, `actor_token_id`. Pipeline list
   and task detail views show a violet badge for `broker_token` tasks
   with the actor name. Task detail metadata grid includes an "actor"
   row with "(impersonation)" label.

166 tests pass in coder-core (30 new tests covering bearer auth,
sessions, CLI, and actor tracking). CI green.

## Open questions (resolved)

- **Token storage:** dotfile at `~/.config/coder/token.json` with 0600
  permissions. OS keychain deferred — dotfile is simple and sufficient
  for a single-user laptop.
- **Multiple simultaneous impersonations:** one token file at a time.
  Multiple sessions can exist server-side (each has its own `token_id`),
  but the CLI overwrites the local token file. Good enough for now.
- **CLI discovery:** `--base-url` flag with `CODER_BASE_URL` env var
  fallback, defaulting to `http://localhost:8080`.

## Links

- Designs: [`0004`](../../designs/wip/0001-generalize-coder-from-vibetrade.md) (build plan step 7), [`0002`](../../designs/active/0002-worker-roles-and-impersonation.md)
- ADRs: [`0006`](../../adrs/0006-per-role-service-accounts.md)
- Related specs: [`0001`](./0001-multi-tenant-project-crud.md), [`0005`](./0005-per-role-service-accounts.md), [`0006`](./0006-pipeline-ui-in-admin.md)

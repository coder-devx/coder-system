---
id: mcp-agent-interface
title: MCP agent interface
type: spec
status: active
owner: ro
created: 2026-04-01
updated: 2026-05-17
last_verified_at: 2026-05-17
summary: Let external agents connect, impersonate, and drive Coder via MCP.
served_by_designs: [mcp-agent-interface-design]
related_specs: [admin-panel, audit-log, impersonation, knowledge-api, multi-tenancy, oauth-mcp, service-accounts, task-orchestration]
parent: knowledge-and-admin
---

# MCP agent interface

## What it is

`/mcp` is the protocol surface that lets any MCP-speaking agent
connect to `coder-core` over streamable HTTP, authenticate with an
existing Coder token, and drive the same project-scoped capabilities
the REST API exposes — listing tasks, creating tasks, reading
knowledge, approving plans, subscribing to pipeline events. It sits
as a FastAPI sub-app peer of the `/v1/*` routes on the same Cloud
Run service, so a single `coder-core` deployment serves both HTTP
and MCP clients. Auth, audit, and tenant isolation reuse the
existing middleware; MCP is a transport wrapper, not a new
permission model.

The primary callers are external agents on operator laptops (a
Claude Code session outside Coder), long-running orchestrator agents
that watch SSE and react via tool calls, and ops/SRE agents acting
under an admin token for fleet-wide work.

## Capabilities

- **Single MCP endpoint with bearer auth.** `POST /mcp` accepts
  JSON-RPC 2.0 over streamable HTTP. The `initialize` request carries
  `Authorization: Bearer <token>`; the adapter tries admin JWT →
  broker JWT → project API key in order, resolving to a
  `CallerIdentity`. Unknown or expired tokens return `-32001
  unauthenticated`. `GET /mcp/health` returns
  `{enabled, version, tools: <count>}` when on, 404 otherwise. One
  bearer per session — role switch requires a new session, so every
  audit row in a session has exactly one caller identity.

- **12-tool v1 surface, caller-filtered.** `tools/list` returns only
  tools the caller is authorised to invoke. Reads (7): `list_tasks`,
  `get_task`, `list_pipeline_runs`, `get_pipeline_run`,
  `list_knowledge`, `get_knowledge`, `get_metrics`. Writes (3):
  `create_task`, `approve_task_plan`, `reject_task_plan`,
  `submit_knowledge` (role-gated, same permissions as the HTTP
  counterparts). Admin-only (2): `impersonate(project_id, role)` mints
  a broker JWT and writes an `impersonate.issue_token` audit row;
  `override_pipeline_run` pauses / resumes / cancels a run. Admin JWT
  callers see all 12; project-API-key callers see 9; developer
  broker-JWT callers see 7.

- **Subscribable resources.**
  `coder://projects/{id}/pipeline-runs/live` wraps the existing
  `pipeline_run.changed` SSE stream;
  `coder://projects/{id}/tasks/{id}/messages` wraps the live
  `task_messages` feed; `coder://projects/{id}/metrics` returns the
  latest rollup. Hard cap of 10 subscriptions per session protects
  against pathological fan-out. All resources scope to the caller's
  project through the same middleware that gates the REST surfaces.

- **Audit parity with HTTP.** Every mutating tool call writes an
  `audit_events` row before returning success, reusing the existing
  action strings (`tasks.create`, `task_plans.approve`, etc.).
  `actor_method='mcp'` distinguishes MCP-initiated mutations from
  HTTP. `mcp.session_opened` is written on `initialize` so operators
  see "agent X connected at T" in the audit log. No bypass surface.

- **Tenant isolation.** Cross-tenant tool calls (e.g. `get_task` with
  another project's task id) return `-32004 not_found`, mirroring the
  REST contract. The `tests/isolation/` matrix carries MCP-path
  entries; the CI drift check blocks any new MCP route not covered.

- **Flag-gated rollout.** `CODER_MCP_ENABLED` (env, default off) gates
  the entire endpoint — when off, `/mcp` returns 404 on every method
  and no routes register. `projects.mcp_enabled` is per-project
  tri-state (NULL = fleet inherit, true = opt in, false = opt out
  even when fleet is on); off returns `-32003 project_mcp_disabled`
  for project-scoped callers (admins bypass). Backout is one env
  flip.

## Interfaces

- `POST /mcp` — JSON-RPC 2.0 streamable-HTTP transport. Methods:
  `initialize`, `tools/list`, `tools/call`, `resources/list`,
  `resources/read`, `resources/subscribe`. Unknown methods return
  `-32601 method not found`.
- `GET /mcp/health` — `{enabled, version, tools}` when the fleet flag
  is on; 404 otherwise.
- `CODER_MCP_ENABLED` env (fleet kill switch);
  `projects.mcp_enabled` tri-state column (per-project opt-in / opt-out).

## Dependencies

- [impersonation](../tenancy/impersonation.md) — the broker mints
  role-scoped JWTs that MCP returns from the `impersonate` tool.
- [service-accounts](../tenancy/service-accounts.md) — admin JWT
  issuance and per-role identity carry through to MCP auth.
- [audit-log](../tenancy/audit-log.md) — every mutation lands here
  with `actor_method='mcp'`.
- [multi-tenancy](../tenancy/multi-tenancy.md) — project scoping
  middleware gates both HTTP and MCP paths.
- [task-orchestration](../pipeline/task-orchestration.md),
  [knowledge-api](./knowledge-api.md) — the underlying read/write
  surfaces the tools wrap.
- The OAuth 2.1 auth-server for clients that can't use bearer headers
  (claude.ai web custom connectors) ships separately —
  see [oauth-mcp](../tenancy/oauth-mcp.md).

## Evolution

- 2026-04 — initial bearer-auth MCP server with 12 tools + 3
  resources; admin-only fleet rollout.
- 2026-04-22 — OAuth 2.1 auth-server layer ships for browser MCP
  clients (see [oauth-mcp](./oauth-mcp.md)); MCP bearer surface
  unchanged.

## Links

- Designs: [mcp-agent-interface-design](../../../designs/active/knowledge/mcp-agent-interface-design.md)
- Related components: [impersonation](../tenancy/impersonation.md),
  [service-accounts](../tenancy/service-accounts.md),
  [audit-log](../tenancy/audit-log.md),
  [admin-panel](./admin-panel.md),
  [multi-tenancy](../tenancy/multi-tenancy.md),
  [task-orchestration](../pipeline/task-orchestration.md),
  [knowledge-api](./knowledge-api.md),
  [oauth-mcp](../tenancy/oauth-mcp.md)
- Runbook: [mcp-agent-interface-rollout](../../../runbooks/mcp-agent-interface-rollout.md)

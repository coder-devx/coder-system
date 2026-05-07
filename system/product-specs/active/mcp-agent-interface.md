---
id: mcp-agent-interface
title: MCP agent interface
type: spec
status: active
owner: ro
created: 2026-04-01
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: Let external agents connect, impersonate, and drive Coder via MCP.
served_by_designs: []
related_specs: [impersonation, service-accounts, audit-log, admin-panel, multi-tenancy, task-orchestration, knowledge-api]
parent: tenancy-and-access
---

# MCP agent interface

## Problem

Coder has a well-shaped internal API (project-scoped REST, impersonation
broker, audit trail, SSE streams) but no first-class way for an external
agent to connect to it. A human running Claude Code on a laptop has two
options: poke endpoints with `curl`, or use the in-tree `coder` CLI which
covers only a sliver of the surface and talks to localhost by default. An
agent running elsewhere — another Claude Code session, a custom
orchestrator, a CI-initiated agent — has no connection story at all.

Three gaps:

1. **Impersonation is local-only.** The broker mints role-scoped JWTs but
   there is no protocol for a non-Coder agent to authenticate, request a
   role, and act as that role over a durable session.

2. **Reading state is one-off.** Every agent that wants pipeline state,
   reviewer verdicts, or metrics re-implements the HTTP client from
   scratch or scrapes the admin panel.

3. **Admin actions require a Google OAuth wall.** Approving a spec,
   retrying a stuck task, granting a budget override — all capable, all
   blocked from agent delegation.

The Model Context Protocol (MCP) is the industry-standard shape for this:
JSON-RPC-over-HTTP where servers expose **tools** (callable functions),
**resources** (readable context), and **prompts** to agent clients. Every
major agent client speaks MCP. Adding an MCP server to `coder-core` means
any agent anywhere can drive Coder with no bespoke integration. The
permission story is already solved by impersonation + audit: MCP is a
protocol wrapper, not a new permission model.

## Users

- **External agent on an operator's laptop** — a Claude Code session
  outside Coder inspects pipeline state, starts tasks, approves plans.
  Connects over streamable HTTP with a broker JWT or project API key.
- **Long-running orchestrator agent** — a headless agent that watches
  Coder, reacts to SSE events, and calls tools. Needs durable connection,
  subscriptions, and impersonation refresh.
- **Ops / SRE agent** — acts under an admin token for fleet-wide work:
  retry stuck tasks across projects, surface metrics, flip flags, ack
  escalations.
- **Coder itself (dogfood, future)** — worker fleet running against its
  own MCP surface. Not a v1 goal but the design doesn't preclude it.

## Goals

- One MCP endpoint on `coder-core` any MCP-speaking client can connect to
  over streamable HTTP, authenticate with a bearer token, and drive
  Coder's core capabilities.
- Auth reuses today's tokens — no new token format or lifecycle. A caller
  presents an existing project API key, broker JWT, or admin JWT; the MCP
  server maps it to `CallerIdentity` via existing middleware.
- Impersonation as a first-class tool. An admin caller invokes
  `impersonate(project, role)` and receives a short-lived broker JWT for
  subsequent tool calls.
- Audit parity with HTTP. Every mutating tool call writes an
  `audit_events` row with the same shape an equivalent HTTP call produces.
  No bypass surface.
- SSE streams exposed as subscriptions. `pipeline_run.changed` and
  `.gate_blocked` become MCP resource subscriptions so agents react
  without polling.
- Flag-gated rollout. `CODER_MCP_ENABLED` (env, default off) gates `/mcp`;
  `projects.mcp_enabled` per-project tri-state gates project-scoped access.
  Backout is one env flip.

## Non-goals

- **stdio transport in v1.** Streamable HTTP only; stdio is a fast-follow.
- **OAuth 2.1 dynamic client registration.** Covered by spec
  [0050-oauth-for-mcp-clients](../wip/0050-oauth-for-mcp-clients.md)
  (claude.ai web custom-connector flow requires it). This spec covers
  bearer-token auth only.
- **Full API parity.** v1 ships the ~12 tools covering the 80% an agent
  needs. Obscure admin operations stay HTTP-only.
- **MCP Prompts.** Tools + resources are the v1 surface; Prompts deferred.
- **Per-tool rate limiting** beyond existing budget gates (spec 0031).
- **MCP for `coder-admin`** (the UI repo). MCP lives in `coder-core` only.
- **Self-hosted MCP client registry.**

## Scope

### Endpoint

`/mcp` is a FastAPI sub-app on `coder-core` using streamable-HTTP
transport (JSON-RPC 2.0). It is a peer of the existing `/v1/*` routes on
the same Cloud Run service. `GET /mcp/health` returns `{enabled, version,
tools: <count>}` when the fleet flag is on; 404 otherwise.

### Auth

The `initialize` request carries `Authorization: Bearer <token>`. The
adapter tries admin JWT → broker JWT → project API key in order, resolving
to a `CallerIdentity`. Unknown or expired tokens return JSON-RPC error
`-32001 unauthenticated`. Per-project opt-out (`projects.mcp_enabled=false`)
returns `-32003 project_mcp_disabled` for project-scoped callers; admins
bypass.

### v1 tool surface (12 tools)

**Reads (any authenticated caller, scope-filtered):**
- `list_tasks(project_id, role=?, status=?, limit=?)`
- `get_task(project_id, task_id)`
- `list_pipeline_runs(project_id, status=?, limit=?)`
- `get_pipeline_run(project_id, run_id)`
- `list_knowledge(project_id, artifact_type=?, folder=?)`
- `get_knowledge(project_id, artifact_type, artifact_id)`
- `get_metrics(project_id, period?)`

**Writes (role-gated):**
- `create_task(project_id, role, prompt, repo?)` — same permissions as
  `POST /v1/projects/{id}/tasks`.
- `approve_task_plan(project_id, plan_id)` — admin or project-api-key.
- `reject_task_plan(project_id, plan_id, reason)` — same.
- `submit_knowledge(project_id, artifact_type, body, ...)` — maps to the
  existing knowledge write endpoint; gated by the existing validator.

**Admin (admin-JWT only):**
- `impersonate(project_id, role)` — mints a broker JWT; writes
  `impersonate.issue_token` audit row attributing the admin actor.
- `override_pipeline_run(project_id, run_id, action)` — pause/resume/cancel.

`tools/list` returns only tools the caller is authorised to invoke:
admin JWT sees all 12; project-API-key caller sees 9 (no admin tools);
developer broker-JWT caller sees 7 (reads + `create_task` only).

### v1 resource surface

- `coder://projects/{id}/pipeline-runs/live` — subscribable; wraps
  the existing `pipeline_run.changed` SSE stream.
- `coder://projects/{id}/tasks/{id}/messages` — subscribable; wraps
  the `task_messages` feed for a live task.
- `coder://projects/{id}/metrics` — fetch-only; returns latest metrics
  rollup.

All resources are scoped to the caller's project by the same middleware
that gates the REST counterparts.

### Audit integration

Every mutating tool call writes an `audit_events` row before returning
success. Action strings reuse existing ones (`tasks.create`,
`task_plans.approve`, etc.). `actor_method='mcp'` distinguishes
MCP-initiated mutations from HTTP-initiated ones. A new action
`mcp.session_opened` is written on `initialize` so operators can see
"agent X connected at T" in the audit log.

### Impersonation flow

1. Admin opens MCP session with admin JWT.
2. Calls `impersonate(project_id, role)`.
3. Server mints broker JWT; returns `{token, role, project_id, exp}`.
4. Caller opens a new MCP session with that JWT as bearer.
5. Subsequent tool calls evaluate against the new role's caller identity.

Every audit row in a session has exactly one caller identity (D3 — no
swap-window ambiguity).

### Flags

`CODER_MCP_ENABLED` gates the endpoint entirely (default `false`).
`projects.mcp_enabled` tri-state: `NULL` = fleet inherit, `true` = opt in,
`false` = opt out even if fleet is on. Initial rollout caps to admin-only
(fleet flag on, no projects opted in).

## Acceptance criteria

- **AC1.** `GET /mcp/health` returns 200 `{enabled:true, version:"...", tools:<count>}` when `CODER_MCP_ENABLED=true`; 404 otherwise.
- **AC2.** `POST /mcp` with a valid `initialize` payload and bearer token returns server-info with capabilities advertising tools + resources + subscriptions.
- **AC3.** `tools/list` returns exactly 12 v1 tools each with name, description, and JSON-Schema input. Caller-filtered: admin JWT sees all 12; project-API-key sees 9; developer broker-JWT sees 7.
- **AC4.** `tools/call create_task` with a valid project-API-key caller creates a task row, dispatches the worker, and writes an `audit_events` row with `action='tasks.create'`, `actor_method='mcp'`, and the same `correlation_id` returned in the tool response.
- **AC5.** `tools/call impersonate(project_id, role='developer')` from an admin caller returns `{token, role, project_id, exp}`, writes `action='impersonate.issue_token'`, and the returned JWT passes verification on subsequent MCP calls.
- **AC6.** `resources/subscribe` on `coder://projects/{id}/pipeline-runs/live` delivers at least one `pipeline_run.changed` event within 5 s when a pipeline run on that project advances.
- **AC7.** `projects.mcp_enabled=false` on a project returns JSON-RPC `-32003 project_mcp_disabled` for any tool call scoped to that project; fleet flag stays on; other projects unaffected.
- **AC8.** `CODER_MCP_ENABLED=false`: the `/mcp` endpoint returns 404 on every method; no routes register. Backout verified.
- **AC9.** A cross-tenant tool call (e.g. `get_task` with another project's task id) returns JSON-RPC `-32004 not_found`. The `tests/isolation/` matrix is extended with MCP-path entries; CI drift check blocks any new MCP route not covered.
- **AC10.** Only `tools/list`, `tools/call`, `resources/list`, `resources/read`, `resources/subscribe` are handled; unknown methods return JSON-RPC `-32601 method not found`.

## Metrics

- **MCP session count (open)** — per project, per actor_type. Alert if zero for 7+ days after fleet enable (indicates no adoption).
- **Tool-call p50/p95 latency** by tool. Targets: reads ≤ 500ms p95, writes ≤ 2s p95, `impersonate` ≤ 300ms p95.
- **Tool-call error rate** by tool, by JSON-RPC error code. Target < 2% reads, < 5% writes.
- **Audit-event rate via MCP** (`actor_method='mcp'` rollup) — leading indicator of agent adoption.
- **Impersonation tokens minted/hr** — agent-driven impersonation volume, separate from HTTP-path impersonation.

## Decisions

- **D1 — One bearer per session.** Bearer fixed at `initialize`; role switch requires a new session. Simplifies audit attribution — no swap-window ambiguity for `actor` on audit rows.
- **D2 — Project API key blast radius unchanged.** MCP callers with a project API key have the same breadth as HTTP callers. No per-agent sub-keys in v1; key-rotation coverage via spec 0038. The OAuth extension (D2 footnote: claude.ai web requires OAuth 2.1) is tracked separately in spec 0050.
- **D3 — Impersonation: two sessions.** `impersonate` returns the token; caller opens a fresh session with it. Every row in a session has exactly one caller identity.
- **D4 — Subscription cap: 10 per session (hard).** Protects against pathological fan-out. 10 is generous for any honest agent.
- **D5 — External-only in v1; workers don't use MCP internally.** Workers continue using `KnowledgeRepoView` and HTTP. Dogfood revisit after external surface soaks.
- **D6 — Tool naming: flat snake_case verbs.** `list_tasks`, `create_task`, `approve_task_plan`.

## Links

- Design: [0049-mcp-agent-interface](../../designs/wip/0049-mcp-agent-interface.md)
- Related specs: [impersonation](./impersonation.md), [service-accounts](./service-accounts.md), [audit-log](./audit-log.md), [admin-panel](./admin-panel.md), [multi-tenancy](./multi-tenancy.md), [task-orchestration](./task-orchestration.md), [knowledge-api](./knowledge-api.md)
- Spec 0050: [oauth-for-mcp-clients](../wip/0050-oauth-for-mcp-clients.md) — OAuth 2.1 auth layer for MCP clients that cannot use bearer headers
- Runbook: [mcp-agent-interface-rollout](../../runbooks/mcp-agent-interface-rollout.md)
- Roadmap: Phase 7 — Trusted Autonomy

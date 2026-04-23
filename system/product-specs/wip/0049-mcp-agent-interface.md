---
id: '0049'
title: MCP agent interface — let external agents connect, impersonate, and drive Coder
type: spec
status: wip
owner: ro
created: 2026-04-23
updated: 2026-04-23
last_verified_at: 2026-04-23
served_by_designs: ['0049']
related_specs:
  - impersonation
  - service-accounts
  - audit-log
  - admin-panel
  - multi-tenancy
  - task-orchestration
  - knowledge-api
  - escalations
---

# 0049 — MCP agent interface

## Problem

Coder has a well-shaped internal API (project-scoped REST, impersonation
broker, audit trail, SSE streams) but no first-class way for an *external
agent* to connect to it. A human running Claude Code on a laptop today has
two options for "drive Coder": poke endpoints with `curl` by hand, or run
the in-tree `coder` CLI (`coder impersonate`, `coder project doctor`) which
covers only a sliver of the surface and talks to localhost by default. An
agent running somewhere else — another Claude Code session, a custom
orchestrator, a CI-initiated agent — has no connection story at all.

That's a gap on three axes:

1. **Impersonation is local-only.** The broker can mint role-scoped JWTs,
   and the CLI consumes them (spec 0007), but there is no protocol by
   which a non-Coder agent can authenticate, request a role, and then act
   *as that role* over a durable session. Agents that could usefully
   drive architect / PM / TM work have no seat at the table.

2. **Reading state is one-off.** A human-driven agent that wants to
   know "what's blocking run X? what's the reviewer's verdict on task
   Y? what does the metrics rollup show this week?" re-implements the
   HTTP client from scratch every time, or scrapes the admin panel.
   Neither composes.

3. **Admin actions are behind a Google OAuth wall.** Approving a spec,
   retrying a stuck task, granting a budget override, flipping a
   project's `auth_mode` — all of these are already capabilities, gated
   on admin JWTs. An agent acting under an operator's delegation has no
   standard handshake for those either.

The Model Context Protocol (MCP) is the shape the industry has
converged on for this — a JSON-RPC-over-HTTP-or-stdio protocol where
servers expose **tools** (callable functions), **resources** (readable
context), and **prompts** (parameterised prompt templates) to agent
clients. Every major agent client (Claude Code, Cursor, VS Code
extensions, custom orchestrators) speaks MCP. Adding an MCP server to
`coder-core` means "any agent anywhere can drive Coder" with no
bespoke integration.

The permission story is *already solved* by impersonation + audit:
MCP is a protocol wrapper, not a new permission model. Each MCP tool
call hands through the existing `require_project_auth` /
`require_admin` middleware and lands in the existing handler, which
already knows how to write an `audit_events` row.

## Users

- **External agent on an operator's laptop** — a Claude Code session
  outside Coder, wants to inspect pipeline state, start a task,
  approve a plan. Connects over streamable HTTP with the operator's
  broker JWT or project API key.
- **Long-running orchestrator agent** — a headless agent that watches
  Coder, reacts to SSE events, and calls tools. Needs durable
  connection + subscriptions + impersonation refresh.
- **Ops / SRE agent** — acts under an admin token to do fleet-wide
  work: retry stuck tasks across projects, surface metrics, flip
  flags, ack escalations.
- **Coder itself (dogfood)** — the worker fleet running against its
  own MCP surface. A PM worker drafting a new spec can query the
  architect's current view of the codebase via MCP; a reviewer
  worker can list related tasks via MCP. Not a v1 goal but shapes
  the design so it doesn't preclude it.

## Goals

- **One MCP endpoint on `coder-core`** that any MCP-speaking client
  can connect to over streamable HTTP, authenticate with a bearer
  token, and drive Coder's core capabilities.
- **Auth reuses today's tokens.** No new token format, no new
  lifecycle. A caller presents an existing project API key, broker
  JWT, or admin JWT; the MCP server maps that to `CallerIdentity` via
  the existing middleware and authorises every tool call the same
  way HTTP does.
- **Impersonation as a first-class tool.** An admin caller can invoke
  `impersonate(project, role)` and receive a short-lived broker JWT
  which subsequent tool calls on the same (or a new) MCP session use
  as their bearer — "act as the developer role on project acme"
  becomes a single tool call.
- **Audit parity with HTTP.** Every mutating tool call writes an
  `audit_events` row with the same shape, action, and correlation ID
  an equivalent HTTP call would produce. No bypass surface.
- **Surface the SSE streams as subscriptions.** `pipeline_run.changed`
  / `.gate_blocked` already exist as SSE; expose them as MCP
  resource subscriptions so agents react without polling.
- **Flag-gated rollout.** `CODER_MCP_ENABLED` fleet flag (default
  off) gates the `/mcp` endpoint; a second per-project flag
  (`projects.mcp_enabled`) gates access to that project's data once
  the server is up. Backout is one env flip.

## Non-goals

- **stdio transport in v1.** Streamable HTTP only. Local stdio
  (spawned subprocess, no network) is useful but adds a second
  transport + session model to maintain and isn't required for any
  named user. Add as a fast-follow once the HTTP shape is stable.
- **OAuth 2.1 dynamic client registration** (the 2025 MCP-auth
  draft). We already have three working token types; re-using them
  is less work and less surface than a full OAuth dance. Revisit
  when an MCP client actually demands it.
- **Full API parity.** Not every HTTP endpoint becomes an MCP tool.
  v1 ships the ~12 tools that cover the 80% of what an agent
  actually wants to do (listed in Scope). Obscure admin operations
  stay HTTP-only.
- **MCP Prompts as a surface.** Tools + resources are plenty; the
  `prompts/` category is a nicety, not a blocker. Deferred.
- **Per-tool rate limiting** beyond what the existing
  `DispatcherQueue` and budget gates cover. If an agent burns tokens
  by calling `create_task` in a tight loop, 0031 budgets catch it.
  Tool-call-rate limits are a phase 2 concern.
- **MCP for `coder-admin` (the UI repo)**. The admin panel stays a
  web app; MCP lives in `coder-core` only. An agent that wants
  "admin-panel-like" reads consumes MCP directly.
- **Self-hosted MCP client registry**. No.

## Scope

### In scope

1. **MCP server mounted on `/mcp` in coder-core.** FastAPI sub-app
   using the official Python MCP SDK (`mcp` package). Streamable-HTTP
   transport. JSON-RPC 2.0 framing per spec. The endpoint is a peer
   of the existing `/v1/*` REST routes on the same Cloud Run service.

2. **Bearer-token auth handshake.** The MCP `initialize` request
   carries an `Authorization: Bearer <token>` header. The adapter
   resolves the token into a `CallerIdentity` via the existing
   `require_project_auth` / admin-JWT verify path. Unknown or expired
   tokens → JSON-RPC error `-32001 unauthenticated`. Per-call the
   resolved identity is threaded into the handler; no ambient state.

3. **v1 tool surface (12 tools).** Grouped by capability tier:

   **Reads (any authenticated caller, scope-filtered):**
   - `list_tasks(project_id, role=?, status=?, limit=?)`
   - `get_task(project_id, task_id)`
   - `list_pipeline_runs(project_id, status=?, limit=?)`
   - `get_pipeline_run(project_id, run_id)`
   - `list_knowledge(project_id, artifact_type=?, folder=?)`
   - `get_knowledge(project_id, artifact_type, artifact_id)`
   - `get_metrics(project_id, period?)`

   **Writes (role-gated — the caller's resolved role must permit):**
   - `create_task(project_id, role, prompt, repo?)` — same
     permissions as `POST /v1/projects/{id}/tasks` today.
   - `approve_task_plan(project_id, plan_id)` — admin or project-api-key.
   - `reject_task_plan(project_id, plan_id, reason)` — same.
   - `submit_knowledge(project_id, artifact_type, body, ...)` — maps
     to the existing knowledge write endpoint; gated by the
     existing validator.

   **Admin (admin-JWT only):**
   - `impersonate(project_id, role)` — mints a new broker JWT,
     returns the token for the caller to reuse on subsequent
     requests. Writes an `impersonate.issue_token` audit row
     attributing the admin actor.
   - `override_pipeline_run(project_id, run_id, action)` —
     pause/resume/cancel, same as today's admin endpoint.

4. **v1 resource surface.** MCP resources are read-only URIs the
   client can subscribe to or fetch.
   - `coder://projects/{id}/pipeline-runs/live` — SSE-backed
     subscription (wraps the existing `pipeline_run.changed` stream).
   - `coder://projects/{id}/tasks/{id}/messages` — the `task_messages`
     feed for a live task.
   - `coder://projects/{id}/metrics` — the latest metrics rollup.
   - Scoped to the caller's project by the same middleware that
     gates the REST counterparts.

5. **Audit integration.** Every mutating tool call writes an
   `audit_events` row before returning success. Action strings reuse
   existing ones (`tasks.create`, `task_plans.approve`, etc.) —
   the only new action is `mcp.session_opened` (on initialize) so
   operators can see "agent X connected at T" in the audit log.
   `actor_method='mcp'` distinguishes MCP-initiated mutations from
   HTTP-initiated ones on the same action.

6. **Impersonation flow.** The admin-only `impersonate` tool is the
   bridge that makes "act as a worker" practical:
   - Admin opens MCP session with their admin JWT.
   - Calls `impersonate(project_id='acme', role='developer')`.
   - Server mints a broker JWT with role=developer, project=acme,
     standard TTL, returns it to the caller.
   - Caller issues a *new* MCP session using that JWT as the bearer
     (or reuses the same session — see open question OQ3).
   - Subsequent tool calls evaluate against the developer-role
     caller identity: only developer-appropriate tools are visible
     in `tools/list`, writes gated accordingly.

7. **Fleet + per-project flags.** `CODER_MCP_ENABLED` gates the
   endpoint entirely (default `false`). `projects.mcp_enabled`
   tri-state per-project (default `NULL` = fleet inherit; `true`
   opts in; `false` opts out even if fleet is on). Initial rollout
   caps to admin-only (fleet flag on, no projects opted in — the
   admin surface works but no project-scoped callers resolve).

8. **Tool visibility is caller-filtered.** `tools/list` returns only
   the tools the authenticated caller is authorised to invoke. A
   developer-role caller sees reads + `create_task` (of appropriate
   roles) but not `impersonate` or `approve_task_plan`. Avoids the
   "why did my tool call just fail with unauthorised" footgun.

### Out of scope

- stdio transport, OAuth 2.1 DCR, Prompts API, MCP-for-coder-admin.
- Per-tool rate limiting (use budgets + dispatcher queue already).
- MCP client authoring (we're the server).
- Streaming tool results (all v1 tools return bounded JSON).
- Encrypted session replay / persistent MCP session state (stateless
  per-request).

## Acceptance criteria

- **AC1.** `GET /mcp/health` returns 200 with
  `{enabled: true, version: "...", tools: <count>}` when
  `CODER_MCP_ENABLED=true`, 404 otherwise.

- **AC2.** `POST /mcp` with a valid `initialize` JSON-RPC payload
  and a valid bearer token returns a server-info response listing
  server name, version, and a capabilities object advertising
  tools + resources + subscriptions.

- **AC3.** `tools/list` returns exactly the 12 v1 tools, each with a
  name, description, and JSON-Schema input. A caller sees only
  tools authorised by their resolved `CallerIdentity`:
  admin-JWT caller sees all 12; project-API-key caller sees 9
  (no admin tools); broker-JWT developer caller sees 7 (reads +
  `create_task(role=developer)` only).

- **AC4.** `tools/call` with `create_task` + a valid
  project-api-key caller creates a task row, dispatches the
  worker, and writes an `audit_events` row with
  `action='tasks.create'`, `actor_method='mcp'`, and the same
  `correlation_id` returned in the tool response.

- **AC5.** `tools/call` with `impersonate(project_id='acme',
  role='developer')` from an admin caller returns
  `{token: "<jwt>", role: "developer", project_id: "acme", exp:
  "..."}`, writes an `audit_events` row with
  `action='impersonate.issue_token'`, and the returned JWT passes
  verification on subsequent MCP calls.

- **AC6.** `resources/subscribe` on
  `coder://projects/{id}/pipeline-runs/live` delivers at least one
  `pipeline_run.changed` event within 5 s when a pipeline run on
  that project advances.

- **AC7.** `projects.mcp_enabled=false` on a project: any tool call
  scoped to that project returns JSON-RPC error `-32003
  project_mcp_disabled`. The fleet flag stays on; other projects
  unaffected.

- **AC8.** `CODER_MCP_ENABLED=false`: the `/mcp` endpoint returns
  404 on every method. No routes register. Backout verified.

- **AC9.** A tool call that would violate multi-tenancy (e.g.
  `get_task(project_id='acme', task_id='<bravo's task>')`) returns
  JSON-RPC error `-32004 not_found`. The `tests/isolation/`
  matrix is extended with MCP-path entries so the drift check in CI
  blocks any new MCP route that's not covered.

- **AC10.** `tools/list`, `tools/call`, `resources/list`,
  `resources/read`, `resources/subscribe` are the only MCP methods
  handled; unknown methods return JSON-RPC `-32601 method not
  found`.

## Metrics

- **MCP session count (open)** — per project, per actor_type.
  Healthy range depends on rollout; alert if zero for 7+ days
  after fleet enable (indicates no adoption).
- **Tool-call p50 / p95 latency** by tool. Targets:
  reads ≤ 500ms p95, writes ≤ 2s p95, `impersonate` ≤ 300ms p95.
- **Tool-call error rate** by tool, by JSON-RPC error code.
  Target < 2% for reads, < 5% for writes.
- **Audit-event rate via MCP** (`actor_method='mcp'` rollup) — a
  leading indicator of actual agent adoption.
- **Impersonation tokens minted / hr** — separate from HTTP-path
  impersonation; shows agent-driven-impersonation volume.

## Open questions

- **OQ1 — MCP session lifetime.** Does one MCP session hold one
  bearer token for its lifetime (simple; forces a new session to
  switch roles), or can the session refresh/rotate the bearer
  mid-session (supports the impersonation handoff in a single
  session)? Leaning: v1 = one bearer per session; `impersonate`
  returns the new token and the client opens a new session with
  it. Simpler, auditable.

- **OQ2 — Project API key scope for MCP.** Today a project API
  key lets the caller hit any project-scoped HTTP endpoint. Same
  breadth via MCP means a shared project key used across several
  agents is a blast-radius concern. Leaning: no new mechanism in
  v1 (same as HTTP); spec 0038's rotation covers key compromise.
  Revisit if a phase-2 wants per-agent sub-keys.

- **OQ3 — Impersonation handoff UX.** After `impersonate()` returns
  a JWT, the client has to open a new MCP session to act as the new
  role. That's two round-trips where operators want one. Possible
  extension: `impersonate` also performs a session-level swap in
  the response so the same session starts handling subsequent calls
  as the impersonated role. Needs more thought on idempotency
  + audit attribution (whose actor on the audit rows during the
  "swapped" window?). Leaning: v1 = new session; document the
  idiom.

- **OQ4 — SSE subscription fan-out.** Each subscribed resource holds
  an SSE connection from MCP server → internal stream. At fleet
  scale (say 50 connected agents each watching 3 projects), that's
  150 concurrent SSE fan-outs. Current implementation handles ~20
  admin-panel connections fine. Phase 2 may need a shared fan-out
  broker. v1 cap: reject new subscriptions past
  `MCP_MAX_SUBSCRIPTIONS_PER_SESSION=10` with JSON-RPC error.

- **OQ5 — Dogfood: should workers use MCP?** The developer worker
  today reads knowledge via `KnowledgeRepoView` (direct GitHub).
  The architect worker fetches via the HTTP API. Using MCP
  internally would unify the fetch path and prove the surface
  under real load — but it adds an in-process MCP client dep and
  latency. Leaning: v1 external-only; revisit when the surface
  is battle-tested externally.

- **OQ6 — Tool naming convention.** `list_tasks` vs `tasks.list`
  vs `tasks/list`. MCP spec is neutral. Leaning: flat
  snake_case verbs (`list_tasks`) since that reads naturally in
  tool-call contexts and matches the emerging convention in most
  MCP servers shipped to date.

## Links

- Design: [0049](../../designs/wip/0049-mcp-agent-interface.md)
- Related specs: [impersonation](../active/impersonation.md),
  [service-accounts](../active/service-accounts.md),
  [audit-log](../active/audit-log.md),
  [admin-panel](../active/admin-panel.md),
  [multi-tenancy](../active/multi-tenancy.md),
  [task-orchestration](../active/task-orchestration.md),
  [knowledge-api](../active/knowledge-api.md)
- Roadmap: Phase 7 — Trusted Autonomy (agents driving Coder is
  the autonomy increase this unlocks)

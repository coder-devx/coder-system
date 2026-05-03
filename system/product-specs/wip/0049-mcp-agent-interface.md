---
id: '0049'
title: MCP agent interface — let external agents connect, impersonate, and drive Coder
type: spec
status: wip
owner: ro
created: 2026-04-23
updated: 2026-04-24
last_verified_at: 2026-04-24
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
parent: knowledge-and-admin
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

## Decisions (closed open questions)

- **D1 — MCP session lifetime: one bearer per session.** The
  bearer is chosen at `initialize` and fixed for the session's
  life. Agents stay in-role indefinitely on one session; a role
  switch requires a new session with a different bearer. Rejected
  the in-session-rotation alternative because it complicates audit
  attribution (who owns the rows during a swap window?) for little
  gain — most agents authenticate once at startup and never
  switch.

- **D2 — Project API key blast radius stays as-is.** A project API
  key used via MCP has the same breadth it does via HTTP today. No
  new per-agent sub-keys in v1. Key compromise is already covered
  by 0038 rotation. Revisit only if a concrete abuse pattern
  emerges.

  > **Footnote (2026-04-25).** The OAuth-for-MCP-clients side of D2
  > ("we already have three working token types; re-using them is
  > less work") was reopened in
  > [0050](./0050-oauth-for-mcp-clients.md) — claude.ai web's
  > custom-connector flow only supports OAuth 2.1, not bearer
  > headers, so the punt has a concrete cost. The project-API-key
  > blast-radius half of D2 stands; only the OAuth half is being
  > revisited.

- **D3 — Impersonation handoff: two round-trips.** `impersonate`
  returns `{token, role, project_id, exp}`; the client opens a
  fresh MCP session with the new token to act as the role. Every
  audit row in a given session has exactly one caller identity —
  no swap-window ambiguity. Documented as the canonical idiom.

- **D4 — Subscription cap: 10 per session (hard).** Cheap
  insurance against a pathological client opening thousands of
  subscriptions on one session. 10 is generous enough that no
  honest agent hits it. If fleet-wide SSE fan-out ever becomes a
  load problem, solve it then with a shared-broker layer — not a
  v1 concern.

- **D5 — External-only v1; workers don't use MCP internally.**
  Developer worker keeps reading knowledge via `KnowledgeRepoView`;
  architect keeps using the HTTP API. Revisit dogfood only after
  the external surface has soaked under real load.

- **D6 — Tool naming: flat snake_case verbs.** `list_tasks`,
  `create_task`, `approve_task_plan`. Reads naturally in tool-call
  contexts and matches the convention most shipped MCP servers use.

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

## Working log

In-flight notes to bridge sessions. Deleted when this WIP folds into
`active/`.

### Session handoff — 2026-04-25 (later)

**Stage 3 complete; soaking.** `MCP_ENABLED=true` on prod (set in
the same Cloud Run revision that flipped `MCP_OAUTH_ENABLED`; see
spec 0050's working log for the timing). `coder.mcp_enabled=true`
flipped at 12:28 UTC via `POST /v1/_admin/projects/coder/mcp-enabled`
— the `coder` dogfood project is the first project actively
serving project-scoped MCP. End-to-end smoke from outside the
cluster passes:

```sh
# AC1
curl -sS https://coder-core-8534948335.europe-west1.run.app/mcp/health
# → {"enabled":true,"version":"0.0.3","protocol_version":"2025-03-26",
#    "tools":[...13 names...],"resources":[...3 URIs...]}

# AC2 + AC3 (project-key caller — the 9 non-admin tools)
curl -sS -X POST .../mcp -H "Authorization: Bearer $CODER_API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize",...}'
# → 200 with capabilities {tools, resources{subscribe:true}}
```

**Live audit evidence** (fleet `/v1/_admin/audit-events`):

```
12:28:32  project.set_mcp_enabled        admin:coder@vibedevx.com   project=coder
11:49:08  mcp.session_opened             api_key                    project=coder
11:25:42  mcp.session_opened             oauth:coder@vibedevx.com   (admin-equivalent)
10:24:36  mcp.session_opened             oauth:coder@vibedevx.com
10:24:01  mcp.session_opened             oauth:coder@vibedevx.com
08:31:32  mcp.session_opened             oauth:coder@vibedevx.com   ← first OAuth-driven session
```

Three caller paths exercised live: project-API-key (this session),
admin JWT (curl), and OAuth-issued tokens minted by claude.ai web
via 0050. AC4 + AC5 (audit-row attribution) implicitly verified
since these rows landed with the right `actor_method` mapping.

**Remaining for fold-to-active** (per AGENTS.md rule 5, ≥30 days
clean prod soak):

1. Watch the audit log for any `actor_method='mcp'` 5xx or
   `mcp.session_opened` from unexpected actors.
2. Set additional `projects.mcp_enabled=true` only on demand.
3. Around 2026-05-25, fold spec + design into `active/`.

**Operational note — task-cleanup, 2026-04-25.** The dogfood
project (`coder` tenant) had 17 stale tasks from the 0049/0023/
0024/0019/0012 ramp — most queued or stuck running for shipped
work. Cleared via `POST /v1/projects/coder/tasks/{id}/override`
with `{"action":"reject"}` (project-API-key auth, sets
`stage=REJECTED` only). 15/17 succeeded; 2 pre-pipeline legacy
tasks (`stage IS NULL`) couldn't be overridden — they're inert
because the dispatcher only picks up rows with a non-null stage.
**Known gap surfaced by this cleanup:** `action=reject` only
updates `stage`; `status` stays at its pre-reject value. The
behavior is correct (dispatcher gates on stage) but the admin
panel + MCP `list_tasks(status=...)` filter still surface
rejected tasks under their old status until manual cleanup.
Worth a one-line follow-up in `api/tasks.py:969` to set
`status=FAILED` (or a new `CANCELLED`) alongside the stage flip.

### Session handoff — 2026-04-24 (end-of-session)

**Status.** Stage 1 + nine Stage 2 slices + the SSE resource slice
merged behind `CODER_MCP_ENABLED=false`. All 13 v1 tools and all 3
v1 resources (pipeline-runs/live, tasks/{id}/messages, metrics)
ship on `coder-core` `main`. The admin-UI toggle lives on
`coder-admin`. **Stage 2 is done; next step is Stage 3 rollout.**

> **Update 2026-04-24 (late session).** SSE resources landed via
> [coder-core#20](https://github.com/coder-devx/coder-core/pull/20).
> Went with the hand-rolled dispatcher (not the `mcp` Python SDK) —
> see the PR description for reasoning. Subscription cap (D4)
> enforced per `(actor, bound_project_id)` since the current
> transport is session-less. The "What to start with next session"
> checklist below is kept for historical context but is satisfied
> by the merged PR. Stage 3 rollout procedure is written up as
> [mcp-agent-interface-rollout](../../runbooks/mcp-agent-interface-rollout.md)
> — don't flip `CODER_MCP_ENABLED` until an external agent is
> within a day of being onboarded (see runbook's "Stage 3 is
> demand-driven" section).

Design decisions D1–D6 above are locked — don't re-litigate. Relevant
ones for the SSE slice: D1 (one bearer per session — role switch needs
a new session), D4 (hard cap 10 subscriptions per session), D6 (flat
snake_case tool/resource naming).

#### What's already in place

**Transport** — `coder_core/mcp/app.py`

- Hand-rolled JSON-RPC 2.0 over plain HTTP POST (no `mcp` Python SDK
  dep yet — skipped in Stage 1 since tools-only didn't need it).
- Handles `initialize`, `tools/list`, `tools/call`, `ping`.
- Per-request contextvar threads `correlation_id` to tool handlers.
- `_ParamError`, `MCPAuthError`, `ValidationError`, `HTTPException`
  all translate to proper JSON-RPC error codes.

**Auth adapter** — `coder_core/mcp/auth.py`

- `resolve_caller` tries: admin JWT → broker JWT → project API key.
- `authorise_for_project` enforces per-project opt-out via
  `projects.mcp_enabled`; admin bypasses.
- Broker-JWT revocation check via `ImpersonationSessionRow.revoked_at`.

**Tool registry** — `coder_core/mcp/tools/__init__.py`

- 13 tools in stable order.
- `ToolDef` has `required_admin` for visibility filtering in
  `tools/list`.
- Thin-shim pattern: each tool delegates to an existing HTTP handler
  via `request_stub_with_correlation_id`.

`SSEBroker` already exists in `coder-core` and is consumed by the admin
panel today. Pipeline-run events flow through it as
`pipeline_run.changed` / `pipeline_run.gate_blocked`.

#### The SSE slice — what needs to happen

Scope (from the "v1 resource surface" subsection above):

- Three resources:
  - `coder://projects/{id}/pipeline-runs/live` (subscribable) — wraps
    existing `pipeline_run.changed`.
  - `coder://projects/{id}/tasks/{id}/messages` (subscribable) — wraps
    the `task_messages` feed.
  - `coder://projects/{id}/metrics` (not subscribable, just fetch) —
    returns the metrics rollup.
- Three new JSON-RPC methods: `resources/list`, `resources/read`,
  `resources/subscribe`.
- Per-session subscription cap = 10 (already in config as
  `mcp_max_subscriptions_per_session`, per D4).

**Transport change required.** The current `app.py` returns a single
`JSONResponse` per request. Subscriptions need the server to hold a
response stream open and push multiple JSON-RPC notification frames.
Two paths:

- **Option A — adopt the `mcp` Python SDK now.** Its
  `streamable_http_app()` handles subscription plumbing + reconnection
  + spec-compliant event-id framing. Trade-off: adds a runtime dep and
  requires refactoring the existing tool registry to the SDK's
  decorator pattern. The SDK is mature enough (it's what Anthropic's
  own servers use). **Recommended.**
- **Option B — hand-roll SSE on top of existing app.** FastAPI has
  `StreamingResponse` for SSE. Keep the tool surface untouched, just
  add a POST `/mcp` variant (or a separate GET for SSE channel opening
  per the MCP spec) that serves `text/event-stream`. Smaller diff,
  less spec-compliant, harder to debug from an MCP client's
  perspective.

Pick A unless there's a strong reason not to.

**Files to touch for Option A:**

- `src/coder_core/mcp/app.py` — wrap existing handlers in the SDK's
  `Server` construct, mount via `streamable_http_app()`.
- `src/coder_core/mcp/resources/` (new package) — one module per
  resource with `read` + optional `subscribe` generator.
- `src/coder_core/mcp/tools/__init__.py` — likely needs adapting to
  the SDK's tool-registration API (small).
- `pyproject.toml` — `uv add mcp`.
- Tests: `tests/test_mcp_resources.py` — subscribe + deliver one
  event on a pushed `pipeline_run.changed`.
- Isolation manifest: no entries needed (MCP already noted as
  project-id-via-body, not URL).

#### Operational state

- Fleet flag `CODER_MCP_ENABLED` is off in prod. Leave off until an
  external agent is actually being onboarded.
- `projects.mcp_enabled` is `NULL` for every project (fleet default).
- Prod image: whatever the latest merge landed as. All today's PRs
  deploy via push-to-main CI.

#### Known debt noted in today's commits

- ~~`submit_knowledge` update-of-missing-artifact leaks
  `-32603 internal` instead of `-32602 invalid_params`.~~ The
  registry-not-found path was already correct (HTTPException 404 →
  `-32602`); the actual leak was *missing required arguments*
  bypassing `tools/call`'s arg-shape check (only `project_id` was
  validated). Fixed via [coder-core#23](https://github.com/coder-devx/coder-core/pull/23):
  `_handle_tools_call` now walks `input_schema['required']` and
  raises `_ParamError` (→ `-32602`) for any missing field, naming
  them in the message. Verified live in prod 2026-04-25.
- Worker pipeline can't reliably land multi-file code tasks. Today's
  dogfood attempts on three slices hung at 20–25 min with no PR. Root
  cause is multi-factor (cold context, cold dep cache, serial
  pipeline stages, `max_turns=50` too tight, subprocess plumbing
  overhead). The spawned E2E worker-health-probe WIP chip-dropped
  earlier today is the right place to track this.
- PR #9 (orphan-dispatch-reaper) closed as stale today. If 0042's
  `zombie_executing` pattern slips and operators see runs stuck at
  `status='running'`, the reaper code in the closed PR is still
  valuable — open a fresh PR rebased on current `main`.

#### What to start with next session

1. Read this note + the "v1 resource surface" and "MCP server mounted
   on `/mcp`" subsections of Scope above.
2. Decide Option A vs. Option B.
3. If A: `uv add mcp`, then draft one resource end-to-end
   (`pipeline-runs/live`) to prove the SDK integration.
4. Add a dedicated test that simulates an `SSEBroker.publish` and
   asserts the subscribed MCP client receives the notification.
5. Add the other two resources once the pattern holds.
6. Ship as one PR (this slice is a single coherent change).

Then Stage 2 is done; Stage 3 is rollout (canary on `coder`, soak,
fleet-flag flip).

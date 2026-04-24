---
id: mcp-agent-interface-rollout
title: MCP agent interface — Stage 3 staged rollout
type: runbook
status: active
owner: ro
created: 2026-04-24
updated: 2026-04-24
last_verified_at: 2026-04-24
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [gcp]
---

# MCP agent interface rollout

The MCP server code (transport, 13 tools, 3 resources, subscription
plumbing, audit integration) is deployed on `coder-core` and
flag-gated on `CODER_MCP_ENABLED`. This runbook covers the staged
rollout — flip the fleet flag, canary on one project, watch, then
expand.

Product view:
[spec 0049](../product-specs/wip/0049-mcp-agent-interface.md).
Design: [design 0049](../designs/wip/0049-mcp-agent-interface.md).
Same fleet-flag-plus-per-project pattern as
[auto-approve-rollout](./auto-approve-rollout.md); the project-level
switch (`projects.mcp_enabled`) is tri-state the same way, with the
same beats-fleet-flag semantics.

## What's wired on prod today (as of 2026-04-24)

- `coder-core` ships the `/mcp` route conditionally on
  `settings.mcp_enabled`. Off → `GET /mcp/health` returns 404; route
  never binds (AC8).
- `CODER_MCP_ENABLED` env var is unset (→ `false`) on the Cloud Run
  service. `/mcp/health` currently 404s on prod.
- `projects.mcp_enabled` column exists on every project row,
  defaults to `NULL` (fleet-inherit). Admin UI has a toggle on the
  project page. Zero projects opted in.
- Image carries the Stage 1 + 2 code: 13 tools, 3 resources, the
  JSON-RPC methods
  `initialize`/`tools/list`/`tools/call`/`resources/list`/`read`/`subscribe`/`ping`.

## When to run this

- **Prerequisite** for flipping: a concrete external agent being
  onboarded (see "Stage 3 is demand-driven" below). Don't flip
  speculatively — the spec carries a zero-adoption alert after 7
  days, and leaving the flag on with nobody using it also widens the
  surface for no gain.
- Stage 3 → 4 → 5 runs left-to-right with watch periods in between.
  Don't compress stages.

## Who can run this

Operator with `run.admin` on the `vibedevx` project (for env flips)
and an admin JWT for the project PATCH + smoke calls. Stage gating is
a **product decision**, not SRE — approval sits with the project
owner before each flag flip.

## Prerequisites

- [coder-core#20](https://github.com/coder-devx/coder-core/pull/20)
  and the Stage 2 slice ancestors merged to `main`, image promoted.
- Fleet verification: image's `/mcp/health` still returns 404 with
  `CODER_MCP_ENABLED` unset. Sanity check:
  ```sh
  curl -sS -i https://coder-core-<hash>.a.run.app/mcp/health
  # Expect HTTP/2 404
  ```
- Admin JWT in hand (minted via the existing admin flow) — needed
  for `initialize` + `tools/list` against the flipped endpoint.

## Steps

### 1. Stage 3 — flip the fleet flag, admin-only

Flip `CODER_MCP_ENABLED=true` on the service. No project opted in
yet, so only admin callers can reach anything project-scoped. AC3
guarantees `tools/list` with a project-API-key returns `-32004
not_found` until Stage 4 opts a project in, which is the expected
shape.

```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=CODER_MCP_ENABLED=true
```

Verify:

```sh
curl -sS https://coder-core-<hash>.a.run.app/mcp/health
# → {"enabled":true, "version":"...", "tools":[…], "resources":[…]}
```

Then an `initialize` + `tools/list` with the admin JWT — both should
succeed and `tools/list` should return 13 tools including
`impersonate` and `override_pipeline_run` (admin-only visible):

```sh
ADMIN_JWT=...  # your admin session token
curl -sS -X POST https://coder-core-<hash>.a.run.app/mcp \
  -H "Authorization: Bearer $ADMIN_JWT" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq '.result.tools | length'
# → 13
```

**Watch for 72 h minimum.** Tail `mcp_session_opened` audit rows and
the `actor_method='mcp'` rollup. Zero rows is fine at this stage
(nobody's expected to use the endpoint yet) — the point of the soak
is confirming the flip didn't regress anything else. Red flags:
spike in 5xx on `/mcp`, `/v1/*` latency regression (the MCP router
shares the service), or any unhandled exception tagged `mcp.app`.

### 2. Stage 4 — opt in one canary project

Pick a project (recommend `coder` — dogfood). Flip its
`projects.mcp_enabled` to `true` via the admin API:

```sh
curl -sS -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"mcp_enabled": true}' \
  https://coder-core-<hash>.a.run.app/v1/projects/coder
```

Now that project's API-key holder can drive Coder via MCP. Hand the
project's API key (or an impersonation-minted broker JWT) to the
onboarding agent and verify the round-trip:

- Agent calls `initialize` → gets server-info + capabilities.
- Agent calls `tools/list` → sees the 9 reads + writes (no admin
  tools).
- Agent calls one tool (e.g. `list_pipeline_runs`) → gets a
  structured result.
- Agent subscribes to `coder://projects/coder/pipeline-runs/live`
  → receives `pipeline_run.changed` notifications when runs
  advance.

Parallel smoke from an admin shell (independent of the agent):

```sh
# Project API-key scoped call — must resolve
PROJECT_KEY=...
curl -sS -X POST https://coder-core-<hash>.a.run.app/mcp \
  -H "Authorization: Bearer $PROJECT_KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_pipeline_runs","arguments":{"project_id":"coder"}}}'
```

**Watch for a week.** The metrics worth pinning:

- Tool-call p50 / p95 per tool. Spec targets: reads ≤ 500 ms p95,
  writes ≤ 2 s p95, `impersonate` ≤ 300 ms p95. A p95 above target
  for any tool is not a rollback by itself but is a flag for the
  next planning cycle.
- Tool-call error rate per JSON-RPC error code. A sustained >5% on
  reads or >10% on writes is a rollback signal — usually traces to
  a specific tool's argument-shape mismatch.
- Audit-event rate with `actor_method='mcp'`. If an agent is driving
  real work this number should track pipeline-run creations + knowledge
  submissions at a reasonable ratio.
- Subscription slot counts via
  `coder_core.mcp.resources._subscriptions.active_count` (wired for
  observability). If any caller sits at cap (10) for hours, suspect
  a leak — check for subscribes without matching unsubscribes in
  the audit log.

### 3. Stage 5 — expand to the rest of the fleet

After a week of steady canary metrics, flip additional projects on
as demand appears. Opt-in is per-project, not fleet-wide — leave the
rest of `projects.mcp_enabled` as `NULL` (fleet-inherit) and flip
only the projects you've agreed to onboard. Treat each new project
as its own mini-soak (48 h) before promoting the next.

Don't set `projects.mcp_enabled=true` on every project at once even
once stage 5 is "done." A NULL that fleet-inherits to `true` is the
same as an explicit `true`, but the NULL stays meaningful if the
fleet flag later goes to `false` for scoped rollback.

## Rollback

**Fleet rollback** — flip off, affects every project:

```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=CODER_MCP_ENABLED=false
```

Route unbinds on next revision roll. Any open subscription streams
error on the client side (connection drops) but no server-side state
persists — in-process broker queues garbage-collect.

**Project-scoped rollback** — leave the fleet flag on, flip one
project off:

```sh
curl -sS -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -d '{"mcp_enabled": false}' \
  https://coder-core-<hash>.a.run.app/v1/projects/<id>
```

Per-project `false` beats the fleet flag regardless (admin callers
bypass via the resolver). Useful if one project's agent is
misbehaving and the rest of the fleet should stay up.

## Success condition

- `/mcp/health` returns 200 with the expected tool + resource count.
- `tools/list` returns the spec's 13 v1 tools; `resources/list`
  returns the 3 v1 resources.
- `audit_events` has `mcp.session_opened` rows attributed to the
  onboarded agent's actor.
- Auditable tool-call rows (`action=tasks.create` etc. with
  `actor_method='mcp'`) show up for any mutating call the agent
  makes.
- Subscription streams deliver `pipeline_run.changed` events to the
  agent within 5 s of publish (AC6, verified in CI against
  [coder-core/tests/test_mcp_resources.py](https://github.com/coder-devx/coder-core/blob/main/tests/test_mcp_resources.py)).

## Stage 3 is demand-driven

Unlike the auto-approve rollout which earns value on its own
(expiring windows save operator clicks), MCP earns value only when
an agent is actually calling it. Keep `CODER_MCP_ENABLED` off until
the first external agent is within a day of being onboarded — the
spec's zero-adoption alert fires at 7 days and the surface is pure
attack surface until then. "Flip it now so we can see if it works"
is what the CI tests are for, not prod.

## If something goes wrong

- **`/mcp/health` still 404 after flag flip** — env var name gotcha.
  pydantic-settings has no prefix, so it's `CODER_MCP_ENABLED` (not
  `CODER_CORE_MCP_ENABLED`). Verify:
  `gcloud run services describe coder-core ... | grep MCP_ENABLED`.
- **Agent gets `-32001 unauthenticated` with a known-good key** —
  token-type mismatch at the resolver. Walk the auth paths: admin
  JWT checks type="admin"; broker JWT checks the broker signature
  and revocation row; API key does a constant-time hash compare
  over active projects. Dump the token (NOT to logs — local only)
  and check which branch it should have taken.
- **Agent gets `-32003 project_mcp_disabled`** — the project row has
  `mcp_enabled=false` explicitly. Either Stage 4 was skipped for
  this project, or a per-project rollback was left in place.
- **Subscription stream delivers ack but no subsequent events** —
  agent subscribed before the upstream event source was emitting.
  Check that the relevant domain event (pipeline run transition,
  message create) actually fires to the SSE broker — grep the
  service logs for `sse_subscribe` with the project_id, then for
  matching `publish` calls. If the broker's empty, the event source
  is the bug, not MCP.
- **Cap exceeded (`-32005`) from a legit client** — 10 concurrent
  subscriptions per `(actor, bound_project_id)` tuple. A
  high-concurrency client should reuse one subscription and
  multiplex server-side instead of opening N. If demand is real,
  raise `MCP_MAX_SUBSCRIPTIONS_PER_SESSION` on the service (default
  10, config in `coder_core.config.Settings`).

## Related

- Runbook:
  [auto-approve-rollout](./auto-approve-rollout.md) — same
  fleet-flag + per-project opt-in shape.
- Runbook: [deploy-coder-core](./deploy-coder-core.md) — image
  promotion, which is the prerequisite for this runbook's prereqs.
- ROADMAP entry: Phase 7 / 0049.
- AGENTS.md rule 5 — this runbook folds the 0049 WIP spec into
  `active/` once the fleet has been on for ≥ 1 month without a
  rollback.

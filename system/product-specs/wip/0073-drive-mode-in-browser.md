---
id: "0073"
title: Drive mode — operator role takeover in the browser
type: spec
status: wip
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
summary: ~
served_by_designs: ["0073"]
related_specs:
  - impersonation
  - admin-panel
  - mcp-agent-interface
parent: ~
---

# Drive mode — operator role takeover in the browser

## Problem

The active design [`impersonation.md`](../../designs/active/impersonation.md)
describes a system where the operator can take over any role in any
project. In practice today, taking over a role requires the
`coder impersonate <role> --project=X` CLI plus a local Claude Code
or Cursor session — there is no in-browser takeover surface.

A live walk on 2026-05-09 confirmed the gap: searching the command
palette for `drive` returns only documents that mention the word; no
action exists. The closest browser surface is `SpecTalk.tsx`, which
is shipped as a frozen demo with a synthetic conversation and no
backend wiring.

The cost of this gap: when a worker is stuck in a way no automated
retry will fix (ambiguous spec, cross-spec design tension, wrong
input artifact), the operator's only path is "open a terminal,
authenticate, run the CLI, drive Claude Code locally". The browser
panel — the place the operator already is — cannot help.

## Users / personas

- **Operator who just spotted an architect task spinning on a
  contradictory spec.** Today: opens a terminal, runs `coder
  impersonate architect --project=coder`, opens a local Claude
  session against the issued token. After: clicks `drive · architect`
  on the project page, gets a chat surface in the browser scoped to
  the architect's tools and knowledge.
- **PM consultant joining for one decision.** Today: needs CLI
  setup, GCP creds, a local agent. After: opens the panel, joins a
  drive session, leaves no local artifact behind.
- **Audit reviewer.** Today: drive sessions exist only as CLI tokens
  in audit logs. After: each browser drive session is a first-class
  `audit_event` chain with a session-level `correlation_id`,
  retrievable from the audit page.

## Goals

When this ships:

- A new `/drive/{project}/{role}` route renders an in-browser chat
  surface attached to a server-issued role-scoped impersonation
  token.
- The token is the same shape as today's CLI-issued impersonation
  token (same scopes, same expiry, same audit tag) — the surface
  changes, the trust model does not.
- Every operator action in drive mode (sent message, confirmed tool
  call, accepted edit) writes an `audit_event` with
  `actor=human:{email}`, `role={role}`, `correlation_id={session_id}`.
- The session has a visible expiry countdown and a `[revoke
  session]` action that revokes the impersonation token immediately
  and locks the conversation.
- `SpecTalk.tsx` is removed or folded into the same surface as a
  spec-scoped invocation (`/drive/{project}/architect?spec=…`); we
  do not maintain two parallel chat surfaces.

## Non-goals

- A new authorisation model. Drive sessions reuse the existing
  impersonation token machinery (multi-tenancy, service-account
  brokerage, expiry).
- Persistent multi-operator sessions. One drive session = one
  operator at a time. Co-presence is out of scope.
- Replacing the CLI flow. The CLI continues to work; drive mode is a
  parallel browser entry point.
- Custom tooling per role beyond what the role's worker contract
  already exposes. Drive mode runs the same tools the autonomous
  worker would.

## Scope

In:

- New route `/drive/{project_id}/{role}` in `coder-admin`. Three-pane
  layout: role context (left), conversation (center), scratch +
  artifact preview (right).
- Server endpoint `POST /v1/projects/{id}/drive/sessions` returning
  `{session_id, role, token, scopes, expires_at}`. Reuses the
  existing impersonation token issuance code path; adds a
  `session_kind=drive` discriminator for audit.
- SSE channel `/v1/projects/{id}/drive/sessions/{session_id}/events`
  streaming turn-level updates (assistant deltas, tool_use,
  tool_result) to the browser. Reuses the pipeline-events SSE
  transport pattern.
- A small `<SessionBanner/>` component visible site-wide while a
  drive session is active: amber-tinted, shows role, project,
  countdown, `[revoke]`.
- Audit integration: every conversation turn that triggers a tool
  call writes an `audit_event` whose `correlation_id` matches the
  session id; the session-start event references the issuing
  operator email and the impersonation token id (last 8 chars).
- A "writes to audit" chip next to the send button so the operator
  always knows their actions are recorded.
- `SpecTalk.tsx` deleted or replaced by a redirect to drive-mode for
  the architect role on the relevant spec.

Out:

- Multi-operator co-presence.
- Persistent in-panel chat history beyond the session token's
  lifetime (operators can copy out; we do not store transcripts
  beyond the audit envelope and retention policy of the existing
  Claude turns table).
- A new model selector specific to drive mode. Drive uses the
  role's configured model unless the operator explicitly routes
  via `?model=…`.

## Acceptance criteria

- **AC1.** From any project page, an action (Now row, project
  Overview, command palette) launches `/drive/{project}/{role}`.
  The first interaction issues a server-scoped impersonation token
  with `session_kind=drive` and writes a session-start
  `audit_event`.
- **AC2.** The conversation pane streams Claude turns over SSE in
  real time; tool calls are rendered with their `input` and
  `output` JSON inline. Each turn is timestamped (mono).
- **AC3.** Every operator-side action (send message, confirm tool
  call, accept edit) writes an `audit_event` with
  `actor=human:{email}`, `role={role}`, `correlation_id={session_id}`,
  recoverable from `/admin/audit?correlation_id=…`.
- **AC4.** A persistent `<SessionBanner/>` is visible site-wide
  while a drive session is active; the countdown reflects the
  token's `expires_at` and decrements live.
- **AC5.** `[revoke session]` invalidates the impersonation token
  server-side, terminates the SSE stream, locks the composer,
  and writes a `session_revoked` audit event within 2s.
- **AC6.** `SpecTalk.tsx` is removed from `coder-admin`. The
  previous route `/projects/{id}/specs/{specId}/talk` redirects to
  `/drive/{project}/architect?spec={specId}`.
- **AC7.** A drive session for a role the operator does not have
  permission to take over returns 403 with a typed error code; the
  panel renders this as a "request access" CTA rather than a 500.

## Metrics

- Number of operator escalations resolved without leaving the
  browser: emerges from zero post-ship and trends up.
- CLI impersonation usage: tracked but not eliminated; we expect
  drive mode to absorb the casual takeovers, leaving CLI for
  bulk / scripted work.
- Session-start to first tool call median: target ≤ 5s on a warm
  load.

## Open questions

- Whether the scratch panel persists across sessions (localStorage
  per project + role) or only for the active session. Defer to
  design.
- How drive mode interacts with auto-approve (WIP 0040). If a worker
  has auto-approve enabled and the operator is mid-drive, do we
  pause auto-approve for the session? Defer to design.
- Token lifetime default. Today CLI tokens default to 60min; drive
  mode probably wants the same. Confirm in design.

## Links

- ADR: [0031](../../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- Design: [0073](../../designs/wip/0073-drive-mode-in-browser.md)
- Depends on: [0069](./0069-canonical-project-state.md)
- Related: [impersonation](../active/impersonation.md), [admin-panel](../active/admin-panel.md), [mcp-agent-interface](../active/mcp-agent-interface.md)

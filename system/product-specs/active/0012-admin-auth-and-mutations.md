---
id: "0012"
title: Admin panel auth and mutations
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-11
served_by_designs: []
related_specs: ["0003", "0010"]
---

# Admin panel auth and mutations

**Phase:** Now (close the dev loop)
**Progress:** 7 / 7 acceptance criteria

## Problem

The admin panel is read-only and has no authentication. Anyone with the
URL can view projects, knowledge, and pipeline state. The human operator
has no way to intervene through the UI — creating tasks, retrying
failures, overriding decisions, and approving merges all happen through
direct API calls or the CLI.

For self-hosting, the admin panel is the human's primary control surface.
It needs to be secure and it needs write capabilities.

## Users

- **Human operator** — needs a secure, usable interface to monitor and
  control the Coder system.

## Goals

- Google OAuth authentication (single user initially, expandable).
- Task lifecycle mutations: create, retry, pause, resume, override.
- Knowledge browser with edit capability (update specs, mark ACs).
- Real-time pipeline view (WebSocket or SSE, not polling).

## Non-goals

- Multi-user RBAC (single operator for now).
- Full knowledge repo editing (complex merges, conflict resolution).
  Simple frontmatter + body edits only.
- Mobile-responsive design.

## Scope

### Auth

Google OAuth 2.0 flow in `coder-core`, session stored as an HTTP-only
cookie. Admin panel redirects to login if no valid session. Single
allowed email initially (configured via env var), expandable to a
domain allowlist.

### Mutations

New API endpoints and corresponding UI:

- `POST /v1/projects/{id}/tasks` — create a task with role, prompt, repo.
- `POST /v1/projects/{id}/tasks/{id}/override` — pause, resume, retry,
  skip, reject (from spec 0010).
- `POST /v1/projects/{id}/tasks/{id}/approve-merge` — human sign-off
  to merge the PR.
- `PUT /v1/projects/{id}/knowledge/{type}/{id}` — update a knowledge
  artifact's body and frontmatter.

### Real-time

Replace 1-second polling on the pipeline view with SSE from `coder-core`.
Task stage transitions push events to connected admin sessions.

## Acceptance criteria

- [x] AC1: Admin panel requires Google OAuth login. Unauthenticated
  requests redirect to the login flow.
- [x] AC2: Only emails matching the configured allowlist can log in
  (initially a single email, `ro`'s Google account).
- [x] AC3: Task creation form in the UI: select project, role, repo,
  write prompt. Task appears in the pipeline view immediately.
- [x] AC4: Pipeline view supports override actions (pause, resume, retry,
  reject) via buttons on each task card.
- [x] AC5: "Approve merge" action on reviewed tasks triggers a merge of
  the associated PR.
- [x] AC6: Pipeline view updates in real-time via SSE (no polling).
  Stage transitions appear within 2 seconds.
- [x] AC7: Knowledge browser supports editing a spec's acceptance-criteria
  checkboxes and saving the change back to the knowledge repo.

## Open questions

- Should the "approve merge" action also trigger the CD pipeline, or is
  that just a side effect of the merge landing on `main`? Leaning
  toward the latter — merge triggers CD naturally.
- SSE vs. WebSocket: SSE is simpler and sufficient for one-way push.
  WebSocket only if we need bidirectional (e.g., chat with workers).
- How does knowledge editing work against a Git-backed repo? Options:
  commit directly to `main`, or open a PR. Leaning toward direct commit
  for checkbox-level edits, PR for larger changes.

## Links

- Specs: [`0003`](../active/0003-admin-panel-read-only.md), [`0010`](./0010-task-orchestration-v1.md)

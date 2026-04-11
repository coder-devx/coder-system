---
id: "0014"
title: Knowledge write API
type: spec
status: wip
owner: ro
created: 2026-04-11
updated: 2026-04-11
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0002", "0016", "0017"]
---

# Knowledge write API

**Phase:** Next — autonomous planning
**Progress:** 0 / 6 acceptance criteria

## Problem

Workers can read knowledge artifacts via the knowledge API (spec 0002)
but cannot write them. Creating a spec, updating an ADR, or marking an
AC complete requires a human to edit the Git-backed repo directly. This
blocks autonomous PM and Architect workers from producing their outputs.

## Users / personas

- **PM worker** — needs to draft and update specs.
- **Architect worker** — needs to create design documents and ADRs.
- **Team Manager worker** — needs to update task-plan artifacts.
- **Human operator** — benefits from audit trail on all automated writes.

## Goals

- Workers can create and update knowledge artifacts (specs, designs,
  ADRs) via the API.
- Changes are committed to the Git-backed knowledge repo with frontmatter
  validation.
- Every write is attributed to the worker that made it (audit trail).

## Non-goals

- Conflict resolution or merge-conflict handling (assume single writer
  at a time per artifact).
- Deleting or moving artifacts (append-only and move operations remain
  manual for safety).
- Binary file uploads.

## Scope

New API endpoints wrapping the GitHub Contents API:

- `POST /v1/projects/{id}/knowledge/{type}` — create a new artifact.
- `PUT /v1/projects/{id}/knowledge/{type}/{artifact_id}` — update an
  existing artifact's body and frontmatter.

Both endpoints:

1. Validate frontmatter against the type's `_TEMPLATE.md` schema.
2. Commit directly to `main` with a structured commit message including
   the worker's actor ID.
3. Return the committed SHA and the artifact's canonical ID.
4. Reject writes that would break cross-link integrity.

## Acceptance criteria

- [ ] AC1: `POST /v1/projects/{id}/knowledge/{type}` creates a new
  artifact file in the Git-backed knowledge repo.
- [ ] AC2: `PUT /v1/projects/{id}/knowledge/{type}/{artifact_id}` updates
  an existing artifact without losing frontmatter fields.
- [ ] AC3: Both endpoints validate frontmatter against the type's
  `_TEMPLATE.md` schema and reject invalid writes with a 422.
- [ ] AC4: Writes that would break a cross-link (referencing a
  non-existent ID) are rejected.
- [ ] AC5: Every write commits to `main` with a structured commit
  message attributing the worker actor.
- [ ] AC6: The response includes the committed SHA and the artifact's
  canonical registry ID.

## Open questions

- Should writes go to `main` directly or open a PR for human review?
  Leaning toward direct commit for automated writes, PR for large
  structural changes.
- How does cross-link validation work for new artifacts whose IDs don't
  exist in the registry yet?

## Links

- Related specs: [`0002`](../active/0002-knowledge-repo-read-api.md), [`0016`](./0016-pm-worker-v1.md), [`0017`](./0017-architect-worker-v1.md)

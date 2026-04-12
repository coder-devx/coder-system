---
id: "0022"
title: "Spec and design approval gates"
type: spec
status: active
owner: ro
created: "2026-04-12"
updated: "2026-04-12"
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0012", "0013", "0014", "0016", "0017"]
---

# Spec and design approval gates

**Phase:** active
**Progress:** 7 / 7 acceptance criteria

## Problem

Specs and designs created by the PM and Architect workers land in `wip/` status
but there is no formal approval or rejection workflow. The human has to manually
edit frontmatter, move files between `wip/` and `active/` directories, and
update the registry — all through raw Git operations or the knowledge write API
with manual status changes. There is no reject-with-feedback path that sends the
PM or Architect back to revise their work.

Task plans already have formal approve/reject (spec 0013). Specs and designs
need the same pattern so the autonomous pipeline has structured human
checkpoints.

## Users / personas

- **Operators** reviewing PM-drafted specs — need a one-click approve/reject
  in the admin panel, not manual frontmatter editing.
- **Pipeline chaining** (spec 0021) — needs a programmatic signal that a spec
  or design was approved to trigger the next pipeline step.
- **PM and Architect workers** — need structured rejection feedback to produce
  revisions.

## Goals

- Add `POST /v1/projects/{id}/knowledge/specs/{spec_id}/approve` that promotes
  a wip spec to active (moves file, updates registry, updates frontmatter).
- Add `POST /v1/projects/{id}/knowledge/specs/{spec_id}/reject` that records
  feedback and optionally triggers a PM revision task.
- Same endpoints for designs (`/knowledge/designs/{design_id}/approve|reject`).
- Admin panel shows approve/reject buttons on spec and design detail pages.
- Approval and rejection events are published via SSE for real-time updates.

## Non-goals

- Multi-reviewer approval (one approver is sufficient for v1).
- Approval workflows with quorum or escalation.
- Versioning specs (approve creates a new version) — approval is binary.
- Approving/rejecting active or deprecated artifacts — only wip.

## Scope

**Approve flow:**
1. Validate artifact is in `wip` status.
2. Update frontmatter: `status: wip` → `status: active`.
3. Move file from `wip/` to `active/` via knowledge write API (create at new
   path + delete old path).
4. Update `registry.yaml` entry: `status`, `folder`, `file` fields.
5. Publish SSE event: `knowledge_approved`.
6. Return updated artifact.

**Reject flow:**
1. Validate artifact is in `wip` status.
2. Record feedback in a new `knowledge_reviews` table (or reuse task_messages
   with a new msg_type).
3. Optionally create a revision task (PM for specs, Architect for designs) with
   the rejection feedback as context.
4. Publish SSE event: `knowledge_rejected`.
5. Return rejection receipt.

**Request bodies:**
- Approve: empty body (no fields needed).
- Reject: `{"feedback": "string", "create_revision_task": bool}`.

**Admin panel:**
- Spec detail page: approve/reject buttons (visible only for wip artifacts).
- Design detail page: same.
- Feedback textarea on reject modal.

## Acceptance criteria

- [x] AC1: `POST /v1/projects/{id}/knowledge/specs/{spec_id}/approve` promotes
  a wip spec to active — frontmatter updated, file moved to `active/`,
  registry.yaml updated. Returns the updated artifact.
- [x] AC2: `POST /v1/projects/{id}/knowledge/specs/{spec_id}/reject` records
  feedback. Returns 200 with the rejection receipt.
- [x] AC3: Same approve/reject endpoints work for designs at
  `/knowledge/designs/{design_id}/approve|reject`.
- [x] AC4: Approving a non-wip artifact returns 422 with
  `code=not_approvable`. Rejecting a non-wip artifact returns 422 with
  `code=not_rejectable`.
- [x] AC5: Reject with `create_revision_task: true` creates a PM task (for
  specs) or Architect task (for designs) with the feedback in the prompt.
- [x] AC6: Admin panel shows approve/reject buttons on wip spec and design
  detail pages. Reject shows a feedback textarea.
- [x] AC7: Approval and rejection publish SSE events (`knowledge_approved`,
  `knowledge_rejected`) with the artifact type, id, and actor.

## Open questions

- Should we reuse `task_messages` for rejection feedback or create a new table?
  Proposed: new `knowledge_reviews` table — cleaner separation, different
  lifecycle from task messages.
- Should approval require admin auth or project API key auth? Proposed: both
  (admin for UI, API key for programmatic use).

## Links

- Task plan approval pattern: spec 0013
- Knowledge write API: spec 0014
- Admin auth and mutations: spec 0012
- PM worker (revision mode): spec 0016
- Architect worker: spec 0017
- Pipeline chaining (consumes approval events): spec 0021

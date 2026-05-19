---
id: '0103'
title: Knowledge reads panel on task detail
type: design
status: deprecated
owner: ro
created: '2026-05-18'
updated: '2026-05-19'
last_verified_at: '2026-05-19'
implements_specs:
- '0103'
decided_by: []
related_designs:
- admin-panel
- task-lifecycle
- observability-and-cost-tracking
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-admin
parent: knowledge-and-admin
deprecated_at: '2026-05-19'
deprecated_reason: >-
  Superseded by canonical design 0099 (Worker Knowledge-Read
  Transparency). One of seven near-duplicate design pairs from the
  2026-05-18 calibration burst; consolidated into 0099 on 2026-05-19.
  Distinct ideas (dual-source capture, deep-link, tenant isolation,
  pipeline-row badge) folded into spec 0099 ACs and re-dispatched to
  architect.
---

# Knowledge reads panel on task detail

## What it does today

The task detail page in `coder-admin` already has a `KnowledgeLookupsPanel` — a collapsed accordion backed by `GET /v1/projects/{pid}/tasks/{tid}/knowledge-lookups`. The panel lists each knowledge-repo artifact fetched during the task run in call order (path, cache-hit badge, byte count), lazy-loaded when the operator expands it. The backend table (`knowledge_lookups`), endpoint, and frontend API client (`getTaskKnowledgeLookups`) are live. What is absent: a count chip in the task detail header visible without expanding the panel, and a role-aware "No knowledge reads" warning for completed PM and Architect tasks where zero grounding reads were recorded.

## Architecture

```mermaid
sequenceDiagram
    participant Browser
    participant Core as coder-core
    participant DB as Postgres

    Browser->>Core: GET /v1/projects/{pid}/tasks/{tid}
    Core->>DB: SELECT tasks + COUNT FROM knowledge_lookups
    DB-->>Core: TaskRow + count
    Core-->>Browser: TaskRead {knowledge_reads_count: N}
    Browser->>Browser: render count chip; pm/architect + terminal + N=0 → warning

    opt operator expands panel
        Browser->>Core: GET /v1/projects/{pid}/tasks/{tid}/knowledge-lookups
        Core->>DB: SELECT … ORDER BY looked_up_at ASC
        DB-->>Core: KnowledgeLookupRow[]
        Core-->>Browser: KnowledgeLookup[]
        Browser->>Browser: render path · cache badge · bytes
    end
```

### Parts

- **`knowledge_reads_count: int | None` on `TaskRead`** — populated by a `COUNT(*)` subquery in `get_task_in_project`; omitted from list endpoints to avoid per-row cost.
- **`KnowledgeReadCountChip`** — small `<Chip>` in the task detail header, shown when `knowledge_reads_count !== undefined`; links to the accordion section.
- **`KnowledgeLookupsPanel`** — existing lazy accordion in `TaskDetail.tsx`; rendered under the chip.
- **Zero-read warning** — rendered below the header chip for completed PM/Architect tasks when `knowledge_reads_count === 0`; wired to `role ∈ {pm, architect}` and terminal `stage`.
- **`GET /v1/projects/{pid}/tasks/{tid}`** — existing endpoint extended with the count field; no new route needed.

### Data flow

`GET /v1/projects/{pid}/tasks/{tid}` fetches the task row then runs a single `SELECT COUNT(*) FROM knowledge_lookups WHERE task_id = $tid` and appends the result as `knowledge_reads_count`. The SPA reads this field from the `TaskRead` response and renders the chip before the user opens the accordion. If the operator opens the panel, a separate `GET …/knowledge-lookups` call loads the full list lazily; the panel caches its response until the task detail unmounts.

### Invariants

- `knowledge_reads_count` is `None` when not yet computed (task still running and no lookups recorded) and `0` when the task completes with no reads.
- The zero-read warning fires only when `stage` is terminal (`completed`, `failed`, `skipped`) and `role` is `pm` or `architect`.
- The chip and warning are purely additive: removing them must not break the existing `KnowledgeLookupsPanel` accordion.
- The `COUNT(*)` query runs inline with the task fetch, never on the list route (`GET /v1/projects/{pid}/tasks`).
- Panel content (full lookup rows) is loaded at most once per task detail mount; a re-expand reuses the cached state.

## Interfaces

| Surface | Effect |
|---|---|
| `GET /v1/projects/{pid}/tasks/{tid}` | Returns `knowledge_reads_count: int | None` alongside existing fields |
| `GET /v1/projects/{pid}/tasks/{tid}/knowledge-lookups` | Existing endpoint unchanged |
| `TaskRead` schema | New optional field `knowledge_reads_count` |
| `KnowledgeReadCountChip` | Small chip in task header linking to panel |
| Zero-read warning component | Inline warning block for PM/Architect tasks with no reads |

## Where in code

- `coder_core/tasks/schemas.py` — `TaskRead` (add `knowledge_reads_count` field)
- `coder_core/tasks/router.py` — `get_task_in_project` (add COUNT subquery)
- `coder-admin/src/components/TaskDetail.tsx` — `KnowledgeLookupsPanel`, `KnowledgeReadCountChip` mount point
- `coder-admin/src/api/tasks.ts` — `getTask` response type (add field)
- `coder_core/tests/test_tasks.py` — `test_knowledge_reads_count_*` test cases

## Evolution

Emerged from the observability push; `knowledge_lookups` table and panel were shipped independently in the same sprint as the knowledge-freshness audit loop.

## Links

- Spec: 0103
- Designs: [admin-panel](../knowledge/admin-panel.md), [task-lifecycle](../pipeline/task-lifecycle.md), [observability-and-cost-tracking](../pipeline/observability-and-cost-tracking.md)
- Repos: coder-core, coder-admin

---
id: graph-aware-retrieval
title: Graph-aware knowledge retrieval
type: design
status: active
owner: ro
created: '2026-04-19'
updated: '2026-05-17'
last_verified_at: '2026-05-17'
summary: Graph-walking retrieval over knowledge cross-links.
implements_specs: []
related_designs:
- knowledge-write-api
- knowledge-repo-model
- knowledge-freshness
- architect-worker
- team-manager-worker
- pm-worker
- worker-roles
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-admin
parent: knowledge-and-admin
---

# Graph-aware knowledge retrieval

## What it does today

`GET /v1/projects/{id}/knowledge/graph` performs a single bounded BFS
over artifact cross-links and returns the full subgraph reachable from
a start node in one round-trip. Replaces N+1 serial walks by workers
(architect, team-manager, reviewer, PM). The response is pinned to a
fixed `ref` (commit SHA) so every node in the subgraph is read from
the same snapshot — cache-coherent across the whole walk.

## Architecture

```mermaid
flowchart TB
  caller["Worker / Admin UI"] -->|GET /knowledge/graph?start=…| h["graph_handler"]
  h -->|resolve main → SHA (once)| gh1[(GitHub: get_ref)]
  h -->|BFS with pinned ref| exp["GraphExpander.expand()"]
  exp -->|read_one(node, ref)| cache["TTL cache"]
  cache -.miss.-> gh2[(GitHub: get_contents)]
  exp -->|build envelope + out_edges| exp
  exp -->|cap: depth ≤3, nodes ≤500, fanout ≤50| exp
  exp -->|ordered nodes + truncated_at| h
  h -->|200 OK| caller
```

### Parts

- **`coder_core/api/knowledge_graph.py`** — FastAPI route: param parsing, ref resolution, handler.
- **`coder_core/knowledge/graph.py`** — `expand(start, params, fetch) -> GraphResult`: pure BFS, no I/O, testable via callback.
- **`coder_core/knowledge/reader.py`** (existing) — `read_one(project, type, id, ref)`; called via partial-applied fetch callback under the pinned `ref`.
- **`coder_core/knowledge/graph_client.py`** — worker-side helper `fetch_graph(project, start, depth, edge_types, …)`.
- **`KnowledgeGraphTab.tsx`** — admin Mermaid render (gated `VITE_KNOWLEDGE_GRAPH_ENABLED`).

### Data flow

Caller requests `GET /knowledge/graph?start=spec/0046&depth=2&edge_types=served_by_designs,related_designs,decided_by&min_freshness=70`.
Handler resolves the project's `main` to a SHA once, then invokes
`expand()` with a fetch callback pinned to that SHA. Expander runs
bounded BFS: deque-pop nodes, skip if visited, fetch at pinned SHA,
freshness-filter (stale → `Stub`, skip its edges), count against
`max_nodes`, sort out-edges lexicographically, cap fan-out, enqueue
children up to `depth`. Returns full `nodes[]`, `stub_nodes[]`,
`truncated_at[]`, and metadata in one response.

### Invariants

- **Cache-coherent.** All node fetches use the same SHA (resolved once at entry); no mid-walk drift.
- **Deterministic.** Response is byte-identical across calls (BFS order + lex tiebreaks + content-addressed cache).
- **Bounded fan-out.** Caps enforced server-side regardless of caller: `depth ≤ 3`, `max_nodes ≤ 500`, per-node `fanout ≤ 50`.
- **No partial state.** Full response built before return; mid-expansion failure (GitHub 5xx) returns 502 with detail; caller retries via spec 0027 transient.
- **Read-only.** No repo writes, no cache writes beyond population, no DB writes except metrics.

## Interfaces

| Surface | Effect |
|---|---|
| `GET /v1/projects/{id}/knowledge/graph` | `start` (`type/id`, required), `depth` (≤3, def 2), `max_nodes` (≤500, def 200), `edge_types` (CSV; def `served_by_designs,related_designs,decided_by`), `min_freshness` (0–100, optional). Returns `{ref, start, params, nodes[], stub_nodes[], truncated, truncated_at[], meta}` or 400/403/409/500. |
| `graph_client.fetch_graph(project, start, depth, edge_types, min_freshness=70, max_nodes=200)` | Worker library; composes URL, parses response into `GraphResult` |
| `KnowledgeGraphTab.tsx` | Admin route `/projects/:projectId/knowledge/:type/:id`; Mermaid render |
| Metrics `knowledge_graph_fetch_seconds_bucket{project,depth_bucket}` (histogram), `knowledge_graph_nodes_returned{project}` (gauge) | Observability |

## Where in code

- `src/coder_core/api/knowledge_graph.py` — `graph_handler` (route entry)
- `src/coder_core/knowledge/graph.py` — `expand` + `GraphParams` + `GraphResult` + `NodeRef` + `Stub`
- `src/coder_core/knowledge/reader.py` — `read_one` (fetch callback target; existing)
- `src/coder_core/knowledge/graph_client.py` — `fetch_graph` (worker helper)
- `src/coder_core/api/_metrics.py` — `knowledge_graph_fetch_seconds` histogram

## Evolution

Spec 0046; shipped as a single route. Workers retain a legacy serial-walk fallback behind `settings.knowledge_graph_enabled` during soak; later stages remove the fallback once metrics stabilise.

## Links

- Spec: [0046](../../../product-specs/wip/0046-graph-aware-retrieval.md)
- Designs: [knowledge-write-api](./knowledge-write-api.md), [knowledge-repo-model](./knowledge-repo-model.md), [knowledge-freshness](./knowledge-freshness.md), [architect-worker](../workers/architect-worker.md), [worker-roles](../worker-roles.md)
- Repos: coder-core, coder-admin

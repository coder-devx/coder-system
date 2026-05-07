---
id: graph-aware-retrieval
title: Graph-aware knowledge retrieval
type: design
status: active
owner: ro
created: '2026-04-19'
updated: '2026-05-06'
last_verified_at: '2026-05-06'
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
parent: knowledge-and-admin
---
# 0046 — Graph-aware knowledge retrieval

## Context

Spec 0046 ships a single Knowledge API endpoint that returns the
subgraph reachable from an artifact in one round-trip, replacing
the N+1 walk every authoring/reviewing worker does today. The
endpoint is read-only, no new storage, reuses the existing TTL
cache, freshness envelope, and typed read shape. The win is
latency at the worker pre-claude assembly site (~6 s → ≤ 1.5 s
p50 on `coder` project) and a 5–10× reduction in upstream
GitHub Contents calls per task.

This design is the wiring: the BFS expander, the cache-coherence
guarantee (one resolved `ref` per fetch), the per-worker call-site
conversions, the bounded-traversal mechanics (`max_nodes` +
per-node fan-out cap), and the metric instrumentation.

## Goals

- Reuse the existing Knowledge API caches and parsers — no new
  storage, no precomputed graph.
- Pin `ref` (commit SHA) once at the start of a graph fetch and
  use it for every node in the response. This is the only new
  semantic guarantee that single-fetches don't already give.
- Keep the response shape an obvious composition of the existing
  single-`GET` shape so workers convert by replacing one helper
  call, not by adding new model code.
- Bound a fetch three ways (depth, total nodes, per-node fan-
  out) and truncate gracefully so a pathological subgraph never
  5xx's.

## Architecture

```mermaid
flowchart TB
  caller["Worker / Admin UI"] -->|GET /knowledge/graph?start=...| handler["graph_handler<br/>(coder_core/api/knowledge_graph.py)"]
  handler -->|resolve main → SHA| gh1[(GitHub: get_ref)]
  handler -->|BFS| expander["GraphExpander<br/>(coder_core/knowledge/graph.py)"]
  expander -->|per node:<br/>cache.get(project, ref, path)| cache["TTL cache<br/>(existing)"]
  cache -.cache miss.-> gh2[(GitHub: get_contents)]
  expander -->|parse + freshness| read["existing single-read<br/>build_envelope()"]
  read -->|envelope incl. cross_links_resolved| expander
  expander -->|enqueue out-edges<br/>under depth/nodes/fanout caps| expander
  expander -->|done| handler
  handler -->|response| caller

  classDef new fill:#d1c4e9,stroke:#4527a0,stroke-width:2px
  classDef existing fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px
  class handler,expander new
  class cache,read,gh1,gh2 existing
```

### Parts

- **`coder_core/api/knowledge_graph.py`** (new) — FastAPI route
  + handler. Owns parameter parsing, ref resolution, expander
  invocation, response assembly.
- **`coder_core/knowledge/graph.py`** (shipped) — `expand()`
  function + supporting dataclasses (`GraphParams`, `GraphResult`,
  `NodeRef`, `Stub`, `TruncatedEdge`). Pure logic (no I/O of its
  own), takes a `Fetch` callback so it's easily testable. Implements
  the bounded BFS, ordering, truncation policy, freshness gating,
  fan-out cap. **No changes required to wire the route.**
- **`coder_core/knowledge/reader.py`** (existing) — already
  exposes `read_one(project, type, id, ref) -> Envelope`. The
  expander's fetch callback is a partial-applied call into this
  with the pinned `ref`. No new code path; `ref` was already a
  parameter, just optional.
- **Worker call sites** — one helper per worker:
  `architect.context_assembly()`,
  `team_manager.context_assembly()`,
  `reviewer.spec_context()`,
  `pm.accept_context()`. Each was a serial walk; each becomes a
  single graph call. The prompt-construction code downstream
  is unchanged — it consumes the envelope set the same way.
- **Admin panel** — `KnowledgeGraphTab.tsx` (new) renders the
  Mermaid diagram from the graph response. Behind
  `VITE_KNOWLEDGE_GRAPH_ENABLED`.
- **Metrics** — emit through the existing
  `_metrics` endpoint (`coder_core/api/knowledge_metrics.py`).
  Two new series: a histogram and a gauge.
- **Migration 0054** — `projects.knowledge_graph_enabled
  BOOLEAN NULL` for the per-project tri-state. NULL = inherit
  fleet default.

### Data flow

1. Caller GETs `/v1/projects/{slug}/knowledge/graph?start=spec/architect-worker&depth=2&edge_types=served_by_designs,related_designs,decided_by&min_freshness=70`.
2. Handler validates project + auth + flags
   (`CODER_KNOWLEDGE_GRAPH_ENABLED` ∨ project explicit true). If
   off, returns 503.
3. Handler resolves the project's repo `main` to a commit SHA
   (`GitHubClient.get_ref('heads/main') -> sha`). This SHA is
   the response's `ref` and the pinned read ref for everything
   below.
4. Handler instantiates `GraphParams(depth, max_nodes, edge_types,
   min_freshness)` and a `NodeRef(type, id)` for start, then calls
   `expand(start, params, fetch=partial(service.get_artifact,
   project=slug, ref=sha))`.
5. Expander runs BFS:
   - **Init** — push `(start_type, start_id, depth=0)` onto a
     deque. Maintain `visited: dict[(type, id), Envelope|Stub]`,
     `order: list[(type, id)]`, `truncated_at: list[Edge]`,
     `truncated: bool`.
   - **Loop** — pop next, if already in `visited` skip;
     otherwise call `fetch((type, id))` to get the envelope.
     - If envelope's `freshness.score < min_freshness`: store as
       a `Stub(type, id, freshness, reason='below_min_freshness')`,
       don't enqueue out-edges.
     - Else store the envelope, append to `order`, count it
       against `max_nodes`. If `len(order) > max_nodes`: mark
       `truncated`, log every would-have-followed edge into
       `truncated_at`, halt.
     - Compute the node's outgoing edges from its frontmatter,
       restricted to the requested `edge_types`. Sort by
       `(edge_type, target_id)` lex. If > `fan_out_cap`,
       slice to first N + push the remainder into
       `truncated_at`.
     - For each kept edge, if the target's depth would be ≤
       `depth`, enqueue `(target_type, target_id, current_depth + 1)`.
6. Handler assembles the response from `order` + `visited` +
   `truncated_at` + the `meta` block, returns 200.

### Invariants

- **Cache-coherence.** Every node's content was fetched at the
  same `ref`. The handler's first GitHub call resolves the SHA;
  every subsequent call (cache miss path) goes to that SHA.
  Concurrent writes between the SHA resolve and the second
  fetch land on a different ref and don't affect this fetch's
  responses.
- **Determinism.** Given `(project, ref, params)` the response
  is byte-identical across calls. BFS ordering with lex
  tiebreaks + sorted-edge expansion + the cache being content-
  addressed makes this hold.
- **Bounded fan-out.** No fetch returns more than `max_nodes`
  nodes (default 200, hard cap 500 enforced server-side
  regardless of caller value). Per-node fan-out cap (50,
  no caller override) prevents one runaway artifact from pulling
  the whole repo.
- **No partial state.** The handler builds the whole response
  before returning. A failure mid-expansion (cache miss + GitHub
  5xx on one node) returns 502 with the partial response in the
  detail; the caller decides whether to retry. Workers using
  this should treat 502 as transient and retry once via the
  existing 0027 transient classifier.
- **Read-only.** The endpoint never writes. No side effects on
  the repo, the cache (beyond the standard read-population), or
  any database column other than the metrics counters.

### Bounded-BFS pseudocode

```python
def expand(start: NodeRef, params: GraphParams, fetch: Fetch) -> GraphResult:
    visited: dict[NodeRef, Envelope | Stub] = {}
    order: list[NodeRef] = []
    truncated_at: list[Edge] = []
    truncated = False
    queue: deque[tuple[NodeRef, int]] = deque([(start, 0)])

    while queue:
        node_ref, depth = queue.popleft()
        if node_ref in visited:
            continue
        try:
            envelope = fetch(node_ref)
        except NotFound:
            visited[node_ref] = Stub(node_ref, reason="not_found")
            continue

        if params.min_freshness is not None and envelope.freshness.score < params.min_freshness:
            visited[node_ref] = Stub(node_ref, freshness=envelope.freshness,
                                     reason="below_min_freshness")
            continue

        if len(order) >= params.max_nodes:
            truncated = True
            truncated_at.extend(_edges_of(envelope, params.edge_types))
            break

        visited[node_ref] = envelope
        order.append(node_ref)

        if depth >= params.depth:
            continue

        edges = sorted(_edges_of(envelope, params.edge_types),
                       key=lambda e: (e.edge_type, e.target_id))
        kept, dropped = edges[:FAN_OUT_CAP], edges[FAN_OUT_CAP:]
        truncated_at.extend(dropped)
        for edge in kept:
            queue.append((edge.target, depth + 1))

    return GraphResult(order=order, visited=visited,
                       truncated=truncated, truncated_at=truncated_at)
```

`_edges_of(envelope, types)` reads the cross-link fields out of
the envelope's frontmatter (only for fields in the requested
`types` set). The expander knows nothing about HTTP, GitHub, or
the cache — it's a pure function over the fetch callback.

## Route specification

> Committed 2026-04-28. Covers the route shape only; migration
> `0054`, fleet flag `CODER_KNOWLEDGE_GRAPH_ENABLED`, admin
> endpoint, and worker conversions ship developer-direct in
> follow-up tasks.

### Path and mount order

```
GET /v1/projects/{project_id}/knowledge/graph
```

Mounted on a dedicated `graph_router` in
`coder_core/api/knowledge_graph.py` and included in `main.py`
**before** the main knowledge router. This prevents the literal
path segment `graph` from being absorbed by the
`/{artifact_type}` catch-all on the existing router. Pattern
mirrors the `ship_router` mount introduced for spec 0044.

**Auth.** Project-scoped `X-Api-Key` header via
`require_project_auth`, identical to all other
`/v1/projects/{id}/knowledge/*` routes.

### Query parameters

| Param | Type | Default | Hard cap | Notes |
|---|---|---|---|---|
| `start` | `str` (required) | — | — | `<type>/<id>` form, e.g. `spec/0046`. 400 if absent or malformed. `type` must be a key in `ARTIFACT_TYPES`. |
| `depth` | `int` | `2` | `3` | BFS hops from start. Enforced by `graph.py:_MAX_DEPTH = 3`; `expand()` raises `ValueError` if exceeded. |
| `max_nodes` | `int` | `200` | `500` | Total full nodes in response. Enforced by `graph.py:_MAX_NODES = 500`; `expand()` raises `ValueError` if exceeded. |
| `edge_types` | CSV `str` | `served_by_designs,related_designs,decided_by` | — | Comma-separated list of `CROSS_LINK_FIELDS` keys. Any unrecognised value → 400. |
| `min_freshness` | `int \| None` | unset | — | `0`–`100`; inherits spec 0043 semantics. 409 STALE if start node is below floor. |

**`edge_types` default rationale.** The architect-worker preset
(`served_by_designs,related_designs,decided_by`) is the primary
caller; making it the API default reduces verbosity for that
path. Workers that need a different edge set always pass an
explicit `edge_types` value regardless.

**Constructing GraphExpander from request inputs.** The route
translates directly:

```python
start_ref = NodeRef(type=start_type, id=start_id)
params = GraphParams(
    depth=depth,
    max_nodes=max_nodes,
    edge_types=set(edge_types_csv.split(",")),
    min_freshness=min_freshness,
)
fetch = lambda ref: service.get_artifact(project_repo, ref.type, ref.id, pinned_sha)
result = expand(start_ref, params, fetch)
```

No changes to `graph.py` are required.

### Cache-coherence invariant

At request entry the handler calls
`GitHubClient.get_ref(org, repo, "heads/main")` once to resolve
the current commit SHA. That SHA is:

1. Stored as `response.ref`.
2. Passed as the `ref` argument to every `KnowledgeService.get_artifact`
   call inside the BFS fetch callback.

Every node in one response therefore reflects the same commit.
A write that races between the SHA resolution and a subsequent
node fetch lands on a different ref and does not affect this
response's content.

### Response envelope

```json
{
  "ref": "1a2b3c4d5e6f...",
  "start": {"type": "spec", "id": "0046"},
  "params": {
    "depth": 2,
    "max_nodes": 200,
    "edge_types": ["served_by_designs", "related_designs", "decided_by"],
    "min_freshness": null
  },
  "nodes": [
    {
      "type": "spec",
      "id": "0046",
      "path": "system/product-specs/wip/0046-graph-aware-retrieval.md",
      "frontmatter": {"id": "0046", "title": "...", "...": "..."},
      "body_markdown": "# 0046 — ...\n\n...",
      "freshness": {"score": 92, "last_verified_at": "2026-04-27", "reasons": []},
      "out_edges": [
        {"edge_type": "served_by_designs", "target_type": "designs", "target_id": "0046"}
      ]
    }
  ],
  "stub_nodes": [
    {
      "type": "designs",
      "id": "0029",
      "stub_reason": "below_min_freshness",
      "freshness": {"score": 35, "last_verified_at": "2026-01-10", "reasons": [...]}
    }
  ],
  "truncated": false,
  "truncated_at": [
    {
      "parent_id": "0046",
      "edge_type": "related_designs",
      "target_id": "0034",
      "reason": "max_nodes_cap"
    }
  ],
  "meta": {
    "node_count": 17,
    "depth_reached": 2,
    "fetched_at": "2026-04-28T12:00:00Z"
  }
}
```

**Node shape.** Each entry in `nodes[]` is the `ArtifactResponse`
wire shape (frontmatter, body\_markdown, freshness from spec 0043,
path) plus `out_edges[]`. `out_edges` lists the outgoing
cross-link references within the requested `edge_types` set so
callers can reconstruct graph topology without re-parsing
frontmatter. The start node is always `nodes[0]`.

**Stub shape.** `stub_nodes[]` entries carry `type`, `id`,
`stub_reason` (`"below_min_freshness"` or `"not_found"`), and
`freshness` (null for `not_found` stubs). Stubs have no
`frontmatter`, `body_markdown`, or `out_edges`. Their outgoing
edges are not traversed and not listed in `truncated_at[]`.

### Truncation taxonomy

`truncated_at[]` entries have shape
`{parent_id, edge_type, target_id, reason}`. Only two reasons
are emitted; both map directly from `graph.py`:

| Wire reason | When emitted | `graph.py` mapping |
|---|---|---|
| `max_nodes_cap` | A node is popped when `len(order) >= max_nodes`; all its kept out-edges are logged | `TruncatedEdge.reason="max_nodes"` — route renames to `max_nodes_cap` |
| `fan_out_cap` | A node has > 50 outgoing edges across `edge_types`; the overflow (sorted lex, tail) is logged | `TruncatedEdge.reason="fan_out_cap"` — wire name unchanged |

**Why not `depth_cap` in `truncated_at[]`.** At the depth
frontier `graph.py` stores the node and `continue`s without
emitting any `TruncatedEdge` — depth capping is natural BFS
termination, not an error or a truncation of a _followed_ edge.
Callers know the explored depth from `meta.depth_reached`.

**Why not `stub_below_freshness` in `truncated_at[]`.** Freshness-
gated nodes appear in `stub_nodes[]` with
`stub_reason="below_min_freshness"`. Their outgoing edges are
never enumerated by `graph.py`; emitting them in `truncated_at`
would require the expander to re-fetch or re-parse the stubbed
artifact's frontmatter after marking it stale — a separate
pass, not part of this route-only scope. Callers know a branch
is unexplored via the stub's presence.

**Multi-axis precedence.** An edge attributable to both bounds
is logged once with `reason="fan_out_cap"` (the more specific
bound). `graph.py` enforces this ordering: per-node fan-out
overflow is recorded before the `max_nodes` check fires on the
same node.

### Error codes

| HTTP | `code` field | Condition |
|---|---|---|
| `400` | `invalid_start` | `start` param absent, not in `<type>/<id>` form, or `type` is not a key in `ARTIFACT_TYPES` |
| `400` | `invalid_edge_type` | Any CSV token in `edge_types` is not a key in `CROSS_LINK_FIELDS` |
| `400` | `param_out_of_range` | `depth > 3`, `max_nodes > 500`, or `max_nodes < 1` |
| `403` | `project_mismatch` | URL `project_id` does not match the caller's API-key tenant |
| `409` | `stale` | `min_freshness` is set and the **start node's** `freshness.score < min_freshness`. Body mirrors spec 0043 single-artifact 409: includes `artifact` with full node data so callers can opt in to stale content. Only the start node triggers 409; reachable stale nodes become `stub_nodes[]` entries. |
| `500` | `graph_internal_error` | Unclassified error |

## Interfaces

- **API:** `GET /v1/projects/{id}/knowledge/graph` with the query
  params from spec scope. Response shape per spec AC1 and the
  Route specification section above.
- **Worker library:** new helper
  `coder_core/knowledge/graph_client.py` exposes
  `fetch_graph(project, start, depth, edge_types,
  min_freshness=70, max_nodes=200) -> GraphResult` — workers
  call this; it composes the URL and parses the response into a
  typed dataclass. Same envelope types the workers already
  consume from single reads.
- **Admin SPA:** `KnowledgeGraphTab.tsx` mounts under
  `/projects/:projectId/knowledge/:type/:id` as a tab. Uses
  Mermaid render via the existing Mermaid renderer added in
  0034 (PR viewer's diff-context shared utility).
- **Metrics:** added to the existing `_metrics` endpoint:
  - `knowledge_graph_fetch_seconds_bucket{project,depth_bucket}`
    — histogram of handler wall-clock per request, bucketed by
    `depth` ∈ {0, 1, 2, 3}.
  - `knowledge_graph_nodes_returned{project}` — gauge of
    `node_count` per fetch (rolling p50 / p95 derived
    downstream).
- **Audit:** the graph endpoint is a read; no audit-events row.
  This matches the existing single-`GET` policy. (Worker call
  sites that previously triggered N reads also wrote no audit;
  net audit-volume change is zero.)

## Per-worker conversion details

| Worker | Today | After 0046 |
|---|---|---|
| Architect (`workers/architect.py`) | spec → walk `served_by_designs` → walk each design's `decided_by` ADRs → walk each design's `related_designs` (≈ 30–50 GETs) | one graph fetch from spec, depth=2, `edge_types=[served_by_designs, related_designs, decided_by]`, `min_freshness=70` |
| Team Manager (`workers/team_manager.py`) | design → walk `decided_by` → walk `related_designs` → walk `affects_services` (≈ 10–20 GETs) | one graph fetch from design, depth=2, `edge_types=[decided_by, related_designs, affects_services]`, `min_freshness=70` |
| Reviewer (`workers/reviewer.py`) | spec → walk `served_by_designs` (≈ 5–10 GETs) | one graph fetch from spec, depth=1, `edge_types=[served_by_designs]`, `min_freshness=70` |
| PM accept-mode (`workers/pm.py`) | spec → walk `related_specs` (≈ 3–5 GETs) | one graph fetch from spec, depth=1, `edge_types=[related_specs]`, `min_freshness=70` |

Each worker keeps a fallback to the prior serial walk gated on
the runtime flag check (`settings.knowledge_graph_enabled` or
project explicit), so a sudden flag flip-off doesn't break
authoring tasks. Fallback removal is a follow-up after a 1-week
soak.

## Open questions

- **Stub-node body inclusion.** Spec open-question #3 — whether
  workers tolerating-stale want stub nodes' bodies. Leaning v1:
  no body in stubs; if a worker wants the body it lowers the
  floor or omits `min_freshness`. Reconsider after the worker
  conversions land and we see whether stale-leaf prompts
  actually hurt output quality.

- **Per-worker default `edge_types` constants.** Workers always
  pass explicit `edge_types`. Where do those defaults live?
  Leaning: `coder_core/knowledge/graph_client.py` exposes named
  presets (`ARCHITECT_EDGES`, `TM_EDGES`, etc.) so the worker
  call sites are one-line and the presets are reviewable in one
  file when we want to evolve them.

- **Multi-start.** Spec OQ #5 — single start vs multi-start.
  v1 single. If multi-start becomes common (reviewer task with
  three spec refs is a real case), v2 endpoint accepts
  `start=spec/a&start=spec/b` and merges into one subgraph
  before truncation. Out of scope for v1.

- **Edge-direction.** Cross-link fields point one way
  (`design.decided_by -> [adr]`). Today's reverse navigation
  ("which designs decided by this ADR?") is not a frontmatter
  field — it requires walking the registry. Should the graph
  endpoint support a reverse-edge mode? Leaning: no in v1; the
  reverse view is a separate "back-reference" feature that
  needs a registry index.

- **Truncation under multi-axis pressure.** Spec OQ #4 — same
  parent hitting both `max_nodes` and per-node fan-out cap on
  the same expansion. Resolved: annotate with
  `reason` ∈ {`max_nodes_cap`, `fan_out_cap`}; fan-out cap wins
  when both apply (see Route specification above).

- **What about `glossary.md`?** It's referenced from many
  artifacts implicitly (terms in the body) but isn't a
  cross-link target in frontmatter. v1 ignores; if a worker
  needs the glossary, it fetches it separately. Same as today.

## Rollout

- **Stage 0 — endpoint + expander land, no consumers.** Ship
  the route, the expander, the metrics, the per-project
  tri-state column (migration 0054). Default
  `CODER_KNOWLEDGE_GRAPH_ENABLED=false`. Endpoint returns 503
  for everyone. CI smoke tests the BFS + truncation +
  cache-coherence invariants.

- **Stage 1 — `coder` project opt-in.**
  `projects.knowledge_graph_enabled=true` for `coder` only.
  Endpoint serves real responses for `coder`. Manually fetch
  graphs at depths 0/1/2/3 against the `coder` knowledge repo;
  inspect node counts, latency, truncation behavior. Tune
  `max_nodes` + `fan_out_cap` defaults if needed.

- **Stage 2 — architect worker conversion behind project flag.**
  In `architect.py`, the new graph-fetch path runs only when
  the project's `knowledge_graph_enabled` is true; otherwise
  the legacy serial walk runs. Trial-flip on `coder`. Compare
  pre-claude assembly latency on the same task shape pre/post.
  Watch architect output quality (compare schema-validated
  pass-through rate to the prior 7-day baseline).

- **Stage 3 — TM, Reviewer, PM conversions behind project flag.**
  Same trial-flip pattern; one worker per day so any regression
  is attributable to that worker's switch.

- **Stage 4 — fleet flip.**
  `CODER_KNOWLEDGE_GRAPH_ENABLED=true` fleet-wide. All workers
  now route through the graph endpoint by default for any
  project where the per-project tri-state is NULL or true.
  Per-project disable still possible.

- **Stage 5 — admin panel surface.**
  `VITE_KNOWLEDGE_GRAPH_ENABLED=true` flips the frontend tab on
  in the admin panel. Mermaid graph view available per artifact.

- **Stage 6 — fallback removal.** After 1-week soak with no
  worker regressions, remove the legacy serial-walk fallback
  from each worker's code. The graph endpoint is the only path.

## Backout plan

- **Per-project disable:** `PATCH /v1/projects/{id}` setting
  `knowledge_graph_enabled=false`. Worker call sites detect on
  next task pickup (settings re-read each task) and use the
  legacy serial walk.
- **Fleet kill switch:** flip
  `CODER_KNOWLEDGE_GRAPH_ENABLED=false`. Endpoint returns 503;
  worker call sites' fallback path triggers (if not yet
  removed in Stage 6) — back to serial walk fleet-wide. If
  fallback was already removed (Stage 6 done), the workers'
  graph_client raises and the task fails-transient and retries
  via 0027; ops should treat the kill switch as also requiring
  worker rollback in that case.
- **Endpoint-side bug.** If the expander has a logic bug
  producing wrong subgraphs but no exception (e.g. duplicate
  nodes, mis-ordered output), the symptom is worker output
  quality regression, not a 5xx. Per-project disable is the
  fastest mitigation; longer-term fix is a code patch +
  expanded unit tests for the BFS invariants. Add the bug's
  reproducing seed to the unit test.
- **Cache-coherence concern.** If a graph fetch is observed
  returning content from two refs (the cache-coherence
  invariant violated), the immediate mitigation is to disable
  the endpoint fleet-wide; the bug is in the cache key not
  including `ref` or in the handler not pinning. Both are
  bugs in this design's contract — cannot be papered over
  with config.

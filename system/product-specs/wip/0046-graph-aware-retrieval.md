---
id: '0046'
title: Graph-aware knowledge retrieval
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
served_by_designs: ['0046']
related_specs:
  - knowledge-api
  - knowledge-freshness
  - architect-worker
  - reviewer-worker
  - team-manager-worker
  - pm-worker
---

# 0046 — Graph-aware knowledge retrieval

## Problem

Today every worker reads knowledge as a tree of single-artifact
fetches. The architect worker's "loads the target spec and all
currently-active designs and ADRs before generating" (see
`architect-worker` spec) means: 1 GET for the spec, then N GETs
to walk `served_by_designs`, then M GETs for each design's
`decided_by` ADRs, then K GETs for each design's
`related_designs`. For a project with 16 active designs + 15
ADRs, the architect worker's cold-load fan-out is on the order
of 30–50 sequential round-trips to the Knowledge API just to
assemble its system-prompt context. Each round-trip is a GitHub
TTL-cache miss (or hit) + a parse + a cross-link resolve.

The N+1 pattern shows up in three places it hurts:

1. **Latency** — a Phase 4 architect task spends ~6–12 seconds in
   pre-claude context assembly that should be one second. At fleet
   scale the dispatcher's queue depth is artificially inflated by
   workers that are blocked on serial Knowledge reads, not on
   model spend.
2. **Cost** — every cache miss is a GitHub Contents API call
   subject to the rate limit; when 0028's DispatcherQueue admits
   3–5 concurrent architect tasks they collectively burn through
   the project's GitHub budget faster than necessary, causing
   cascading 429s already observed in the cost-regression-alert
   feed.
3. **Freshness coherence** — when the architect walks ADR by ADR
   serially, each one's `freshness` block is computed against a
   different cache snapshot. A design fetched at T=0 may reference
   an ADR that's been freshness-adjusted by T=5. Workers can't
   ask "give me everything reachable from this spec at min
   freshness 70" — they have to walk and filter, and a single
   stale leaf is enough to make a downstream dispatch decision
   stale-blind.

What we want instead: a single Knowledge API call that says "give
me the subgraph reachable from artifact X, following these edge
types, to this depth, with each node's freshness ≥ N," and
returns the whole pre-joined subgraph as a single response — same
typed shapes as the existing single-artifact reads, but composed.

## Users

- **Architect worker** — primary consumer. Replaces its current
  serial walk during context assembly (the one that loads the
  spec + active designs + ADRs) with a single graph fetch from
  the spec at depth=2, edge types `[served_by_designs,
  related_designs, decided_by]`, freshness floor inherited from
  the project's worker-side default. Latency floor expected to
  drop to one round-trip + parse.
- **Team Manager worker** — secondary consumer. The TM's plan
  authoring needs the design + its dependencies. Single graph
  fetch from the design.
- **Reviewer worker** — when reviewing a developer task that
  references a spec, the reviewer needs the spec's subgraph
  (designs it's served by, ADRs decided by those designs) to
  judge whether the change respects the broader contract.
- **Admin panel** — the existing artifact-detail view today
  shows a flat "related artifacts" list assembled by the
  frontend from registry entries. With graph retrieval it can
  render an actual graph view (mermaid or D3) without the
  frontend doing N HTTP calls.
- **Cold-start ingester (0045)** — when the architect worker is
  in `cold-start` mode generating a per-batch design, having the
  prior batch's `artifacts[]` + their resolved cross-links
  available in one call lets the cross-batch context-passing
  wire (see 0045 design) stay cheap.

## Goals

- Replace the N+1 pattern at its three biggest call sites
  (architect worker pre-claude assembly, TM plan authoring,
  reviewer worker context load) with a single
  `GET /v1/projects/{id}/knowledge/graph` call that returns the
  whole subgraph in one round-trip.
- **Determinism preserved.** The returned subgraph is ordered
  (BFS, ties broken by `(type, id)` lex) and capped (max nodes,
  max depth, max edge fan-out per node) so a fetch is bounded
  and reproducible. Two callers asking for the same subgraph at
  the same repo HEAD get byte-identical responses.
- **Freshness floor respected per-edge.** If `min_freshness=N` is
  passed, every node in the subgraph has `freshness.score ≥ N`,
  AND any edge whose target is below the floor is included as a
  stub (`{id, type, freshness}` with no body) but its outgoing
  edges are not traversed. Workers see "this design exists but is
  stale, so I'm not seeing its sub-tree" and can decide to either
  refuse the gate or proceed with a known-blind branch.
- **Same typed shapes.** Every node in the response is the same
  Pydantic-typed envelope as the single-artifact `GET` returns
  (frontmatter + body + freshness + resolved one-hop cross-links).
  No new model. The graph response is a layer over the
  existing read shape.
- **Cache-coherent.** All artifacts in one graph response are
  pulled at one repo `ref` (commit SHA), so two artifacts in the
  response can never disagree about each other's content.

## Non-goals

- **Write semantics.** Graph retrieval is read-only. Mutations
  still go through `POST /knowledge/{type}` and `PUT
  /knowledge/{type}/{id}`. There is no "graph write" verb.
- **Materialised graph storage.** No precomputed graph table, no
  background indexer. The graph endpoint walks the registry +
  resolves cross-links at request time using the same Knowledge
  API caches that single reads use. If a fetch is slow the fix
  is the cache, not a new index.
- **Cross-project edges.** The graph is bounded to one project's
  knowledge repo. A `related_designs` reference to another
  project's design ID returns `404` like it does today; it does
  not walk into another project. Cross-project pattern surfacing
  is 0048's territory.
- **Edge types beyond the existing cross-link fields.** v1
  traverses only the existing `CROSS_LINK_FIELDS`
  (`served_by_designs`, `implements_specs`, `decided_by`,
  `related_designs`, `related_specs`, `affects_services`,
  `affects_repos`, `depends_on`, `superseded_by`). New edge
  types are out of scope; if we want them, they're a registry
  schema change first.
- **Subscription / streaming.** The endpoint is request/response,
  not SSE. A worker that wants live updates polls or subscribes
  via the existing `pipeline_run.changed` SSE channel for run-
  level events.
- **Content-search inside the subgraph.** This is a graph
  traversal, not a search; it doesn't take a text query. Search
  is a separate spec.

## Scope

### In scope — endpoint contract

`GET /v1/projects/{id}/knowledge/graph`

Query parameters:

- `start` (required) — `<type>/<artifact_id>` (e.g.
  `spec/architect-worker`, `design/0046`). The graph anchor.
- `depth` (default `2`, max `3`) — BFS depth from the start node.
  Depth 0 = just the start node + its one-hop edges _resolved_
  (i.e. the existing single-`GET` shape's
  `cross_links_resolved` block). Depth 1 = + one hop. Depth 2 =
  + two hops. Hard cap at 3 — see "Bounds" below.
- `edge_types` (default _all_) — comma-list restricting which
  cross-link fields are followed. e.g.
  `edge_types=served_by_designs,related_designs` walks only
  those two field names.
- `min_freshness` (default unset; semantics inherit
  `knowledge-freshness` 0043) — applied to every node. Below-
  floor nodes returned as stubs; their outgoing edges are not
  traversed.
- `max_nodes` (default `200`, hard cap `500`) — hard ceiling
  on node count in the response. A traversal that would exceed
  the cap is **truncated** with `truncated: true` and a list of
  `(parent_id, edge_type, target_id)` tuples in the response
  envelope's `truncated_at[]` field, so callers know what's
  missing.

Response shape (typed):

```json
{
  "ref": "1311290abc...",
  "start": {"type": "spec", "id": "architect-worker"},
  "params": {"depth": 2, "edge_types": ["..."], "min_freshness": 70},
  "nodes": [
    {
      "type": "spec",
      "id": "architect-worker",
      "frontmatter": {...},
      "body": "...",
      "freshness": {"score": 92, "reasons": [...]},
      "edges": [
        {"edge_type": "served_by_designs", "target": "design/architect-worker"},
        ...
      ]
    },
    ...
  ],
  "stub_nodes": [
    {"type": "design", "id": "0029",
     "freshness": {"score": 35, "reasons": [...]},
     "stub_reason": "below_min_freshness"}
  ],
  "truncated": false,
  "truncated_at": [],
  "meta": {
    "node_count": 17,
    "edge_count": 34,
    "depth_reached": 2,
    "fetched_at": "2026-04-19T14:00:00Z"
  }
}
```

Each node's `body` is the same markdown body the single-artifact
`GET` returns. `frontmatter` is the same parsed dict. `freshness`
is the same envelope from 0043. The new piece is `edges[]`,
which lists outgoing cross-link references _within the
subgraph_ (so the caller can rebuild the graph topology without
re-parsing frontmatter cross-link fields).

### In scope — bounds + truncation

A graph fetch is bounded three ways and any breach truncates
rather than 5xx-errors:

- **`max_nodes`** — BFS halts when the queue would push the
  count over the cap. Returns `truncated: true` and lists every
  edge that would have been followed but wasn't.
- **`depth`** — caller-specified, hard-capped at 3. Beyond depth
  3 the response stops following; not a truncation, just the
  natural BFS frontier.
- **Per-node fan-out cap** — if a single node has > 50 outgoing
  edges across the requested edge types, only the first 50 (lex
  by `(edge_type, target_id)`) are followed. Remaining edges go
  into `truncated_at[]`. This is a defence against a pathological
  artifact pulling the whole repo into one fetch.

### In scope — caching

- **Same TTL cache as single-artifact reads.** No new cache.
  Each node assembled into the graph response is pulled through
  the existing `(project, ref, path)` keyed cache. A graph fetch
  with all cache hits is one parse-pass per node + one registry
  parse — no GitHub round-trips.
- **`ref` is pinned per-fetch.** The handler resolves `main` to a
  commit SHA at the start of the request and uses that SHA for
  every node fetched in the response. This is the cache-coherence
  invariant. A graph fetch racing with a knowledge write either
  sees pre-write state for every node or post-write — never a
  partial mix.
- **New metric.**
  `knowledge_graph_fetch_seconds_bucket{project,depth_bucket}`
  histogram + `knowledge_graph_nodes_returned{project}` gauge
  on the `/v1/projects/{id}/knowledge/_metrics` endpoint, so we
  can watch p95 and confirm the latency promise.

### In scope — worker integration

- Architect worker's pre-claude assembly switches from the serial
  walk to one graph fetch with `depth=2, min_freshness=70,
  edge_types=served_by_designs,related_designs,decided_by`. The
  in-prompt context block is built from the resulting subgraph.
- Team Manager worker's plan authoring switches from "load the
  approved design + walk its `decided_by`" to one graph fetch
  rooted at the design with `depth=2`.
- Reviewer worker's spec-context load (when the developer task
  references a spec) switches to one graph fetch rooted at the
  spec with `depth=1, edge_types=served_by_designs`.
- PM worker's accept-mode currently re-reads the spec it drafted
  + any `related_specs`; switches to one graph fetch rooted at
  the spec with `depth=1, edge_types=related_specs`.

Each worker's prompt-construction code keeps its prior shape
(injected `# Spec`, `# Active designs`, `# ADRs` sections) but
the data source is the graph response, not N single-fetches.

### In scope — admin panel

- Per-artifact view gains a "Graph" tab that calls the graph
  endpoint with `depth=2, all edge types, no freshness floor`
  and renders a Mermaid diagram of the subgraph. Click a node
  to navigate to it (replacing the current "related artifacts"
  flat list).
- Behind `VITE_KNOWLEDGE_GRAPH_ENABLED`.

### In scope — graph in-process for cold-start

The cold-start aggregator (0045) currently passes "earlier
artifacts' frontmatter + ids" cross-batch. Once 0046 lands, the
aggregator can call the graph endpoint after each batch lands in
the running PR's tree-snapshot to give the next batch a real
`graph_context` object instead of a flat ids list. This is an
0045-side opt-in change, not a 0046 requirement.

### Out of scope

- POSTing a graph (e.g. uploading a fully-resolved subgraph for
  bulk write). Writes stay one-at-a-time.
- Diffing two graph snapshots ("what changed since `ref`?"). Out
  of scope; achievable via two fetches + caller-side diff.
- Per-edge metadata beyond `edge_type` (e.g. weighting, or
  freshness-of-edge). Edge is just a typed reference.

## Acceptance criteria

- **AC1.** `GET /v1/projects/{id}/knowledge/graph?start=<type/id>`
  exists and returns the documented response shape with
  `node_count, edge_count, depth_reached, fetched_at` populated.
  Auth: project-scoped same as other knowledge reads.

- **AC2.** Default-args fetch (`depth=2`, all edge types, no
  freshness floor) on a known seed (`spec/architect-worker` in
  the `coder` project) returns ≥ 15 nodes and ≤ 200 nodes; the
  start node is at index 0; nodes are ordered BFS with
  `(type, id)` lex tiebreak.

- **AC3.** `max_nodes` truncation: a fetch with `max_nodes=10`
  on a subgraph that would otherwise return ≥ 15 nodes returns
  exactly 10 nodes, `truncated: true`, and ≥ 5 entries in
  `truncated_at[]` each with `(parent_id, edge_type, target_id)`.

- **AC4.** Per-node fan-out cap: if any single node has > 50
  outgoing edges in the requested `edge_types`, only the first
  50 (lex by `(edge_type, target_id)`) are followed; the rest
  appear in `truncated_at[]`.

- **AC5.** Freshness gating: a fetch with `min_freshness=70`
  excludes any node with `freshness.score < 70` from `nodes`
  (it appears in `stub_nodes` instead with
  `stub_reason="below_min_freshness"`); below-floor nodes do
  not have their outgoing edges traversed.

- **AC6.** Cache coherence: the handler resolves `start`'s
  branch to a commit SHA at request time and uses that SHA for
  every subsequent fetch in the response; the response's `ref`
  echoes that SHA. A test that opens a write between the start-
  resolve and the second fetch asserts the second fetch returns
  pre-write content.

- **AC7.** Architect worker's pre-claude assembly is converted
  to a single graph fetch (`depth=2, min_freshness=70,
  edge_types=served_by_designs,related_designs,decided_by`).
  Existing `architect` JSON-schema validation continues to pass.
  Pre-claude wall-clock latency drops measurably (target: p50
  ≤ 1.5 s on `coder` project's seed; pre-0046 baseline ≈ 6 s).

- **AC8.** Team Manager and Reviewer workers each switch to a
  graph fetch at their respective context-load site. Same
  schema validations continue to pass.

- **AC9.** Metrics:
  `knowledge_graph_fetch_seconds_bucket{project,depth_bucket}`
  and `knowledge_graph_nodes_returned{project}` exposed on
  `/v1/projects/{id}/knowledge/_metrics`. p95 latency target
  per project ≤ 2 s at depth=2.

- **AC10.** Admin panel's per-artifact view gains a "Graph"
  tab behind `VITE_KNOWLEDGE_GRAPH_ENABLED` rendering a Mermaid
  diagram from the graph endpoint. Click a node to navigate.

- **AC11.** Flag-gated fleet-wide on
  `CODER_KNOWLEDGE_GRAPH_ENABLED` (default off on first deploy).
  When off, the endpoint returns 503 and worker conversions
  fall back to the prior serial walk via a runtime check.
  Per-project escape hatch
  `projects.knowledge_graph_enabled` (NULL = inherit, tri-state).

## Metrics

- **Pre-claude assembly latency by worker** — p50/p95 wall-clock
  from "task picked up" to "claude spawn". Headline KPI; expect
  the architect/TM/reviewer numbers to drop ≥ 4× post-conversion.
- **GitHub Contents calls per task** — count of upstream calls
  per task lifecycle, per role. Expect ≥ 30→ ≤ 5 for architect
  tasks. Confirms the N+1 fix actually reduces upstream load.
- **Graph response p95 latency by depth** — `_metrics` histogram
  carved by `depth_bucket ∈ {0, 1, 2, 3}`. Watch for outliers;
  > 2 s at depth=2 means the cache is missing or the project's
  registry is pathological.
- **Truncated-fetch rate** — count of responses with
  `truncated: true` per week per project. Steady non-zero rate
  → revisit `max_nodes`/`fan_out_cap` defaults; one-off spike →
  one artifact has unusual fan-out.
- **Stub-node rate** — `stub_nodes / (nodes + stub_nodes)` per
  graph fetch when `min_freshness` is set. Trends over time
  show how often callers are seeing freshness-blind branches.

## Open questions

- **Edge-type defaults.** AC2 says "all edge types" by default.
  Some edges are noisy for reasoning use-cases — e.g.
  `affects_repos` from a design pulls the deployment repo in,
  which the architect doesn't need at prompt time. Should
  workers default to a curated set, or always specify
  `edge_types` explicitly? Leaning: workers always pass
  explicit `edge_types`; the unspecified default is for admin /
  exploratory use only. Design to specify per-worker constants.

- **`min_freshness` default for workers.** Today every worker
  reads without a freshness floor (so a stale design still
  reaches the prompt). 0046 is the natural place to flip the
  default to "70 unless overridden." But that's a behaviour
  change beyond the N+1 fix and might surface latent stale
  artifacts as new failures. Leaning: convert workers to use
  `min_freshness=70` _and_ tolerate stub_nodes (treat each
  as a `# Stale: <id>` block in the prompt). Risk: the stale
  branches were silently informing prompts; now they won't.

- **Stub-node body inclusion.** AC5 says stub nodes carry no
  body. But for the worker tolerating-stale path, having the
  body is useful even if stale (clearly labelled). Should
  `min_freshness` separate "exclude entirely" vs "include but
  flag"? Two query params (`exclude_below=N`, `flag_below=M`)
  feels right but adds surface area. Leaning: v1 just
  `min_freshness` with stub-no-body; if workers need bodies of
  stale leaves they pass a lower floor.

- **`depth` semantics for the start node's resolved cross-
  links.** The current single-`GET` shape resolves cross-links
  one hop deep (`cross_links_resolved`). Is graph `depth=0`
  equivalent? Or is depth=0 = "just the start node, no edges
  resolved at all"? Leaning: depth=0 = start node only with
  `edges[]` listed but no targets fetched. depth=1 = + targets.
  Documented clearly because the off-by-one is easy to confuse.

- **Truncation policy under multi-axis pressure.** If a fetch
  hits both `max_nodes` AND a per-node fan-out cap on the same
  node, what's logged? Two entries in `truncated_at[]` for the
  same parent? One? Design needs to specify.

- **Should the graph endpoint accept a list of starts?** A
  reviewer might want the graph rooted at multiple specs in one
  call (e.g. a developer task that touches three specs). v1
  is single-start; multi-start would just call the endpoint N
  times client-side. Acceptable for now.

## Links

- Related specs:
  [knowledge-api](../active/knowledge-api.md),
  [knowledge-freshness](../active/knowledge-freshness.md),
  [architect-worker](../active/architect-worker.md),
  [reviewer-worker](../active/reviewer-worker.md),
  [team-manager-worker](../active/team-manager-worker.md),
  [pm-worker](../active/pm-worker.md)
- Design: [0046](../../designs/wip/0046-graph-aware-retrieval.md)
- Roadmap entry: [ROADMAP.md](../ROADMAP.md) → Phase 8 / 0046

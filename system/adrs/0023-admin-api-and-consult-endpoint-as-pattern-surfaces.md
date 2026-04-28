---
id: "0023"
title: Admin API + dedicated worker consult endpoint as v1 pattern surfaces; MCP resource deferred
type: adr
status: proposed
date: 2026-04-28
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: ['0048', '0049']
---

# ADR 0023 — Admin API + dedicated worker consult endpoint as v1 pattern surfaces; MCP resource deferred

## Context

Design 0048 surfaces cross-project patterns to two audiences:
operators (who want to browse the fleet-wide pattern index) and
workers (who want a pre-decision hint at authoring time). Multiple
surface shapes were considered:

- An **admin REST API** under `/v1/_admin/patterns/*` (admin token).
- A **project-scoped worker consult endpoint**
  `/v1/projects/{id}/patterns/consult` (project token, broker-mediated).
- An **MCP resource** (via 0049's resource registry) that exposes
  pattern groups over the existing MCP protocol.
- **Inline annotation** — the indexer injects `cross_project_hints`
  into artifact API responses when it detects a matching pattern.

The choice of surface(s) determines the audit trail, the isolation
model, and the scope of the 0049 dependency.

## Options considered

1. **Admin API only.** Workers cannot consult; operators browse via
   REST + CLI. Simple, single surface. Pros: minimal scope. Cons:
   excludes the primary worker-facing use case (architects consulting
   before writing an ADR) — one of the spec's two headline users.

2. **Admin API + project-scoped consult endpoint (this ADR).**
   One surface per audience. Audit trail per call in `consultations`
   + `audit_events`. Rate cap on the consult endpoint protects
   against runaway worker loops. The broker attaches a minimal
   `fleet:patterns:consult` scope that is accepted by exactly one
   endpoint. Pros: clean separation of operator and worker surfaces;
   audit trail per call; rate cap; isolation invariant provable at
   the endpoint boundary. Cons: two surfaces to maintain.

3. **Admin API + MCP resource.** Replace the bespoke consult endpoint
   with an MCP resource in the 0049 registry. Pros: reuses the MCP
   transport and session model already being built. Cons: MCP
   resources are read-model subscriptions (SSE or one-shot reads)
   that don't naturally model the "worker posts a topic, gets ranked
   results" interaction; a tool would fit better, but the tool
   registry is purpose-built for human-initiated operations in
   0049's design. The rate-cap + audit logic would need to be added
   to the MCP layer specifically for this surface, duplicating what
   the consult endpoint already provides. Defers value until the MCP
   layer is more mature.

4. **Inline annotation.** The indexer writes `cross_project_hints`
   back into artifact API responses. Workers receive pattern hints
   passively when reading their task spec. Pros: no new endpoint; no
   explicit worker call. Cons: violates the "indexer only reads"
   invariant (the indexer would need write access to the artifact
   cache); couples pattern freshness to the artifact cache TTL; cannot
   be rate-capped independently; the audit trail would need to live
   in the artifact read path, not in a dedicated consultation record.

## Decision

Adopt **option 2 — admin API + project-scoped consult endpoint**.
MCP resource for patterns is **deferred to Stage 2** after the
worker consult surface has validated adoption (consultation rate KPI
≥ 30%). Inline annotation is rejected permanently as incompatible
with the "indexer only reads" invariant.

## Rationale

**Clean separation of audiences.** The admin API is fleet-scoped
and requires an admin token; it is the operator's browsing surface.
The consult endpoint is project-scoped, runs through the broker, and
carries the `fleet:patterns:consult` minimal scope; it is the
worker's authoring-time surface. These are different contracts with
different auth, different rate limits, and different response shapes.
Merging them into one surface or routing through MCP conflates the
two audiences.

**Audit trail per consultation call.** The consult endpoint writes
a `consultations` row + `audit_events` row per call. This is the
primary observable for the consultation rate KPI. An MCP resource
subscription or inline annotation makes this per-call audit harder
to attach: MCP subscriptions are session-lifecycle events, not
per-topic queries; inline annotation fires on artifact reads, not
on worker decision points.

**`fleet:patterns:consult` scope is a minimal, whitelist-enforced
grant.** The broker attaches exactly one extra scope when it
recognises the intent header; that scope is accepted by exactly one
endpoint. The surface exposure is as small as possible. An MCP tool
in the 0049 registry would require either `admin:full` (too broad)
or a new MCP-layer scope check (duplicating the broker logic).

**MCP surface deferred, not rejected.** Once the worker consult
endpoint has proven adoption, the natural MCP exposure is an MCP tool
that calls the consult handler — a thin shim in the 0049 tool
registry following the same pattern as all other MCP tools. Deferring
until adoption is validated avoids duplicating infrastructure before
anyone needs it.

## Consequences

- **Positive.** Two clean, purpose-built surfaces, each with the
  right auth + audit + rate-limit for its audience.
- **Positive.** MCP deferral keeps 0048's scope minimal and 0049's
  registry uncluttered until validation data exists.
- **Positive.** The "indexer only reads" invariant holds; no write
  path from the indexer to the artifact cache.
- **Negative.** Two surfaces to maintain. Mitigated by the fact
  that `coder_core/api/patterns.py` is one file; both endpoint
  families share the same underlying query logic in
  `_brokers/patterns_consult.py`.
- **Follow-up.** Stage 2: if worker adoption validates, add an MCP
  `consult_patterns` tool to the 0049 tool registry as a shim over
  the consult handler. This requires an ADR amendment or a new ADR
  for that addition.

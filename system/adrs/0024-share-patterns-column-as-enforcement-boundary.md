---
id: "0024"
title: "`share_patterns` column as the cross-project read enforcement boundary"
type: adr
status: proposed
date: 2026-04-28
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: ['cross-project-patterns']
---

# ADR 0024 — `share_patterns` column as the cross-project read enforcement boundary

## Context

Design 0048 introduces the first surface in coder-core where one
project's knowledge metadata can reach another project's workers.
This is a deliberate, opt-in relaxation of the `multi-tenancy`
invariant that all prior design work has treated as inviolable
(ADR 0005, tenant-isolation design). The question is: **where does
the enforcement boundary live, and what is the opt-in model?**

Two separate but related questions require a decision:

1. **Opt-in model.** Should projects contribute to the pattern index
   by default, requiring explicit opt-out? Or should they be excluded
   by default, requiring explicit opt-in?
2. **Enforcement location.** Should the `share_patterns` check live
   in the database (row-level security), the application layer
   (handler filter), or the Pydantic response model (schema guard)?

The pre-seal draft (`fleet_patterns_index_opt_in BOOLEAN NOT NULL
DEFAULT true`) used opt-in-by-default. The spec seal resolved this
as a per-tenant setting but left the default open; the post-seal
brief tightened it to opt-out by default (NULL = opt-out).

## Options considered

### Opt-in model

1. **Opt-in-by-default (`DEFAULT true`).** Every project contributes
   unless it explicitly opts out. Maximises cross-project coverage
   from day 1. Cons: a newly onboarded project's knowledge is shared
   before the project's operators have knowingly consented. Violates
   the principle of least surprise for multi-tenant isolation.

2. **Opt-out by default (NULL = opt-out, this ADR).** A project
   contributes only after an operator explicitly sets
   `share_patterns=TRUE`. The fleet starts dark; operators turn on
   sharing project by project. Cons: lower coverage on a small fleet
   (relevant when fleet=2); the operator must take an explicit action
   before any cross-project groups form.

### Enforcement location

A. **Database row-level security (RLS).** The `pattern_groups.members`
   JSONB already contains `project_id`s; RLS cannot easily filter
   JSONB array members. A separate relational members table would be
   needed, and RLS policies would need to be written for each table
   (the admin endpoint and the consult endpoint have different access
   rules). High operational complexity.

B. **Application-layer filter in the handler (this ADR).** The
   consult handler and admin handler each call
   `SELECT share_patterns FROM projects WHERE id = member.project_id`
   and strip non-sharing members before building the response. This
   is the same pattern the rest of coder-core uses for project-scope
   checks.

C. **Pydantic response model only.** Trust the indexer to never
   write non-sharing members; enforce only at the schema layer with
   `Config.extra='forbid'`. Pros: zero query overhead at serve time.
   Cons: if a project opts out *after* being indexed, its members
   remain in the persisted `pattern_groups` rows and would be served
   until the next indexer run. This violates the "serve-time re-check"
   requirement from the spec.

## Decision

**Opt-in model:** adopt **option 2 — opt-out by default** (`share_patterns
BOOLEAN NULL`, NULL = opt-out). A project must explicitly set
`share_patterns=TRUE` to contribute.

**Enforcement location:** adopt **option B — application-layer
filter** in both the consult handler and the admin handler, **plus**
option C's Pydantic guard as a belt-and-suspenders invariant.

The indexer also enforces at write time: it only fetches snapshots
from `share_patterns=TRUE` projects. The serve-time filter in the
handler is the safety net for the case where a project opted out
after the last indexer run.

## Rationale

**Opt-out by default aligns with the multi-tenancy principle.**
ADR 0005 ("Multi-tenant Coder Core, project-aware in every call")
establishes that tenant isolation is enforced in every call, not
just polite. Opt-in-by-default for sharing would mean a new project's
knowledge is exposed to other projects' workers before any operator
has consciously enabled it. That contradicts ADR 0005's spirit. The
cost — operators must take one explicit `PATCH` call to begin sharing
— is low; the benefit is that consent is always explicit.

**Application-layer filter handles the "opt-out after index" case.**
A project may share knowledge in one indexer run, then retract consent
before the next run. Database RLS on JSONB members is not practical;
the application-layer re-check at serve time ensures the retraction
takes effect at the next worker call without waiting for a new indexer
run. This is the same serve-time-check pattern used in the isolation
test harness (tenant-isolation design).

**Pydantic guard is belt-and-suspenders.** Even if the handler has
a bug, `Config.extra='forbid'` prevents the response model from
accidentally serialising a field that wasn't explicitly reviewed.
The schema test enforces this at CI. Neither the application filter
nor the schema guard alone is sufficient; both together form a
defence-in-depth boundary.

**Admin scope does not bypass `share_patterns`.** An admin token
bypasses _authentication_, not the _data policy_. An operator who
wants to read a non-sharing project's knowledge must use the
per-project `/v1/projects/{id}/knowledge/*` endpoints directly —
not the patterns surface. This is consistent with the principle that
sharing is a data-governance decision by the project's operators, not
a capability the fleet operator can override unilaterally.

## Consequences

- **Positive.** Sharing is always explicit consent by the project's
  operators. No project is surprised to find its ADRs appearing in
  another project's worker context.
- **Positive.** Opt-out after an indexer run takes effect at the next
  consult call, not the next index run. The retraction is immediate
  from the worker's perspective.
- **Positive.** The enforcement boundary is readable code in the
  handler, auditable in CI, and tested by the isolation matrix.
- **Negative.** On a 2-project fleet, both projects must explicitly
  set `share_patterns=TRUE` before any cross-project `adr` or
  `spec_problem` groups form. The operator must take 2 explicit PATCH
  calls to activate the surface. Acceptable given the alternative is
  silent sharing.
- **Negative.** Serve-time re-check adds 1–2 project lookup queries
  per consult call (one per unique member `project_id`). These are
  keyed lookups on `projects.id` (primary key) and will be cached
  by the ORM session. Not a material latency impact.
- **Follow-up.** If the fleet grows to 20+ projects and per-project
  explicit opt-in becomes a friction point, a fleet-wide default
  override setting (`CODER_CROSS_PROJECT_PATTERNS_DEFAULT_SHARE=true`)
  can be added. This would require a new ADR since it changes the
  consent model.

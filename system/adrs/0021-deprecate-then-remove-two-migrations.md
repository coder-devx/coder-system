---
id: "0021"
title: Field removal requires two migrations — deprecate then remove
type: adr
status: proposed
date: 2026-04-28
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: ["template-schema-migration"]
---

# ADR 0021 — Field removal requires two migrations — deprecate then remove

## Context

The schema change taxonomy in design 0047 includes "field remove." The question
is whether removing a frontmatter field can be done in a single migration or
must be preceded by a separate deprecation migration.

A single-migration removal means: migration N simultaneously removes the field
from all artifacts and the validator stops recognising it. Projects that
haven't applied migration N yet will have artifacts that carry the field; since
the validator no longer recognises it, any PR on those projects fails CI (the
validator's "unknown field" check).

A two-migration approach means: migration N marks the field as deprecated
(validator tolerates its presence with a warning, but no longer requires it or
validates its value); migration M > N removes the field from artifacts (the
validator then rejects the field as unknown). Between N and M, operators can
observe that the field is present but not relied upon; workers can stop writing
it; migration M cleans up.

Two categories of fields were evaluated separately:

- **Schema-enforced fields** (in the validator's required-fields map, or
  part of cross-link validation): removing these fields has CI consequences
  for pre-migration projects.
- **Optional cosmetic fields** (not in any required-fields map, not part of
  cross-link validation): removing these fields from artifacts is purely
  cosmetic; their absence or presence is invisible to the validator.

## Options considered

**Option A — Single migration for all field removals**

- Simple: one migration, one PR per project.
- Risk (schema-enforced fields): between the migration landing in
  `coder-system` and the project merging the migration PR, any PR on the
  project that touches a file carrying the old field will fail CI if the
  validator has been updated to reject the field. This is the same problem as
  with renames, but alias-tolerance does not apply to removals — there is no
  "new name" to alias to, just absence.
- Workaround: the validator could add a temporary "tolerate but warn" mode for
  the field during the migration window, but this is ad-hoc per removal and
  has no uniform declaration mechanism.

**Option B — Two migrations: deprecate then remove (this ADR)**

- Migration N sets `DEPRECATED_FIELDS = ["tier"]` in the migration file. The
  registration CI extracts this into `validator-aliases.yaml` (reusing the
  same alias infrastructure) as a "deprecated_field" entry: the validator
  tolerates the field's presence but emits a warning and does not validate its
  value.
- Migration M > N (shipped once N reaches 100% fleet adoption) uses
  `remove_frontmatter_key` to remove the field from all artifacts. The
  validator's deprecated-field entry is retired in the same `coder-system` PR
  that ships migration M; after M, the field is unknown and fails validation.
- The gap between N and M gives operators visibility: the admin matrix shows
  when all projects have adopted the deprecation; workers can be updated to
  stop writing the field; migration M is then a clean mechanical removal.

**Option C — Two migrations required only for schema-enforced fields; single
migration allowed for optional cosmetic fields**

- A pragmatic middle ground: if the field is not in the validator's
  required-fields map and not a cross-link participant, a single migration can
  remove it without CI risk.
- Risk: distinguishing "schema-enforced" from "optional cosmetic" requires
  per-field knowledge that is not always obvious from the migration file alone.
  Authors could misclassify a field and ship a single-migration removal that
  breaks CI.

## Decision

Adopt **Option B** for schema-enforced fields (required, validated, or
cross-link-participating). Adopt **Option C** as a documented exception for
fields that are demonstrably optional and not part of cross-link validation.

In practice, the default authoring guidance is: **prefer two migrations for
any field removal**. A single migration is only acceptable when the schema
author can demonstrate via the validator's field registry that the field is
truly cosmetic. The migration file must declare `SINGLE_MIGRATION_REMOVAL =
True` with a comment explaining why; the registration CI emits a warning and
requires a reviewer to explicitly approve the exception.

## Rationale

**Single-step removal of schema-enforced fields breaks mid-migration CI.**
The problem is structurally the same as field renames, but alias-tolerance
handles renames by providing a target name; removals have no target. The
deprecation-then-removal pattern provides the tolerance window that alias
entries provide for renames.

**Two migrations are cheap.** Each migration is a small YAML declaration. The
cost of two migrations instead of one is one additional PR per project (the
deprecation PR). Given that field removals are rare (less frequent than adds),
the overhead is minimal.

**The deprecation step provides observability.** The gap between migration N
(deprecate) and migration M (remove) gives operators a window to update workers
that write the field, update runbooks that reference it, and confirm no system
component relies on it. A single-migration removal provides no such window.

## Consequences

- **Positive.** No project's CI is broken by a field removal landing before
  the migration PR merges.
- **Positive.** The deprecation window surfaces operational dependencies on the
  field that would otherwise go unnoticed.
- **Negative.** Two migrations instead of one for any non-trivial field
  removal. Each migration is small; the overhead is authoring time and one
  additional PR per project.
- **Follow-up.** The `DEPRECATED_FIELDS` declaration reuses the
  `validator-aliases.yaml` infrastructure (a "deprecated_field" entry type
  alongside the "alias" entry type). The validator reads both; the retired
  entry for a deprecated field is set once migration M reaches 100% fleet
  adoption.

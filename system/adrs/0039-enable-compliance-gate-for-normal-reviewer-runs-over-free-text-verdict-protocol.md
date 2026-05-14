---
id: 0039
title: Enable compliance gate for normal reviewer runs over free-text VERDICT protocol
type: adr
status: proposed
date: '2026-05-14'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- 0094
---

# ADR 0039 — Enable compliance gate for normal reviewer runs over free-text VERDICT protocol

## Context

The current reviewer worker emits free-text with a `VERDICT: approve /
request_changes` line; Phase 4 regex-parses it. The compliance gate
(`validate_and_retry` + `resolve_schema_name`) is already wired for
all structured-output roles (PM, Architect, Team Manager) and for
ship-mode reviewer runs (`reviewer_ship.json`). Non-ship reviewer
runs skip the gate entirely (`resolve_schema_name` returns `None`).

Spec 0094 requires `security_findings` and `performance_findings`
arrays in every reviewer output and demands that `approve` cannot
carry `critical` security findings — *"enforced by schema"* (AC3).
Text-based parsing cannot enforce a cross-field constraint at schema
level.

## Options considered

1. **Schema gate (this ADR)** — add `reviewer.json`, extend
   `resolve_schema_name` for non-ship reviewer runs, enforce the
   critical→request_changes constraint via JSON Schema `if/then`.
   Reviewer output format shifts from free-text to structured JSON.

2. **Dispatcher enforcement** — keep the `VERDICT:` free-text protocol,
   append a secondary structured block for findings, and enforce the
   constraint in Python dispatcher logic after regex parsing.

3. **Post-hoc validator** — parse VERDICT and findings heuristically,
   then run a Python validator that rejects `approve`+`critical` and
   re-dispatches the worker.

## Decision

Option 1 — schema gate with `reviewer.json`.

## Rationale

The compliance gate infrastructure exists and is battle-tested across
four other roles. Option 1 reuses it exactly: `resolve_schema_name`
gets one new branch; the gate's re-prompt loop, budget enforcement,
and `raw_output_held` fallback all apply without modification.

Options 2 and 3 require bespoke Python enforcement that duplicates
what JSON Schema `if/then` provides, adding two new code paths with
no shared test harness. The spec's "enforced by schema" language is
also a direct signal that option 1 is the intended shape.

The breaking change (reviewer must emit JSON) is mitigated by the
compliance gate's re-prompt loop: a reviewer that emits the old
free-text format gets one correction turn before failing, which is
the same behavior as any other role that drifts from its schema.

## Consequences

- Non-ship reviewer tasks now fail if the reviewer emits malformed
  JSON after the compliance budget is exhausted. Operators monitor the
  compliance failure rate during the 7-day soak.
- Existing reviewer tests that match the `VERDICT:` regex must be
  updated to supply a JSON envelope fixture.
- Ship-mode reviewer behavior is unchanged (still validates
  `reviewer_ship.json` only; security findings not required).
- The `parse_review_verdict` and `parse_review_url` regex parsers
  become fallback-only paths for shadow mode and legacy task reads.

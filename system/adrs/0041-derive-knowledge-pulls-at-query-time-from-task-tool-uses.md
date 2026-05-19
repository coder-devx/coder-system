---
id: '0041'
title: Derive knowledge pulls at query time from task_tool_uses
type: adr
status: proposed
date: '2026-05-18'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- 0097
---

# ADR 0041 — Derive knowledge pulls at query time from task_tool_uses

## Context

Spec 0097 requires surfacing, per task, the list of knowledge-repo artifact fetches the worker made. Workers make these fetches as `Bash` tool calls (`gh api repos/{org}/{kr}/contents/system/…`). The dispatcher already parses the Claude CLI JSONL transcript into `task_tool_uses` rows via `_persist_transcript_telemetry` (observability / compliance gate work, specs 0025/0027). Three storage strategies were evaluated for the knowledge-pull list.

## Options considered

1. **Query-time derivation from `task_tool_uses`** — filter and regex-extract existing `Bash` rows at `GET /tasks/{id}` request time. Zero migration; uses an already-indexed table; a task has O(100) tool-use rows; pattern match on short `input_args` strings (under 200 bytes for `gh api` commands) is cheap; task detail is a low-frequency read endpoint.
2. **Pre-store in `task_metadata` JSON column** — extract at task completion and pack the array into the existing JSON blob (spec 0088 `task_metadata`). Zero new table, but bloats the tasks row with a variable-length array; `task_metadata` was designed for scalar feature flags and runtime hints, not large collections.
3. **New `task_knowledge_pulls` table** — cleanest schema for cross-task analytics ("which tasks fetched design X?"). Adds migration and ORM model overhead now for a query pattern only needed by a follow-on grounding-score spec that is not yet approved.

## Decision

Option 1: derive knowledge pulls at query time from `task_tool_uses`.

## Rationale

`task_tool_uses` is indexed on `task_id`; the per-request join over O(100) rows with a regex on short strings is negligible on a low-frequency detail page. Option 2 violates the scalar-flag contract of `task_metadata` (spec 0088 documents keys as runtime hints, not arrays); packing a growing array into a JSON blob also makes cross-task queries impractical. Option 3 is premature: the cross-task analytics surface belongs to a future grounding-score spec, and the raw data will be available for backfill at that point from `task_tool_uses`.

The only `task_metadata` addition from this design is the scalar string key `knowledge_pulls_status` (`"ok"` | `"capture_failed"`), which is consistent with spec 0088's scalar-flag intent and is needed to distinguish "zero fetches" from "transcript parse failure".

## Consequences

- No database migration required for spec 0097.
- If a follow-on grounding-score spec requires cross-task knowledge-pull analytics, a `task_knowledge_pulls` table can be introduced and backfilled from `task_tool_uses` at that time.
- The `knowledge_pulls_status` scalar is the only `task_metadata` addition; it carries no payload, keeping the tasks row cheap.

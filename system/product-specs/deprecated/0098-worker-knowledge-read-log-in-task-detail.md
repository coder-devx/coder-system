---
id: 0098
title: Worker Knowledge Read Log in Task Detail
type: spec
status: deprecated
owner: ro
created: '2026-05-18'
updated: '2026-05-19'
last_verified_at: '2026-05-19'
deprecated_at: '2026-05-19'
reason: >-
  Superseded by canonical spec 0099 (Worker Knowledge-Read
  Transparency). This was one of seven near-duplicate specs the
  founder/PM calibration loop emitted on 2026-05-18 for the same idea
  (surface worker knowledge-repo fetches on the task detail page).
  Consolidated 2026-05-19; distinct contributions folded into 0099.
served_by_designs:
- admin-panel
related_specs:
- admin-panel
- knowledge-api
- observability
parent: knowledge-and-admin
---

# Worker Knowledge Read Log in Task Detail

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

Operators auditing grounding quality must download the raw session transcript from GCS to answer what the worker actually pulled from the knowledge repo before producing its output. The data is already captured: `knowledge_lookups` records every read through the KnowledgeService, and `task_tool_uses` records every direct `gh api .../contents/` Bash call the worker made — but neither table's data appears in the admin panel. An operator checking whether a PM draft task fetched the relevant sibling specs must unzip a JSONL file and scan hundreds of tool-call entries.

## Users / personas

- **Operators** using the task detail page to audit why a task produced low-quality output or a stale spec draft.
- **The consultant evaluate loop**, which currently infers grounding coverage by parsing the full transcript — a slow path that existing queryable endpoints could replace.

## Goals

- Operators can see every knowledge artifact the worker fetched during a run, inline on the task detail page, without downloading the transcript.
- Auditing grounding becomes a 10-second admin panel check rather than a multi-minute transcript dig.

## Non-goals

- Automatic grounding-quality scoring or flagging — this spec surfaces the raw signal only.
- Surfacing non-knowledge tool uses (Bash commands, Edit/Read/Grep calls on the source workspace).
- Retroactive backfill for tasks that completed before `knowledge_lookups` shipped.

## Scope

- New Knowledge reads section on the existing task detail page (`/projects/:id/pipeline/:taskId`) in `coder-admin`.
- Consumes two existing `coder-core` endpoints: `GET /{task_id}/knowledge-lookups` and `GET /{task_id}/tool-uses` (filtered to `gh api` Bash calls against `/contents/` paths).
- Display: artifact path, fetched-at timestamp, source (KnowledgeService vs direct Bash), listed chronologically.
- No new backend work required; pure admin-panel addition consuming already-recorded data.

## Acceptance criteria

- **AC1.** The task detail page for any completed task shows a Knowledge reads section listing every artifact path the worker fetched, with a fetched-at timestamp for each entry.
- **AC2.** The section distinguishes reads through the KnowledgeService from direct `gh api` Bash calls, labelled accordingly.
- **AC3.** When a task has zero knowledge reads, the section renders an empty-state message rather than being hidden or absent.
- **AC4.** The Knowledge reads section is visible on the task detail page for PM draft and Architect design tasks in the staging environment.
- **AC5.** Each artifact path is a link that opens the file in the project knowledge repo on GitHub in a new tab.

## Metrics

No new metrics instrumented; reduction in transcript-download support requests is the informal adoption signal.

## Open questions

- Should KnowledgeService cache-hit reads (no actual `gh api` call issued) be shown or hidden? Assumption: show cache-miss fetches only.
- For legacy tasks predating `knowledge_lookups`, show a reads-not-available notice rather than an empty list.

## Links

- Spec: [knowledge-api](../knowledge/knowledge-api.md)
- Spec: [admin-panel](../knowledge/admin-panel.md)
- Spec: [observability](../pipeline/observability.md)
- Design: [admin-panel](../../designs/active/knowledge/admin-panel.md)
- Design: [knowledge-stack](../../designs/active/knowledge/knowledge-stack.md)

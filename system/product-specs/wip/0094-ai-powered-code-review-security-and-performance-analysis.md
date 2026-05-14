---
id: 0094
title: 'AI-Powered Code Review: Security and Performance Analysis'
type: spec
status: wip
owner: ro
created: '2026-05-14'
updated: '2026-05-14'
last_verified_at: '2026-05-14'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- reviewer-worker
- developer-worker
- observability
parent: worker-roles
---

# AI-Powered Code Review: Security and Performance Analysis

**Phase:** wip
**Progress:** 0 / 6 acceptance criteria

## Problem

Every PR opened by the Developer worker passes through the Reviewer for convention and AC compliance — but security vulnerabilities and performance regressions are only caught if they happen to be documented in the project's conventions or ADRs. A SQL injection vector or an unbounded query can pass reviewer approval because the reviewer's scope is constrained to diff + ACs + conventions, with no structured security or performance analysis pass (spec 0065 scope cut). Operators discover these issues post-merge, during production incidents or manual audits.

## Users / personas

- **Operators** of the admin panel: want confidence that every PR has been scanned for security and performance before merge, without having to encode every OWASP category into project convention docs.
- **Developer workers** in the pipeline: receive targeted, actionable fix feedback before the PM acceptance gate rather than vague lint-level notes.

## Goals

- Add a structured security analysis pass (OWASP Top 10 aligned, credential exposure) and a structured performance analysis pass (N+1 queries, unbounded pagination, algorithmic complexity) to every reviewer-worker run.
- Surface findings as tagged inline GitHub PR comments (`[security]` / `[performance]`) distinct from convention comments.
- Escalate `critical`-severity security findings to `request-changes` regardless of AC/convention compliance.
- Persist finding counts on the task row so the admin panel task detail page can display them.

## Non-goals

- Integration with third-party SAST/DAST tools (Snyk, Semgrep, SonarQube).
- Runtime or load-performance testing.
- Escalating `high` (non-critical) security findings or any performance findings to `request-changes` (may revisit post-soak).
- Modifying the PM acceptance criteria or ship-attestation schema.

## Scope

- Reviewer role prompt (`system/roles/reviewer/tasks/review.md`) gains two required analysis sections: Security Analysis (OWASP Top 10 categories, credential exposure patterns) and Performance Analysis (N+1 queries, missing index hints, unbounded pagination, algorithmic complexity).
- Reviewer structured output schema (`reviewer.json`) gains `security_findings` and `performance_findings` arrays with severity-tagged finding objects.
- Orchestrator writes finding counts to task metadata; admin panel task detail reads them.
- Admin panel task detail: a "Security" count chip and a "Performance" count chip alongside the existing verdict chip for reviewer tasks.

## Acceptance criteria

- **AC1.** Every reviewer-worker task output includes `security_findings` and `performance_findings` arrays (possibly empty). A PR with no issues produces both as `[]`; the admin panel task detail shows counts of 0 for each.
- **AC2.** A synthetic test diff containing a SQL injection pattern causes the reviewer to emit at least one `security_findings` entry with `severity: "critical"` and the GitHub PR review includes a `[security][critical]` inline comment on the offending line.
- **AC3.** A reviewer task emitting any `critical`-severity security finding submits `request-changes` on the GitHub PR even when all ACs and conventions pass; the `approve` path requires `security_findings` to contain no `critical` entries (enforced by schema).
- **AC4.** A synthetic test diff containing an N+1 query pattern causes the reviewer to emit at least one `performance_findings` entry and a `[performance]` inline comment on the PR; performance findings alone do not change an `approve` verdict to `request-changes`.
- **AC5.** The admin panel task detail page shows "Security" and "Performance" count chips for all reviewer tasks, reading from the new task metadata fields, verifiable in the test environment.
- **AC6.** The reviewer role prompt at `system/roles/reviewer/tasks/review.md` in the knowledge repo contains an explicit "Security analysis" section (listing OWASP-aligned check categories) and a "Performance analysis" section (listing query, pagination, and complexity patterns), verifiable by reading the file.

## Metrics

- Fraction of fleet reviewer tasks emitting non-empty `security_findings` (baseline vs. 30 days post-ship).
- `request-changes` rate attributable to `critical` security findings as a new subcategory on the observability dashboard.

## Open questions

- Should `high`-severity security findings also force `request-changes`? Recommend `critical`-only for the initial ship and re-evaluate during soak.
- Performance analysis scope: Python/SQL only (coder-core stack) or language-agnostic? Recommend Python/SQL first.

## Links

- Related specs: [reviewer-worker](../active/reviewer-worker.md), [developer-worker](../active/developer-worker.md), [observability](../active/observability.md)
- Designs: TBD — Architect to produce a wip design for the schema extension and prompt changes.

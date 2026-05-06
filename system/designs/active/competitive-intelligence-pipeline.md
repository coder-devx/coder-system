---
id: competitive-intelligence-pipeline
title: Competitive Intelligence Pipeline
type: design
status: active
owner: ro
created: '2026-04-08'
updated: '2026-05-06'
deprecated_at: '2026-04-23'
deprecated_reason: 'Salvaged from the deleted coder-agent repo on 2026-04-08 as a

  placeholder for a future PM-worker capability, but no spec was

  ever authored and no roadmap phase scheduled the rebuild. Sitting

  in wip/ implied in-flight work when it wasn''t. Deprecating

  preserves the historical design for future rehydration while

  clearing the active surface. Rehydrate by re-authoring a fresh

  spec with a current WIP number when the roadmap actually plans

  the capability.

  '
last_verified_at: '2026-05-06'
verified_by: knowledge-audit
implements_specs: []
decided_by: []
related_designs:
- system-overview
- worker-roles
affects_services:
- coder-core
affects_repos:
- coder-core
parent: null
---
# Competitive Intelligence Pipeline

> Salvaged from the deleted `coder-agent` repo (`app/analyzer/`,
> `app/spec_writer/`, `app/enricher/`) which implemented a working end-to-end
> version of this pipeline for VibeTrade. The code is gone; the design lives
> here so the clean rebuild can reconstruct it without re-deriving the
> decisions.

## Context

Every managed project has competitors. Keeping up with them is Product
Manager work: who ships what, at what price, with which integrations, and
what threats or opportunities does that create for us.

Doing this by hand doesn't scale across many projects or many competitors.
The old `coder-agent` repo had a working three-phase pipeline that
produced structured competitor intelligence into Notion. We're rebuilding
it as a first-class capability of the Product Manager role in
`coder-core`.

## Goals

- **PM capability**, per managed project: "given a list of competitors,
  produce and maintain a structured intelligence page for each one in the
  project's knowledge base".
- **Three-phase pipeline**: crawl → spec → enrich, each independently runnable.
- **Project-parameterized** — no VibeTrade-specific strings in the core
  logic. All prompts, priority keywords, and target schemas come from the
  project's config.
- **Stateful logins**: handle competitors hidden behind auth, including
  2FA/CAPTCHA, without storing long-lived session tokens.
- **Hybrid runtime**: crawl is heavy (Playwright + Chrome); spec + enrich
  are light and can run on Cloud Run.

## Non-goals

- Not a general web scraper. The priority scoring, page selection, and
  synthesis prompts are tuned for *product* intelligence, not arbitrary crawling.
- Not a continuous watcher. This is batch-triggered (manually or on a
  schedule), not live.

## Pipeline shape

```mermaid
flowchart LR
  pm[PM Worker] --> orch[Pipeline orchestrator]
  orch --> crawl[Phase 1: Crawl<br/>Playwright + persistent profile]
  crawl --> bundle[(bundle: pages, screenshots,<br/>summary.md, manifest.json)]
  bundle --> spec[Phase 2: Spec Writer<br/>Claude strict-JSON prompt]
  spec --> specjson[(spec.json)]
  specjson --> enrich[Phase 3: Enricher<br/>GitHub API · DDG · httpx · Claude]
  enrich --> notion[(Per-project Notion DB<br/>sub-page tree per competitor)]
  sm[(GCP Secret Manager<br/>competitor-{project}-{slug})] -.-> crawl
```

## Phase 1 — Crawl (local-only)

**Why local:** Playwright + persistent Chrome profile lets the user solve
CAPTCHAs and 2FA in a visible window the first time; cookies survive for
subsequent runs. This is incompatible with headless Cloud Run execution.

Key design points from the working implementation:

- **Persistent Chrome profile** at `~/.coder-agent/chrome-profile` (configurable). Survives across runs. Cookies and auth state stick.
- **Seed set**: both the marketing site (`start_url`) and the app (`login_url`) are seeded. Same-site matching is by registered apex domain so `app.X.com` and `docs.X.com` are both followed.
- **Must-try paths** (`/pricing`, `/plans`, `/features`, `/product`, `/platform`, `/how-it-works`, `/about`) are seeded for every target even if not linked from the home page — many sites hide these behind JS-rendered nav.
- **Priority-scored URL queue** — three tiers of keyword matches. Tier 1 (pricing/plans/features/product/platform) gets a 20× bonus. Depth penalty per extra path segment past 3. Hard penalty for `/api-reference/` and `/sdk-reference/` trees that eat budgets.
- **Skip patterns** — legal/privacy/terms, social links, auth flows, binary assets. Keeps the budget on product pages.
- **Interactive login fallback** — if credentials aren't provided but a `login_url` is, open the browser visibly and wait for the user to log in by hand. Resume auto-detects by either (a) the user touching a sentinel file, (b) navigation back to an allowed apex with no auth keywords in the URL, or (c) 10-minute timeout. Always gives at least 30s before auto-resuming so the user has time to start.
- **Per-page capture** — title, H1/H2/H3 headings, visible body text (capped at 8k chars), internal + outbound links (top 200), full-page screenshot.
- **Output bundle** — one directory per (project, competitor): `pages/*.json`, `screenshots/*.png`, `manifest.json`, and an aggregated `summary.md` for Phase 2 to consume.

**Credentials** for logins are stored in GCP Secret Manager under the
naming convention already aligned with [ADR 0009](../../adrs/0009-per-managed-project-cloud-account-and-github-org.md):
`coder/{managed_project_id}/competitor-credentials/{competitor_slug}`,
each payload a JSON object `{username, password, notes, url}`. Only the
secret *path* is stored in the project's Notion DB; values never leave
Secret Manager.

## Phase 2 — Spec Writer (Cloud Run-safe)

Reads the bundle's `summary.md` and calls Claude with a **strict-JSON
system prompt** that outputs a fixed schema:

```json
{
  "overview": "...",
  "features": "markdown",
  "pricing": "markdown",
  "api": "markdown",
  "strengths": "markdown",
  "weaknesses": "markdown",
  "threats": "markdown",        // project-specific
  "opportunities": "markdown",  // project-specific
  "key_facts": { "founded": "...", "headquarters": "...", "target_users": "...", ... }
}
```

Critical prompt tricks learned the hard way:

- **"Output ONLY the JSON object — no preamble, no code fences, no commentary."** Then strip code fences defensively on parse anyway, because Claude sometimes sneaks them in.
- **Explicit extraction requirements** in the prompt. Tell Claude to SCAN THE ENTIRE SOURCE for tier names and dollar amounts, not stop after the first two. Name the failure mode ("do NOT stop after the first two tiers") and give examples ("if you see TIER_A $60, TIER_B $120, TIER_C $336, ALL THREE must appear"). Same pattern for features, integrations, SDKs.
- **"Not documented" is the last resort.** Make the model actually look before giving up on a field.
- **Cap input at ~60k chars** going into Claude (≈ 15k tokens). The full model supports 200k but this keeps it fast and cheap.

Writes the structured spec into the project's Notion database as a
**sub-page tree** under the competitor row, one page per top-level field
(Overview, Features, Pricing, API, Strengths, Weaknesses, Threats,
Opportunities). Marks the competitor row status as "Spec Ready" and
stamps "Last Analyzed".

## Phase 3 — Enricher (Cloud Run-safe)

Runs **after** the spec writer. Detects gaps (fields under a minimum
length or containing "unknown"/"not documented"), gathers targeted
research, and synthesizes patches.

Sources:

1. **GitHub REST API** — for competitor repos found in the crawl bundle
   (scan links and body text for `github.com/org/repo` references, plus
   a domain-guess fallback). Fetches stars, forks, contributors, issues,
   license, pushed/created dates, primary language, description.
   Contributor count comes from the Link header of
   `/contributors?per_page=1` (last-page trick). Closed-issue count from
   the search API.
2. **DuckDuckGo HTML search** — no API key needed. Posts to
   `html.duckduckgo.com/html/` with a realistic User-Agent, regex out
   `class="result__snippet"` blocks. Used for founding year, HQ, funding
   rounds, valuation.
3. **Targeted httpx fetch** — plain GET + strip-tags for `/pricing`,
   `/integrations`, `/api`, `/developers`, `/docs` pages the crawler
   might have missed.

Claude synthesizes all findings into a **patch JSON** with a strict
"omit keys where you found nothing" rule, and the enricher merges
patches back into `spec.json` in place. An enrichment sub-page is
added to the competitor's Notion tree with a "Gap Resolution Summary"
at the bottom showing which gaps were closed and which remain open.

## Integration points in coder-core

This pipeline becomes a module inside `coder-core` (initially — may
split later):

```
src/coder_core/
  workers/
    pm.py                       existing PM worker
    pm_competitive_intel/       new module
      orchestrator.py           triggers crawl → spec → enrich
      crawler/                  Phase 1 (Playwright, local-only)
      spec_writer/              Phase 2 (Claude strict-JSON)
      enricher/                 Phase 3 (GitHub + DDG + httpx + Claude)
      notion_writer.py          sub-page tree creation
```

The orchestrator is PM-role-scoped and reads project config for:

- Notion database ID for competitors (per project).
- Project-specific prompt context (who the project is, what it competes on).
- Priority-tier keywords (project can extend the defaults).
- Secret Manager prefix (follows ADR 0009 convention).

## Open questions

- **Where does the crawl run** once Coder is multi-tenant? Options:
  1. Strictly on the user's local machine via impersonation — the user's laptop runs the PM worker that runs Playwright.
  2. A dedicated "heavy worker" Cloud Run service with a headful Chrome via xvfb — less interactive but centralizable.
  3. A hybrid: default to Cloud Run headful, fall back to local on CAPTCHA.
  My preference is option 1 initially — respects the stateful-login reality and keeps Coder's fleet lightweight.
- **Scheduling** — cron-triggered per project, or PM-worker-decided? Probably both.
- **Deduplication** — when the same pipeline re-runs next month, do we diff against the prior spec and only surface *changes*? Likely yes; add a diff summary page.
- **Schema generalization** — the "threats" and "opportunities" fields are VibeTrade-flavored. For a project where the competitor concept is "open-source libraries we depend on", the fields would differ. Make the schema a per-project config.

## Promotion criteria → active

- Orchestrator exists in `coder-core` and is reachable via the PM worker.
- Phase 2 + Phase 3 run on Cloud Run for at least one project that isn't VibeTrade.
- Phase 1 runs via impersonated local PM worker (Claude Code on the user's laptop).
- Secrets follow the ADR 0009 naming.
- One competitor intelligence page has been generated end-to-end on the new system.

## Links

- Designs: [`0001`](../active/0001-system-overview.md), [`0002`](../active/0002-worker-roles-and-impersonation.md), [`0004`](./0001-generalize-coder-from-vibetrade.md)
- Roles: [`product-manager`](../../roles/product-manager.md)
- ADRs: [`0006`](../../adrs/0006-per-role-service-accounts.md), [`0009`](../../adrs/0009-per-managed-project-cloud-account-and-github-org.md)
- Integrations: [`notion`](../../integrations/notion.md), [`github`](../../integrations/github.md), [`gcp`](../../integrations/gcp.md), [`anthropic`](../../integrations/anthropic.md)

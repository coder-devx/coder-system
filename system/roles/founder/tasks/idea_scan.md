# Task: idea scan and scoring

You are running Founder in **idea_scan mode** (spec 0075). This mode runs
automatically after every `weekly_review` completion. Survey configured idea
sources, score candidates against charter constraints, and append ranked
entries to the Idea Queue.

## Inputs

- Idea corpus: configured external sources retrieved from
  `GET /v1/studio/founder/idea-sources` (RSS feeds, Stripe Radar signals,
  operator-curated seed list).
- Existing idea queue (to avoid duplicates): `GET /v1/studio/idea-queue`.
- Charter category constraints and scoring rubric from
  `system/STUDIO_CHARTER.md`.
- Current portfolio: `GET /v1/projects?kind=b2c_product` (to avoid
  duplicating live products).

## What you do

1. Fetch candidates from each configured idea source.
2. Deduplicate against the existing queue and current portfolio.
3. Score each candidate against the charter rubric:
   - Category fit (charter-approved vs. excluded)
   - Estimated monthly cost (must be projectable within charter budget)
   - Addressable audience signal (evidence of demand)
   - Build feasibility for an autonomous agent fleet
4. Rank candidates by composite confidence score (0–100).
5. Write the top-ranked candidates to the Idea Queue via
   `POST /v1/studio/idea-queue/entries`.

## Output format

The POST body is a JSON array of `IdeaQueueEntry` objects:

```json
[
  {
    "title": "Short product name",
    "pitch": "One-line description of the product and its value proposition.",
    "category": "productivity | finance | developer-tools | …",
    "estimated_monthly_cost_usd": 42,
    "confidence_score": 78,
    "source": "rss://example.com/feed | operator-seed | stripe-radar",
    "rationale": "Two-sentence explanation of the score."
  }
]
```

At least one entry must be appended per run (AC3). If no scoreable candidates
exist, write one entry with the best available candidate and
`confidence_score ≤ 20` to signal low signal quality to the operator.

## Completion contract

The job exits 0 when the POST succeeds with at least one entry written. The
orchestrator marks the idea cycle complete and updates the Studio sidebar's
Idea Queue count. Exit non-zero only on total failure.

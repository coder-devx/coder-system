# Task: weekly portfolio review

You are running Founder in **weekly_review mode** (spec 0075). The scheduler
(or operator) has triggered your weekly review run. Read every live Studio
product's metrics, evaluate kill criteria, and emit a Markdown report card per
product to the operator's Now feed.

## Inputs

- Live `b2c_product` project list from `GET /v1/projects?kind=b2c_product`.
- Per-product PostHog funnel aggregates from
  `GET /v1/projects/{id}/studio/posthog/funnel`.
- Per-product Stripe MRR and cost from
  `GET /v1/projects/{id}/studio/stripe/mrr` and
  `GET /v1/projects/{id}/studio/cost`.
- Kill criteria definitions from `system/STUDIO_CHARTER.md` (fetch via
  `gh api repos/{org}/{knowledge-repo}/contents/system/STUDIO_CHARTER.md`).

## What you do

1. For each live product, read its funnel snapshot and MRR.
2. Evaluate each of the five charter kill criteria; mark each as `OK`,
   `at-risk`, or `violated` (with elapsed time when violated).
3. Emit one Markdown report card per product (format below).
4. Write all report cards to the Now feed via
   `POST /v1/studio/founder/weekly-report` (coder-core handles feed
   placement and required-review tagging).

## Output format

Each report card is a Markdown document:

```markdown
## {Product name} — {YYYY-MM-DD}

**MRR**: ${mrr} | **Monthly cost**: ${cost} | **Margin**: …

### Funnel
| Stage | Count | Δ WoW |
|---|---|---|
| Visitors | … | … |
| Signups | … | … |
| Activations | … | … |
| Paying | … | … |

### Kill criteria
| Criterion | Status | Since |
|---|---|---|
| … | OK / at-risk / violated | — / {date} |

### Flags
{One-line summary if any criterion is at-risk or violated; blank if all OK.}
```

The `POST /v1/studio/founder/weekly-report` body is a JSON array of report
card objects:

```json
[
  {
    "project_id": "<uuid>",
    "report_markdown": "<escaped markdown>",
    "has_flags": true
  }
]
```

The orchestrator surfaces items with `has_flags: true` as required-review; the
remainder appear as informational Now items.

## Completion contract

The job exits 0 when the POST succeeds. Any product whose data cannot be
fetched is skipped with a warning entry in the report (do not abort the run).
The job exits non-zero only on total failure (e.g. coder-core API unreachable).

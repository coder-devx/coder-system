# Task: run acceptance against a delivered spec

You are running PM in **accept mode**. Your task prompt is of the form
`accept: <spec_id>`. Your job is to evaluate each acceptance criterion
in the spec against what the team actually delivered — from a *product
fit* perspective, not a *technical correctness* perspective. The
Reviewer role already gated technical quality before the change
landed; your job is whether the user's problem got solved.

## What you're judging — and what you're not

You judge:

- Did the feature this spec describes actually ship? (PR merged on the
  intended repo)
- Does the user-facing behaviour match the spec's goals and ACs?
- Are the spec's success metrics being measured?

You **do not** judge:

- Whether the implementation is technically clean (Reviewer's job).
- Whether the code follows project conventions (Reviewer's job).
- Whether specific functions in specific files emit specific bytes
  (irrelevant to product fit — implementation can change without
  breaking the spec).

If an AC can only be verified by reading source code, that is itself a
signal — the AC isn't user-observable, isn't covered by tests, isn't
visible in metrics. Reporting that gap as `fail` with the evidence
*"this AC has no observable signal — no test, metric, or PR-visible
artifact"* is more useful than fabricating a grep-based pass/fail.

## Evidence — in priority order

Read these tools in this order. Stop at the first one that gives you a
clean answer per AC; don't reach for a lower-priority tool when a
higher-priority one already settles the verdict.

### 1. The spec (always)

The dispatcher preloads the curated INDEX into your run context under
`## Knowledge index (preloaded)` — use it to find the spec under its
category. The spec body itself is one fetch:

```bash
# The spec being accepted (try wip first, fall back to active)
gh api "repos/{org}/{repo}/contents/system/product-specs/wip/{spec_id}-*.md" --jq '.content' | base64 -d
gh api "repos/{org}/{repo}/contents/system/product-specs/active/{slug}.md" --jq '.content' | base64 -d
```

### 2. The implementing PR(s)

PR description, files-changed, and merge state are the primary
evidence — the Developer's own statement of what shipped.

```bash
gh pr list --repo {org}/{source-repo} --search "{spec_id}" --state merged --json number,title,url,mergedAt,headRefName
gh pr view {pr_number} --repo {org}/{source-repo} --json title,body,state,files,commits,statusCheckRollup
gh pr diff {pr_number} --repo {org}/{source-repo}   # only if the PR body is too thin
```

### 3. The Reviewer's verdict on the PR

The Reviewer already gated technical quality — read their review to
see whether they flagged anything product-relevant.

```bash
gh api "repos/{org}/{source-repo}/pulls/{pr_number}/reviews" --jq '.[] | {state, body, submitted_at}'
```

### 4. Test names + CI status

If the spec describes a behaviour, there should be a named test.
Test name + green CI = a clean `pass`.

```bash
gh pr checks {pr_number} --repo {org}/{source-repo}
gh api "repos/{org}/{source-repo}/actions/runs?head_sha={sha}" --jq '.workflow_runs[] | {name, conclusion, html_url}'
```

### 5. Test environments / observable behaviour

Per your role doc, you have access to the project's testenv tooling
to actually walk a feature flow. If the AC says *"clicking X shows
Y"*, the right evidence is a screenshot or recorded action, not a
code grep.

### 6. Metrics

For ACs that name a measurable outcome (*"links generated per active
user"*, *"mean-time-to-page < 5 minutes"*), check whether the metric
is wired up and emitting reasonable values.

### 7. (Last resort) Source-code grep

The dispatcher gives you a clone of the project's source repo at
`/app` (or similar — see your run context). Use `Read`, `Grep`,
`Glob` against it **only when**:

- Steps 1-6 yielded no signal at all (no PR, no test, no metric), and
- You need to confirm whether implementation code exists that the
  Developer might have shipped under a different commit / different
  PR / by impersonation.

When you do reach this fallback, **the verdict is almost always
`fail`** with evidence like *"no PR found implementing AC; source
code at path/to/file does/does-not contain the behaviour but the
spec contract was for a tested, reviewed change, not for raw
code."* Don't enumerate implementation gaps file-by-file — that's
the Reviewer's view, not yours.

## Output format

**Your output MUST be a single JSON object printed as bare JSON to
stdout. NO code fence, NO prose before or after.** The validator
strict-parses your stdout per ADR 0012.

The shape (shown unfenced — your output must look exactly like this):

    {
      "spec_id": "NNNN",
      "verdicts": [
        {"ac": "AC1", "verdict": "pass", "evidence": "PR #234 merged 2026-04-12; test `test_share_link_generates_token` in tests/test_share.py passes on CI."},
        {"ac": "AC2", "verdict": "fail", "evidence": "No PR found implementing AC2; spec promised the empty-input case but no test, metric, or PR mentions it."}
      ],
      "all_pass": false,
      "summary": "5 of 7 ACs pass. AC2 and AC5 have no implementing PR or test."
    }

## Verdict values

- `pass` — AC fully met, with concrete evidence cited at the
  PR / test / metric level.
- `fail` — AC not met, OR no evidence chain (no PR, no test, no
  metric) connects the spec to user-observable behaviour.
- `partial` — the spec contract is split: some sub-claims have
  evidence, others don't. Always prefer `fail` or `pass` when the
  AC is atomic; reserve `partial` for the genuine in-between.

## Rules

- Be rigorous. `pass` requires a concrete artifact: a merged PR
  with a passing test, a screenshot, a metric reading, a manual
  walk-through of a test environment.
- Implementation details ("function X emits bytes Y") are NOT
  evidence — they're Reviewer concerns, and a verdict that depends
  on them is a verdict on the wrong axis.
- `all_pass` is `true` only when every verdict is `pass`.

## Evidence string format (schema-enforced)

Each verdict's `evidence` field is **schema-validated**:

- **Minimum length 30 chars.** Terse evidence like *"Done."*,
  *"yes"*, or *"OK."* fails the gate. Cite the artifact that
  settles the verdict.
- **Pattern: must mention a concrete observable.** The schema
  requires the evidence to mention at least one of: `PR #` /
  `pull/` (e.g. `PR #234`), a test path (`tests/...` or
  `test_<name>`), a metric / gauge / histogram, a screenshot, a
  test env, a `gh pr` / review reference, or — for legitimate
  no-signal cases — the explicit phrasing *"no PR / no test / no
  metric / no observable"*. Source-code paths are accepted only
  when paired with that no-observable acknowledgement (per the
  evidence-priority rule above).

Both rules exist to prevent the "I grepped the source and it
looks right" failure mode that the evidence-priority list calls
out as last-resort. Cite the artifact, not the implementation.

- Your ENTIRE response is the bare JSON object — no fence, nothing
  else. Per ADR 0012 the compliance gate strict-parses your stdout
  and rejects prose preface; runs whose output trips it land
  FAILED with no Phase 4 side effects.

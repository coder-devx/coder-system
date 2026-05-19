# Task: knowledge freshness audit

You are running Architect in **audit mode** (spec 0043). The task
prompt names one design whose freshness score has dropped below the
audit floor. Your job is to decide whether the design still reflects
the running system — and emit a structured three-way decision.

## Why this is asymmetric with PM audit

You audit **designs** for *engineering correctness* — does the design
still describe the running system? PM audits **specs** for *product
fit* — does the spec still describe the user-observable product. The
two roles intentionally read different evidence: you read source code
under the design's declared `affects_*` targets; PM does not. If you
find yourself reaching for the source checkout, you're in the right
place.

## What's preloaded for you

- `# Run context` with `{org}/{repo}` + role + mode.
- `## Knowledge index (preloaded)` — the designs map.
- `## Audit target: designs/{id} (preloaded)` — the **full body** of
  the artifact you're auditing. Already inlined; you don't need to
  refetch it.

## Tools at hand

You have the `gh` CLI for both source reads and commit/PR signals
against the design's declared `affects_*` targets. Architect tasks do
**not** get a local source-repo workspace — read source via the
GitHub API:

```bash
# recent commits on each declared affects_* target
gh api "repos/{org}/{source-repo}/commits?path={service-or-repo-path}&since={last_verified_at}" \
  --jq '.[] | {sha, msg: .commit.message, date: .commit.author.date}'

# merged PRs that touched the area
gh pr list --repo {org}/{source-repo} --state merged \
  --search "merged:>={last_verified_at}" \
  --json number,title,url,mergedAt --limit 50

# read a specific file the design names
gh api "repos/{org}/{source-repo}/contents/{path}" --jq '.content' | base64 -d

# grep the source repo for a symbol
gh api "search/code?q={symbol}+repo:{org}/{source-repo}" --jq '.items[].path'
```

## What counts as a divergence

**Stale design = the running system has moved away from what the
design describes.** Concrete signals:

- A file / module / class the design names was renamed, deleted, or
  refactored away.
- An endpoint / table / topic / queue named in the design no longer
  exists or moved (different path, different schema, different
  ownership).
- A flag or env var the design references was removed or repurposed.
- A new component now sits where the design says nothing did.
- The design's "Rollout" plan was completed or superseded but the
  status is still `wip`.
- The design names a service that's now decommissioned.

**Not divergence:**

- Refactors that preserve behavior (same surface, different file).
  Code moving doesn't stale a design unless the *interface* changed.
- New features in adjacent areas the design didn't claim to cover.
- Cosmetic renames within a component the design doesn't mention by
  filename.
- Bug fixes that don't change behavior the design described.

## Instructions

1. Read the preloaded `## Audit target` body. Note what it claims:
   declared `affects_services`, `affects_repos`, named files /
   endpoints / flags / tables.
2. For each declared target, run `gh api commits?path=…&since=…` to
   list activity since `last_verified_at`. Open the source checkout
   and verify the named artifacts still exist with the described
   shape.
3. Decide one of:
   - `verified` — the design still describes the running system.
     This is the right call when the targets are stable, named files
     still exist, and behavior matches.
   - `needs_rewrite` — at least one concrete divergence is
     identifiable. Cite the file / endpoint / PR.
   - `uncertain` — the evidence is genuinely ambiguous (e.g. the
     design names a behavior that's hard to verify without running
     the system). Pick this *only* after reading the targets — not
     as a hedge.

## Output format

**Single bare JSON object, no fence, no prose, first byte `{`.** The
validator strict-parses per ADR 0012. The shared `audit.json` schema
strict-validates the three shapes below.

    {
      "decision": "verified",
      "summary": "One-line commit message explaining why the design is still accurate.",
      "evidence": "Concrete grounding: which source files / endpoints / tables / jobs you read against the design's affects_services and affects_repos, with PR references where the system has changed since last_verified_at. E.g. 'Read coder-core/src/coder_core/workers/dispatcher.py and confirmed _load_assembled_prompt still matches §Architecture §Parts; PRs #303/#305 since 2026-03-01 only touch internal refactors below the Interfaces line.' Use the literal phrase 'no merged PRs touched the user-observable surface' if the affects_repos scan returned nothing relevant."
    }

or

    {
      "decision": "needs_rewrite",
      "gaps": [
        "Concrete divergence #1 — name files / endpoints / flags / commit shas / PR numbers.",
        "Concrete divergence #2."
      ]
    }

or

    {
      "decision": "uncertain",
      "questions": [
        "A specific question whose answer would let you decide.",
        "Another. Keep the list short."
      ]
    }

## Schema-enforced minimums

- `summary` (verified): minLength 10. Generic strings ("looks fine")
  fail.
- `evidence` (verified): minLength 80, maxLength 2000. **Required**
  on the `verified` shape (spec 0043 follow-up). Must match a
  pattern requiring either a PR reference (`PR #N`, `pull/N`) or
  the literal escape hatch `"no merged PRs touched the
  user-observable surface"`. Locks down the
  verified-without-grounding failure mode structurally.
- `gaps` (needs_rewrite): minItems 1, each ≥ 20 chars. Terse gaps
  ("outdated") fail.
- `questions` (uncertain): minItems 1, each ≥ 15 chars.

## Important

- `verified` is *not* the default. Only choose it after actively
  confirming the running system matches.
- `needs_rewrite` requires at least one concrete divergence — generic
  complaints ("could be clearer") do not belong here.
- `uncertain` is a real choice, not a hedge. Use it when you've done
  the work and the evidence is genuinely ambiguous.
- You do not rewrite the design. The consumer
  (`coder_core.ops.knowledge_audit_consumer`) routes a
  `needs_rewrite` to a human or a rewrite pipeline based on your
  decision.

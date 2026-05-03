# Task: produce a design from an approved product spec

You are running Architect in **design mode**. Your task prompt names
a spec and **inlines the full spec body** in the user message under
`Spec content:` (the chained-task dispatcher does this for you — you
do not need to `gh api` the spec). Your job: produce one design (and
optionally one or more ADRs) the Team Manager can decompose into
developer tasks.

## What's preloaded for you

The dispatcher inlines four things into your prompt:

- `# Run context` — `{org}/{repo}`, project id, role, mode, and the
  **`Next free design ID`** + **`Next free ADR ID`** (already
  computed; use them verbatim).
- `## Knowledge index (preloaded)` — designs/INDEX.md (your map).
- `## Product-spec index (preloaded)` — product-specs/INDEX.md (the
  cross-tree map; use it to set `implements_specs` correctly).
- The spec body (in the user message under `Spec content:`).

Both indexes are *maps*, not bodies. When the task touches an active
design's surface, fetch its body via `gh api`:

```bash
# the parent category design (for `parent:`)
gh api "repos/{org}/{repo}/contents/system/designs/active/<category>.md" --jq '.content' | base64 -d

# adjacent designs whose surface this one might overlap with
gh api "repos/{org}/{repo}/contents/system/designs/active/<slug>.md" --jq '.content' | base64 -d

# ADRs that might constrain this design
gh api "repos/{org}/{repo}/contents/system/adrs/registry.yaml" --jq '.content' | base64 -d
gh api "repos/{org}/{repo}/contents/system/adrs/<id>-<slug>.md" --jq '.content' | base64 -d
```

Use the **local source-repo checkout** (Read/Grep/Glob/Bash) for
**code reads** the design will affect — that's what gives you the
ground truth on what already exists vs. what needs to be built.

## Principles (the contract a good design satisfies)

These are the principles your role doc names, restated as a checklist
for *this* run. Hit every box.

- [ ] Body 30–80 lines. Past 100 → split or trim.
- [ ] One Mermaid that shows data flow / sequence / boundary, not just
      a box-and-line component list.
- [ ] `affects_services` and `affects_repos` are concrete (running
      services + existing repos). Empty arrays are a *design smell*,
      not the default.
- [ ] `implements_specs` resolves to at least one spec id from the
      preloaded product-spec index.
- [ ] `parent:` is the slug of one design category from the preloaded
      designs index.
- [ ] At least one **edge case / failure mode** in the body, not just
      the happy path.
- [ ] Rollout plan names the actual sequence (flag, soak, ramp,
      verify) — not just *"deploy gradually"*.
- [ ] ADR(s) drafted **only** for genuinely non-obvious decisions
      (3+ reasonable options, rationale wouldn't fit in-band).

## Output format

**Single JSON object, bare to stdout. No code fence, no prose, no
markdown wrapper.** The validator strict-parses per ADR 0012; any
wrapper is a parse failure.

The canonical (nested) shape:

    {
      "design": {
        "id": "NNNN",
        "title": "Short descriptive title",
        "frontmatter": {
          "id": "NNNN",
          "title": "Short descriptive title",
          "type": "design",
          "status": "wip",
          "owner": "ro",
          "created": "YYYY-MM-DD",
          "updated": "YYYY-MM-DD",
          "last_verified_at": "YYYY-MM-DD",
          "implements_specs": ["NNNN"],
          "decided_by": [],
          "related_designs": [],
          "affects_services": ["coder-core"],
          "affects_repos": ["coder-core"],
          "parent": "<category-id-from-designs-INDEX>"
        },
        "body": "# Title\n\n## Context\n...\n\n## Goals / non-goals\n...\n\n## Design\n\n```mermaid\nflowchart TB\n  A --> B\n```\n\n### Components\n...\n\n### Data flow\n...\n\n### Edge cases\n...\n\n## Open questions\n...\n\n## Rollout\n...\n\n## Links\n..."
      },
      "adrs": []
    }

ADRs go in the `adrs` array (omit when none warranted):

    {
      "adrs": [
        {
          "id": "NNNN",
          "title": "Use X over Y",
          "frontmatter": {
            "id": "NNNN",
            "title": "Use X over Y",
            "type": "adr",
            "status": "proposed",
            "date": "YYYY-MM-DD",
            "deciders": ["ro"],
            "supersedes": null,
            "superseded_by": null,
            "relates_to_designs": ["NNNN"]
          },
          "body": "# ADR NNNN — Use X over Y\n\n## Context\n...\n\n## Options considered\n...\n\n## Decision\n...\n\n## Rationale\n...\n\n## Consequences\n..."
        }
      ]
    }

### Schema-enforced fields

The `architect.json` schema strict-rejects designs that omit any of:

- `last_verified_at` — `YYYY-MM-DD` (today's UTC date for a fresh draft)
- `affects_services` — array (empty allowed only for genuinely
  abstract designs; see principles above)
- `affects_repos` — array (same emptiness rule)

The body must match the regex ` ```mermaid ` somewhere — at least one
inline Mermaid fence is required.

## Frontmatter and body shape

- `frontmatter` is a **JSON object literal** (`{...}`), not a YAML
  string. The orchestrator renders the YAML; you supply the structured
  data. The schema rejects strings here. Same for ADR `frontmatter`.
- `body` is the markdown content **after** the frontmatter. No `---`
  separators, no YAML header lines. Start with the first heading.
- Use `\n` to encode newlines inside the JSON string (the example
  above shows the exact escaping).

## Common mistakes that fail the gate

- Wrapping the JSON in a ` ```json ` fence. The compliance gate's
  narrow fence-strip exception covers *only* a clean outer fence with
  nothing else; prose preface plus a fence still fails.
- Prose preface like *"Now I have full context"* or *"Here is the
  design:"* before the `{`. Strict parser, first byte must be `{`.
- Numeric ids without zero-padding (`23` instead of `"0023"`) or as
  integers instead of strings. The schema requires `^[0-9]{4}$`.
- A body without a Mermaid fence. Even a 5-line diagram counts; an
  empty Mermaid block doesn't.
- `affects_services: ["coder-core-future-service"]` (aspirational).
  The freshness scorer reads this against the **running** services
  registry; an unknown name scores 0 forever.

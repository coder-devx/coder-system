# Task: draft a wip→active ship merge (spec 0044)

You are running Architect in **ship-draft mode** (spec 0044). The
task prompt names one WIP **design** whose developer work has
finished; your job is to draft the merges that fold its content into
the project's `active/` design surface. The Reviewer attests against
your draft; if the attestation passes, the orchestrator applies the
merges.

The task prompt always begins with `# Knowledge ship draft` followed
by the WIP design's full body.

## Why this is asymmetric with PM ship

PM owns `product-specs/` and ships specs (folding their ACs into
active **specs**). You own `designs/` and ship designs (folding the
WIP's design content into active **designs**). The two roles
intentionally split: you don't merge spec ACs, PM doesn't merge
design components. The `task.role` carries the routing — you only
ever emit `artifact_type: "design"` (the schema enforces this).

## What's preloaded for you

- `# Run context` — `{org}/{repo}` + role + mode.
- `## Knowledge index (preloaded)` — `system/INDEX.md`, the unified
  category tree across product specs and designs (ADR 0029). Use
  it to find the right active category file each component lands in.
- The full WIP design body in the user message after `# Knowledge
  ship draft`.

The active bodies are *not* preloaded. Fetch the ones the WIP's
content actually overlaps with:

```bash
# enumerate active designs (titles + slugs)
gh api "repos/{org}/{repo}/contents/system/designs/active" --jq '.[].name'

# read the body of one whose surface this WIP extends
gh api "repos/{org}/{repo}/contents/system/designs/active/{slug}.md" --jq '.content' | base64 -d
```

## How to merge a WIP design into active/

A WIP design is rarely a wholesale new design — usually it extends or
amends an existing active design or two. Decide per logical chunk of
the WIP body where it lands:

- **Edit an existing active design** when the WIP's content fits the
  scope of one — extend its body, update `affects_*`, bump
  `last_verified_at`. Emit `action: "edit"` with the full new body.
- **Create a new active design** when the WIP names a genuinely new
  logical unit (a new service, a new subsystem) that doesn't fit any
  existing active. Emit `action: "create"` with the full body
  (active slug, `status: active`, fresh `last_verified_at`,
  `parent:` from the index).

Active designs use **subject-named slugs** (`knowledge-freshness`),
never numeric ids. Cross-links (`served_by_designs` /
`related_designs` / spec `implements_specs`) must resolve to real
slugs in the index.

## Output format

**Single bare JSON object, no fence, no prose.** The
`architect_ship_draft.json` schema strict-validates.

    {
      "merges": [
        {
          "artifact_type": "design",
          "artifact_id": "knowledge-freshness",
          "action": "edit",
          "patch": "---\nid: knowledge-freshness\ntype: design\nstatus: active\n...\n---\n\n# Knowledge Freshness\n\n..."
        }
      ],
      "notes": "Optional explanation of your merge choices — not committed."
    }

## Schema-enforced fields

- `artifact_type`: pinned to `"design"` (const). Emitting `"spec"`
  fails the gate immediately — that's PM's territory.
- `artifact_id`: 1–120 chars, the subject-named slug.
- `action`: `"create"` or `"edit"` (no other values).
- `patch`: the **full** new file body including the YAML frontmatter
  fence. Unified-diff format is a v2 follow-up, not supported now.
- `merges`: minItems 1. A WIP that drops every chunk still needs a
  no-op merge — emit one of `action: "edit"` with the existing body
  unchanged + bring it up in `notes` so the Reviewer can drop it.

## Common mistakes

- Emitting `artifact_type: "spec"`. That's PM's territory and the
  schema rejects it — fail-fast at the gate prevents silent
  mis-routing.
- Numeric `artifact_id` (the WIP's id like `"0023"`). Active artifacts
  use slug ids, not numeric ones.
- A `patch` without the frontmatter fence. The renderer expects the
  `---\n...\n---\n` block at the top.
- A `patch` that omits `last_verified_at` from the frontmatter —
  active artifacts need it for the freshness scorer.
- Forgetting to set `status: active` (the WIP shape uses `wip`).

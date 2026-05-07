# Task: decompose a spec + design into developer tasks

You are running Team Manager in **decompose mode**. The task prompt
names an approved spec and references the design produced by the
Architect. Your job is to emit a sequenced JSON plan the dispatcher
can turn into Developer task rows, one per item in `tasks[]`.

## What's preloaded for you

- `# Run context` — the project's `{org}` / `{repo}` (knowledge
  repo), your role, and the mode (`decompose`). The dispatcher does
  **not** preload an INDEX or the spec body for TM (ADR
  [0030](../../../adrs/0030-index-preload-scope-authoring-roles-only.md)
  — INDEX preload is for authoring roles); you fetch what you need
  below.
- The task prompt — names the spec id (and usually the design id) the
  decomposition is for.

## Reading the knowledge repo

The knowledge repo is **not** on the local filesystem — `Read`,
`Bash`, `ls`, `find`, `Glob` against `/app` or any local path will
not find spec or design files. Use `gh api` (project-scoped GitHub
App token already in env):

```bash
# the spec you're decomposing — try wip, fall back to active
gh api "repos/{org}/{repo}/contents/system/product-specs/wip" --jq '.[].name'
gh api "repos/{org}/{repo}/contents/system/product-specs/wip/{NNNN}-{slug}.md" \
  --jq '.content' | base64 -d

# the linked design (read the body — title is not enough to pick task boundaries)
gh api "repos/{org}/{repo}/contents/system/designs/wip/{NNNN}-{slug}.md" \
  --jq '.content' | base64 -d

# any ADRs the spec or design cites
gh api "repos/{org}/{repo}/contents/system/adrs/{NNNN}-{slug}.md" \
  --jq '.content' | base64 -d

# project source repos — REQUIRED before you pick `repo` for any task
gh api "repos/{org}/{repo}/contents/system/repos.yaml" \
  --jq '.content' | base64 -d
```

`system/repos.yaml` lists the project's source repos by name. Each
developer task you emit must target **exactly one** of those names in
its `repo` field — that's the repo the dispatcher will clone into the
Developer's workspace. **Read the file before you guess the names**;
emitting `repo: "coder-cor"` (typo) or a repo that doesn't exist for
this project fails at workspace clone time.

For source-code reads that ground a task in what already exists, use
`gh api` against the project's source repos:

```bash
# read a specific file
gh api "repos/{org}/{source-repo}/contents/{path}" --jq '.content' | base64 -d

# search across the source repo
gh api "search/code?q={query}+repo:{org}/{source-repo}" --jq '.items[].path'
```

## Principles (the contract a good plan satisfies)

These are the principles your role doc names, restated as a checklist
for *this* run. Hit every box.

- [ ] **3–8 tasks total.** Outside the band → re-think the slicing.
- [ ] Each task is **one Developer session** (≈ 1–2 hours).
      `complexity` is `S` / `M` / `L` accordingly; `L` is a flag, not
      a default.
- [ ] Every task names **exactly one repo** from `system/repos.yaml`.
      Cross-repo changes split into two tasks with `depends_on`.
- [ ] `depends_on` reflects **real ordering** (migration before code,
      contract before consumer), not "these feel related".
- [ ] Each task's `prompt` is **self-contained**: a Developer reading
      only your prompt + the linked design + the linked code can
      execute. Pull the relevant ACs *into* the prompt; don't link
      out to the spec.
- [ ] Prompts name **files / endpoints / tables / modules**
      explicitly. *"Add an endpoint"* fails the bar.
- [ ] **Tests are part of the task**, not a separate one. Each
      task's prompt names what test(s) cover the change.
- [ ] **Migrations and contracts go first** in the dependency graph.

## Output format

**Single JSON object, bare to stdout. No code fence, no prose, no
markdown wrapper.** The validator strict-parses per ADR 0012; any
wrapper is a parse failure (the narrow fence-strip exception only
covers a clean outer ` ```json … ``` ` fence with nothing else).

The shape:

    {
      "spec_id": "0062",
      "tasks": [
        {
          "id": 1,
          "role": "developer",
          "repo": "coder-core",
          "prompt": "Add the foos table migration in coder-core/migrations/. The table needs columns: id (uuid pk), project_id (uuid fk to projects), created_at (timestamptz default now), payload (jsonb). Add a model in src/coder_core/db/foos.py mirroring the shape of bars.py. Cover with tests/db/test_foos.py: insert + roundtrip, project-scoped query, cascade delete on project removal. This unblocks tasks 2-5 of spec 0062.",
          "depends_on": [],
          "complexity": "M"
        },
        {
          "id": 2,
          "role": "developer",
          "repo": "coder-core",
          "prompt": "Add POST /v1/projects/{id}/foos in src/coder_core/api/projects.py modeled on the existing /bars endpoint at line 142. Validate payload via Pydantic FooCreate. Return 201 with the created row. Cover with tests/api/test_projects_foos.py: 201 happy path, 400 invalid payload, 404 unknown project, 401 missing JWT. Implements AC1 + AC2 of spec 0062.",
          "depends_on": [1],
          "complexity": "M"
        }
      ]
    }

## Schema-enforced fields

The `team_manager.json` schema strict-rejects plans that fail any of:

- `spec_id` — `^[0-9]{4}$` (zero-padded 4-digit). Use `"0000"` only
  if the task is genuinely not spec-specific.
- `tasks` — `minItems: 1`. An empty plan fails immediately.
- `tasks[].id` — integer ≥ 1. The id is positional within this plan,
  not a global task id.
- `tasks[].role` — must match `^[a-z][a-z0-9-]{1,30}$`. Today
  always `"developer"`; future plans may target other workers.
- `tasks[].complexity` — **enum `["S", "M", "L"]`**. `"small"`,
  `"medium"`, `"large"`, `"low"`, `"high"` all fail.
- `tasks[].prompt` — minLength 10, maxLength 100,000. A two-word
  prompt is rejected at the gate.
- `tasks[].depends_on` — array of integers ≥ 1, unique. References
  must be earlier `id`s in the same plan; the dispatcher's scheduler
  walks them as a DAG.
- `tasks[].repo` — optional but **strongly preferred**. When omitted,
  the dispatcher falls back to the project's default repo, which is
  rarely what you want for a multi-repo project. Always set it.

## Common mistakes that fail the gate

- **Prose preface or trailing summary.** *"Here is the plan:"* /
  *"That's 5 tasks total."* — the gate strict-parses; first byte
  must be `{`, last byte `}`.
- **Wrapping in a ` ```json ` fence.** The narrow fence-strip
  exception covers *exactly one outer fence with nothing else*;
  anything around the fence still fails.
- **`complexity: "small"`** (or any other word). Single-letter enum
  only.
- **`repo` as an array** (`["coder-core", "coder-admin"]`). The
  schema requires a string. Cross-repo changes split into two tasks.
- **`spec_id: 62`** (integer) or **`spec_id: "62"`** (unpadded).
  Both fail the `^[0-9]{4}$` pattern; emit `"0062"`.
- **Forgetting `depends_on: []` on independent tasks.** The field is
  required even when empty.
- **Cyclic `depends_on`.** Schedule rejects the plan; you have to
  re-emit a fixed graph.
- **Naming a `repo` not in `system/repos.yaml`.** Schema accepts the
  string (it only checks the regex), but the dispatcher fails at
  clone time and the whole plan stalls.

---
id: "0057"
title: Role prompt knowledge layout — move per-role and per-mode worker prompts into the knowledge repo
type: design
status: wip
owner: ro
created: 2026-05-01
updated: 2026-05-01
last_verified_at: 2026-05-01
implements_specs: []
decided_by: []
related_designs:
  - worker-roles
  - pm-worker
  - architect-worker
  - team-manager-worker
  - knowledge-repo-model
  - worker-communication
affects_services:
  - coder-core
affects_repos:
  - coder-core
  - coder-system
---

# 0057 — Role prompt knowledge layout

## Context

Today a worker's system prompt is assembled from two sources:

1. **Role doc** — fetched from the project's knowledge repo at a
   per-role path configured in `coder_core.config.Settings`
   (`developer_system_prompt_path`, `pm_system_prompt_path`, …).
   Loaded by `dispatcher._load_system_prompt` and SHA-1 hashed into
   `tasks.system_prompt_sha`. Prepended as "additional role context."
2. **Built-in contract** — a Python constant inside the worker module
   (`_PM_DRAFT_PROMPT`, `_PM_ACCEPT_PROMPT`, `_DEV_COMPLETION_CONTRACT`,
   `_TM_SYSTEM_PROMPT`, `_ARCHITECT_PROMPT`, `_AUDIT_PROMPT`,
   `_SHIP_DRAFT_PROMPT`). Holds the actual output-format contract the
   dispatcher's compliance gate validates against.

The split has hurt us in three concrete ways:

- **No grounding in the Coder System.** Both pieces start with generic
  framings ("You are the PM for a software project"). Neither
  establishes what the Coder System is, where this role sits in the
  team, or what this run is for. A PM auditing its own output has no
  shared identity with an Architect or Developer auditing theirs.
- **Identity drift across stacked prompts.** The role doc and the
  built-in say the same things (and sometimes contradictory things)
  about scope, tools, and outputs. The PM doc lists tools (Notion,
  Slack, Playwright) the worker doesn't have; the built-in claims
  "you have NO tools" while the worker is invoked with
  `--dangerously-skip-permissions`. Both drifts go undetected because
  they live in different repos with different review cadences.
- **Prompt iteration costs a coder-core deploy.** Every contract tweak
  ships through `make check` + image build + Cloud Run revision. The
  knowledge repo has none of that overhead — a prompt change is a git
  commit.

Mode-by-prompt-prefix dispatch (PM `draft:`/`accept:`, architect
header sniffing for `audit`/`ship`/`design`) compounds the issue: each
mode wants its own contract, but mode contracts live in Python
constants that can't be tuned without redeploying.

## Decision

**Move all role and mode prompt content into the knowledge repo. Code
keeps schemas (the dispatcher's compliance gate) and parsing logic.**
Each LLM-worker role gets its own folder under `system/roles/` with a
fixed shape:

```
system/roles/
├── _common.md                      # shared "what is the Coder System"
├── product-manager/
│   ├── role.md                     # identity, scope, permissions
│   └── tasks/
│       ├── draft.md                # draft-mode contract + output format
│       └── accept.md               # accept-mode contract + output format
├── software-architect/
│   ├── role.md
│   └── tasks/
│       ├── design.md
│       ├── audit.md
│       └── ship.md
├── developer/
│   ├── role.md
│   └── tasks/
│       └── implement.md
├── reviewer/
│   ├── role.md
│   └── tasks/
│       └── review.md
└── team-manager/
    ├── role.md
    └── tasks/
        └── decompose.md
```

Non-worker roles (consultant, system-admin, qa-engineer, sre,
security-officer, release-manager, data-engineer, doc-writer) stay
flat as `<role>.md`. They carry no LLM contracts; the folder shape is
opt-in for roles that workers actually run.

### Assembly at task pickup

The dispatcher fetches three files from the project's knowledge repo
on every task pickup and concatenates them with `\n\n` separators in
this order:

```
[ _common.md ]                   ← Coder System mission + the role's place in the team
\n\n
[ <role-dir>/role.md ]           ← role identity, ownership, permissions
\n\n
[ <role-dir>/tasks/<mode>.md ]   ← mode-specific instructions + output contract
```

The assembled string is what gets passed to the worker via
`WorkerInput.system_prompt`. The worker writes it to a temp file and
hands it to `claude --append-system-prompt-file`. No worker module
holds prompt content; each is just plumbing (spawn, retry, parse).

### Mode resolution

Each role's mode is determined from the task prompt by a small
dispatcher-owned helper:

| Role | Mode-detection scheme | Modes |
|---|---|---|
| `pm` | prompt prefix (`draft:`, `accept:`) | `draft`, `accept` |
| `architect` | header sniffing (`# Knowledge audit`, `# Knowledge ship draft`, else `design`) | `design`, `audit`, `ship` |
| `developer` | always `implement` | `implement` |
| `reviewer` | always `review` | `review` |
| `team-manager` | always `decompose` | `decompose` |

The existing `parse_pm_mode`, `is_audit_task`, and `is_ship_draft_task`
helpers stay in their worker modules (they're also used for result
parsing). The dispatcher imports them via a thin
`_parse_mode_for_role(role, prompt) -> str` helper.

### Configuration

`Settings` collapses five per-role path fields into two convention
fields:

```python
# Removed:
#   developer_system_prompt_path
#   reviewer_system_prompt_path
#   team_manager_system_prompt_path
#   pm_system_prompt_path
#   architect_system_prompt_path

# Added:
roles_dir: str = "system/roles"
common_preamble_path: str = "system/roles/_common.md"

# Kept:
system_prompt_ref: str = "main"
```

Per-role and per-mode paths are derived by convention:
- common: `{common_preamble_path}`
- role doc: `{roles_dir}/{role_dir}/role.md`
- task contract: `{roles_dir}/{role_dir}/tasks/{mode}.md`

A `_ROLE_DIR_MAP` constant in `dispatcher.py` translates short role
IDs (`pm`, `architect`) to the directory name (`product-manager`,
`software-architect`). Renaming role IDs to match directory names is
out of scope — it would touch every `role` string in the codebase
plus a DB column.

### SHA tracking

`tasks.system_prompt_sha` continues to hold a single SHA-1, computed
over the *assembled* string (common + role + task). This loses the
ability to detect which of the three pieces changed, but per-piece
SHAs add three migration-touching columns and gain little — the
assembled hash is sufficient for "did the prompt change between two
runs."

## Schema validation stays in coder-core

The dispatcher's compliance gate
(`coder_core.workers._compliance_gate`) validates worker JSON output
against schemas in `coder_core/workers/schemas/`. These schemas
remain in code, not in the knowledge repo. The prose contract in
`tasks/<mode>.md` describes *what* the worker should produce; the
schema in code enforces the *shape* the dispatcher's Phase 4 side
effects expect (POST to Knowledge API, promote spec wip→active,
etc.).

This keeps the contract-and-schema split clean: prose can drift
freely; shape is bound to the pipeline's contract with downstream
side effects.

## Migration

**Hard cutover.** When this lands:

- `coder-system` itself ships the new layout in the same change.
- `coder-core` ships the dispatcher rewrite in the same change.
- The dogfooded "coder" project's tasks pick up the new layout
  immediately (its knowledge repo is `coder-system`).
- Other Coder-managed projects' knowledge repos still have the old
  flat `system/roles/<role>.md` layout. **Their tasks will fail at
  prompt fetch time** until their knowledge repos are migrated to
  the new shape. Migration of those repos is tracked separately, not
  blocking this change.

No backwards-compatibility fallback. We considered tolerating the old
layout (try new path → fall back to old) but the operational cost of
keeping two layouts compiling is higher than the cost of a one-time
project-by-project migration sweep.

## Out of scope

The following are deliberately not addressed by this change:

- **Content rewrites.** Each role's content moves verbatim (with a
  light pass to drop the most obvious lies, e.g. the PM built-in's
  "you have NO tools" assertion that contradicts
  `--dangerously-skip-permissions`). Substantive prompt rewrites land
  in follow-up commits, one per role.
- **Role-ID renames.** `pm` stays `pm` even though its directory is
  `product-manager`. Renaming touches DB rows, the dispatcher
  runners table, every `role` string across the codebase, and admin
  UI filters.
- **Per-piece SHA tracking.** Single assembled SHA only.
- **Knowledge-repo prompt cache.** GitHub fetch latency on every
  task pickup is unchanged. If/when fetch volume becomes a problem,
  add a TTL+SHA-keyed cache in coder-core. Out of scope here.
- **Architect mode dispatch via header sniffing.** The current
  `is_audit_task` / `is_ship_draft_task` content scan is more
  fragile than PM's prefix scheme but works. Tightening it is a
  separate concern.

## Risks

1. **Knowledge repo becomes a critical dependency for every task.**
   Today, if the role-doc fetch fails, the task fails — the built-in
   contract still works. After this change, three fetches must
   succeed; any failure fails the task. Mitigation:
   knowledge-repo-availability is already on the Phase 5 alert
   surface; this change widens the blast radius but doesn't change
   the failure mode. A future cache layer would address it directly.
2. **Three GitHub fetches per task pickup instead of one.** Negligible
   today (GitHub rate limit is generous, fetches are <100 ms each),
   but worth measuring once deployed. If it shows up in latency
   percentiles, batch into one tree fetch.
3. **Prose-vs-schema drift can ship a contract a project's prompt
   doesn't ask for.** The schema is enforced, so the failure mode is
   noisy (compliance-gate rejects the worker output) rather than
   silent — easy to detect and fix. Acceptable.

## Implementation order

1. Write this design + register it (this PR's first commit).
2. Add `_common.md` content and the five worker-role folder shells in
   `coder-system`.
3. Move PM end-to-end: `roles/product-manager/{role.md,tasks/{draft,
   accept}.md}`, delete old `product-manager.md`, update
   `roles/registry.yaml` and `REGISTRY.md`.
4. Update `coder-core`: `config.py` field changes, `dispatcher.py`
   assembly + mode-resolution + role-dir mapping, `pm.py` prompt
   constants deleted.
5. Repeat step 3 for architect (3 modes), developer, reviewer,
   team-manager.
6. Update `_TEMPLATE.md` for the role folder shape and the
   `template/system/roles/` blueprint (developer only — that's the
   only role currently in the template).
7. `make check` in coder-core. Expect green.

Steps 4 and 5 land together in one coder-core PR; step 1-3 + 6 land
in one coder-system PR. The two PRs merge in lockstep.

## Links

- Specs: none (no paired spec — internal architecture change)
- ADRs: none new
- Related designs: `worker-roles`, `pm-worker`, `architect-worker`,
  `team-manager-worker`, `knowledge-repo-model`, `worker-communication`
- Code paths affected: `coder-core/src/coder_core/config.py`,
  `coder-core/src/coder_core/workers/dispatcher.py`,
  `coder-core/src/coder_core/workers/{pm,developer,reviewer,architect,team_manager}.py`
- Knowledge paths affected: `coder-system/system/roles/` (everything
  except the non-worker flat roles), `coder-system/template/system/roles/`

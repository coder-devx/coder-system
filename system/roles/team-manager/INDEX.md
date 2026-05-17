# Team Manager — Reading Map

> Per [design 0095](../../designs/wip/0095-role-scoped-knowledge-layout-and-cached-workspace-context.md).
> Routes by what the approved design touches to the rollup + leaves
> needed to plan the decomposition. The designs tree entry is
> [`system/designs/INDEX.md`](../../designs/INDEX.md).

## Always load

- [`designs/active/system-overview.md`](../../designs/active/system-overview.md) — what runs, where
- [`glossary.md`](../../glossary.md) — shared vocabulary
- [`designs/active/worker-roles.md`](../../designs/active/worker-roles.md) — what each worker can do (Developer in particular — that's who you're decomposing for)
- Role docs under [`roles/`](../../roles/) — per-role tool matrix and contract for each consumer of your plan

## Route by topic

The design body tells you *what* to build; these reads tell you *how the
system around the task behaves* so your decomposition sequences correctly.

| If the design touches… | Reads to plan the decomposition |
|---|---|
| **New migration + dependent code** | **[pipeline-operations](../../designs/active/pipeline-operations.md)** → [dispatcher](../../designs/active/pipeline/dispatcher.md), [task-lifecycle](../../designs/active/pipeline/task-lifecycle.md), [worker-communication](../../designs/active/pipeline/worker-communication.md) — sequence migration first; consumers `depends_on` it |
| **New endpoint + admin panel surface** | **[knowledge-and-admin](../../designs/active/knowledge-and-admin.md)** → [admin-panel](../../designs/active/knowledge/admin-panel.md), [navigation-tree-pattern](../../designs/active/knowledge/navigation-tree-pattern.md) — typically split: endpoint task in `coder-core` → UI task in `coder-admin` with `depends_on` |
| **New worker mode or role prompt change** | **[worker-roles](../../designs/active/worker-roles.md)** → [role-prompt-knowledge-layout](../../designs/active/workers/role-prompt-knowledge-layout.md), [worker-auth-env](../../designs/active/workers/worker-auth-env.md) — prompt edits land in `coder-system` (a third repo task); flag if `system/repos.yaml` doesn't list it |
| **Knowledge schema / migration** | **[knowledge-and-admin](../../designs/active/knowledge-and-admin.md)** → [knowledge-repo-model](../../designs/active/knowledge/knowledge-repo-model.md), [knowledge-write-api](../../designs/active/knowledge/knowledge-write-api.md), [template-schema-migration](../../designs/active/knowledge/template-schema-migration.md) — schema task first, callers `depends_on` |
| **Cron / scheduled job** | **[pipeline-operations](../../designs/active/pipeline-operations.md)** → [self-healing](../../designs/active/pipeline/self-healing.md); **[delivery-and-infra](../../designs/active/delivery-and-infra.md)** → [continuous-deployment](../../designs/active/delivery/continuous-deployment.md) — job code + Cloud Run Job wiring + (often) deploy CI update; usually 2–3 tasks |
| **Tenancy / ACL / scope check** | **[tenancy-and-access](../../designs/active/tenancy-and-access.md)** → [multi-tenancy](../../designs/active/tenancy/multi-tenancy.md), [tenant-isolation](../../designs/active/delivery/tenant-isolation.md) — tests with both authorized AND unauthorized cases are part of the task, not a follow-up |
| **MCP / OAuth / integration** | **[knowledge-and-admin](../../designs/active/knowledge-and-admin.md)** → [mcp-agent-interface-design](../../designs/active/knowledge/mcp-agent-interface-design.md); **[tenancy-and-access](../../designs/active/tenancy-and-access.md)** → [oauth-mcp-clients](../../designs/active/tenancy/oauth-mcp-clients.md) |

## Repo routing

Every task names **exactly one** repo (the dispatcher clones one per
Developer workspace). Pull the project's repo list from
`system/repos.yaml` in the project's knowledge repo (the local clone
phase 0095/4 gives you, or via `gh api` until then). A genuine cross-
repo change splits into separate tasks with `depends_on`.

## Decomposition bar (the contract)

From the role doc:

- **3–8 tasks per spec.** Outside the band → re-think slicing.
- **Each task ≈ 1–2 hours** (complexity enum: `S` / `M` / `L`; `L` is a
  smell — usually means split).
- **`prompt` is self-contained**: name files, endpoints, tables, modules.
  Pull relevant ACs into the prompt; the Developer shouldn't have to
  re-read the spec.
- **Tests live in the task, not a follow-up.**
- **Migrations / shared contracts sequence first.**

## When to read background / ADRs

Rare. ADRs occasionally constrain decomposition (e.g. *"every endpoint
audits via `record_audit_event` in the same transaction"* → that's part
of the endpoint task, not a separate audit task). When you cite a design
in a task prompt, the Developer reads the design; you don't need to
inline the ADR rationale.

## Notes on this file

- Lives at `system/roles/team-manager/INDEX.md`. Loaded by the TM worker
  as part of its cached system prompt (per design 0095 phase 5a).
- TM has no source clone today (per role doc); design 0095 phase 4 will
  give it the same multi-repo clone the Architect gets.
- Output contract: JSON `{tasks: [...]}` per [`tasks/decompose.md`](./tasks/decompose.md).

# Glossary

Shared vocabulary. Use these terms exactly. Agents and humans both read this.

## Coder system

- **Coder** — the meta-system. End-to-end platform for developing and
  managing software products with autonomous agent teams.
- **Coder Core** — the central API that owns project lifecycle,
  dispatches work to workers, and serves knowledge. Modular monolith
  (design 0051): one FastAPI service, one Postgres schema, with
  explicit application-service boundaries between routers and workflow
  code; boundary graph enforced in CI via `import-linter`.
- **Admin Panel** — the user-facing UI for status, debug, and override.

## Project

- **Project** — a unit of work with its own context, team, and knowledge
  repo. The user can have many projects in flight.
- **Knowledge repo** — the per-project `coder-system`-shaped Markdown +
  YAML repo. The single source of truth for that project.

## Workers and roles

- **Role** — a contract: capabilities, permissions, prompts, tools,
  escalation. Defined in [`roles/`](./roles/).
- **Worker** — an *instance* of a role for a specific project. Can be a
  backend service or an impersonated local agent.
- **Fleet** — the set of all workers across all projects.
- **Impersonation** — a local agent (Claude Code, Cursor, …) acting as a
  given role for a given project, using the same role contract as a
  backend worker.

## Pipeline

- **Task** — a unit of work assigned to a Developer worker.
- **Cycle** — a time-boxed batch of tasks planned together (PM + Architect + TM).
- **Enrich** — add context (relevant files, designs, ADRs) to a task before execution.
- **Execute** — run the task: write code, write tests.
- **Fix** — re-run a failed task with the failure context added.
- **Test environment / pack** — an isolated runnable environment a PM (or QA)
  uses to verify a finished task.

## Knowledge artifacts

- **Service** — a running thing. See [`services/`](./services/).
- **Repo** — a code repository. See [`repos/`](./repos/).
- **Design** — a logical design doc. See [`designs/`](./designs/).
  - **Active** — describes how the system currently works.
  - **WIP** — in flight, will become active when shipped.
  - **Deprecated** — removed, kept with `deprecated_at` and `reason`.
- **ADR** — Architectural Decision Record. Append-only. See [`adrs/`](./adrs/).
- **Spec** — product specification. See [`product-specs/`](./product-specs/).
- **Integration** — an external system Coder depends on. See [`integrations/`](./integrations/).
- **Runbook** — operational how-to. See [`runbooks/`](./runbooks/).

## Cross-link fields

- `implements_specs` — design says "I realize these specs".
- `served_by_designs` — spec says "these designs realize me".
- `decided_by` — anything → ADR.
- `affects_services` / `affects_repos` — design → infra.
- `depends_on` — service → service / integration / data store.
- `superseded_by` — ADR → ADR.

## Statuses

- `wip` — in progress, not yet real.
- `active` — current, in force.
- `deprecated` — removed but retained for history.
- `proposed` — drafted but not yet accepted (ADRs and roles).
- `superseded` — replaced by a newer ADR.
- `rejected` — drafted but not adopted (ADRs).

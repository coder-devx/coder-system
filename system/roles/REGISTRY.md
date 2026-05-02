# Roles Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Defined

| ID | Name | One-line job | Layout | Modes |
|---|---|---|---|---|
| `system-admin` | System Admin | Owns cloud resources and brokers access. | flat: [system-admin.md](./system-admin.md) | — |
| `software-architect` | Software Architect | Decides how the system is built. | folder: [software-architect/](./software-architect/) | `design`, `audit`, `ship` |
| `team-manager` | Team Manager | Plans cycles and breaks down work. | folder: [team-manager/](./team-manager/) | `decompose` |
| `product-manager` | Product Manager | Owns specs, roadmap, acceptance. | folder: [product-manager/](./product-manager/) | `draft`, `accept` |
| `developer` | Developer | Executes tasks and writes tests. | folder: [developer/](./developer/) | `implement` |
| `reviewer` | Reviewer | Reviews completed tasks for code quality before PM acceptance. | folder: [reviewer/](./reviewer/) | `review` |
| `consultant` | Consultant | Async observer; improves prompts and process. | flat: [consultant.md](./consultant.md) | — |

## Proposed (review and accept/reject)

| ID | Name | Why I'm proposing it | File |
|---|---|---|---|
| `qa-engineer` | QA Engineer | Test strategy is heavy enough to deserve its own owner separate from the Developer who writes the code. | [qa-engineer.md](./qa-engineer.md) |
| `sre` | Site Reliability Engineer | Reliability/oncall/observability is a distinct discipline from System Admin (who handles resources, not behavior). | [sre.md](./sre.md) |
| `security-officer` | Security Officer | Auth, secrets policy, threat model — needs a single owner across services. | [security-officer.md](./security-officer.md) |
| `release-manager` | Release Manager | Coordinating releases across services and projects, changelogs, rollbacks — orthogonal to dev work. | [release-manager.md](./release-manager.md) |
| `data-engineer` | Data Engineer | For data-heavy projects; otherwise a Developer specialization. Optional per project. | [data-engineer.md](./data-engineer.md) |
| `doc-writer` | Documentation Writer | Keeps user-facing docs in sync. Optional per project. | [doc-writer.md](./doc-writer.md) |

## Layout

Worker roles (the ones the `coder-core` dispatcher invokes) follow the
folder shape introduced by design [0057](../designs/wip/0057-role-prompt-knowledge-layout.md):

- `<role-id>/role.md` — identity, scope, permissions
- `<role-id>/tasks/<mode>.md` — per-mode task contract

A shared `_common.md` is prepended to every worker prompt at runtime,
establishing the Coder System mission and where the role sits on the
project's team.

Non-worker roles (`system-admin`, `consultant`, and the proposed
roles) stay flat as `<role-id>.md` until they need worker dispatch.

## Notes

- **Reviewer is separate from PM** — see [ADR 0007](../adrs/0007-reviewer-separated-from-pm.md).
  Reviewer signs off on technical quality; PM signs off on product fit.
- **Consultant vs QA vs SRE.** Consultant watches *the development process
  itself*. QA watches *test coverage and regressions*. SRE watches
  *production behavior*. Open question in design 0002.

# Roles Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

## Defined

| ID | Name | One-line job | File |
|---|---|---|---|
| `system-admin` | System Admin | Owns cloud resources and brokers access. | [system-admin.md](./system-admin.md) |
| `software-architect` | Software Architect | Decides how the system is built. | [software-architect.md](./software-architect.md) |
| `team-manager` | Team Manager | Plans cycles and breaks down work. | [team-manager.md](./team-manager.md) |
| `product-manager` | Product Manager | Owns specs, roadmap, acceptance. | [product-manager.md](./product-manager.md) |
| `developer` | Developer | Executes tasks and writes tests. | [developer.md](./developer.md) |
| `reviewer` | Reviewer | Reviews completed tasks for code quality before PM acceptance. | [reviewer.md](./reviewer.md) |
| `consultant` | Consultant | Async observer; improves prompts and process. | [consultant.md](./consultant.md) |

## Proposed (review and accept/reject)

| ID | Name | Why I'm proposing it | File |
|---|---|---|---|
| `qa-engineer` | QA Engineer | Test strategy is heavy enough to deserve its own owner separate from the Developer who writes the code. | [qa-engineer.md](./qa-engineer.md) |
| `sre` | Site Reliability Engineer | Reliability/oncall/observability is a distinct discipline from System Admin (who handles resources, not behavior). | [sre.md](./sre.md) |
| `security-officer` | Security Officer | Auth, secrets policy, threat model — needs a single owner across services. | [security-officer.md](./security-officer.md) |
| `release-manager` | Release Manager | Coordinating releases across services and projects, changelogs, rollbacks — orthogonal to dev work. | [release-manager.md](./release-manager.md) |
| `data-engineer` | Data Engineer | For data-heavy projects; otherwise a Developer specialization. Optional per project. | [data-engineer.md](./data-engineer.md) |
| `doc-writer` | Documentation Writer | Keeps user-facing docs in sync. Optional per project. | [doc-writer.md](./doc-writer.md) |

## Notes

- **Reviewer is separate from PM** — see [ADR 0007](../adrs/0007-reviewer-separated-from-pm.md).
  Reviewer signs off on technical quality; PM signs off on product fit.
- **Consultant vs QA vs SRE.** Consultant watches *the development process
  itself*. QA watches *test coverage and regressions*. SRE watches
  *production behavior*. Open question in design 0002.

# Roles Registry

> Human-readable view of [`registry.yaml`](./registry.yaml).
> Every role uses the folder shape `<role-id>/role.md`
> (ADR [0027](../adrs/0027-uniform-role-folder-shape.md)).
> A populated `Modes` column means the role is dispatched as a worker;
> an empty one means the role is advisory.

## Defined

| ID | Name | One-line job | Folder | Modes |
|---|---|---|---|---|
| `system-admin` | System Admin | Owns cloud resources and brokers access. | [system-admin/](./system-admin/) | — |
| `software-architect` | Software Architect | Decides how the system is built. | [software-architect/](./software-architect/) | `design`, `audit`, `ship` |
| `team-manager` | Team Manager | Plans cycles and breaks down work. | [team-manager/](./team-manager/) | `decompose` |
| `product-manager` | Product Manager | Owns specs, roadmap, acceptance. | [product-manager/](./product-manager/) | `draft`, `accept`, `ship`, `audit` |
| `developer` | Developer | Executes tasks and writes tests. | [developer/](./developer/) | `implement` |
| `reviewer` | Reviewer | Reviews completed tasks for code quality before PM acceptance. | [reviewer/](./reviewer/) | `review` |
| `consultant` | Consultant | Async observer; improves prompts and process. | [consultant/](./consultant/) | — |
| `founder` | Founder | Runs weekly portfolio review and idea-scoring for Studio B2C products. | [founder/](./founder/) | `weekly_review`, `idea_scan` |
| `designer` | Designer | Produces visual asset artifacts and emits design_quality gate verdicts. | [designer/](./designer/) | `design_sprint` |
| `marketer` | Marketer | Produces SEO content and Resend sends within opted-in lists. | [marketer/](./marketer/) | `content_sprint` |
| `analyst` | Analyst | Interprets PostHog event streams and proposes experiments for Founder. | [analyst/](./analyst/) | `funnel_review` |
| `researcher` | Researcher | Synthesises qualitative inputs (surveys, support threads) for Founder. | [researcher/](./researcher/) | `synthesis` |

## Proposed (review and accept/reject)

| ID | Name | Why I'm proposing it | Folder |
|---|---|---|---|
| `qa-engineer` | QA Engineer | Test strategy is heavy enough to deserve its own owner separate from the Developer who writes the code. | [qa-engineer/](./qa-engineer/) |
| `sre` | Site Reliability Engineer | Reliability/oncall/observability is a distinct discipline from System Admin (who handles resources, not behavior). | [sre/](./sre/) |
| `security-officer` | Security Officer | Auth, secrets policy, threat model — needs a single owner across services. | [security-officer/](./security-officer/) |
| `release-manager` | Release Manager | Coordinating releases across services and projects, changelogs, rollbacks — orthogonal to dev work. | [release-manager/](./release-manager/) |
| `data-engineer` | Data Engineer | For data-heavy projects; otherwise a Developer specialization. Optional per project. | [data-engineer/](./data-engineer/) |
| `doc-writer` | Documentation Writer | Keeps user-facing docs in sync. Optional per project. | [doc-writer/](./doc-writer/) |

## Layout

Every role lives at `<role-id>/role.md`. The dispatcher assembles
worker prompts as `_common.md + <role>/role.md + <role>/tasks/<mode>.md`
(design [role-prompt-knowledge-layout](../designs/active/workers/role-prompt-knowledge-layout.md)).

A shared `_common.md` is prepended to every worker prompt at runtime,
establishing the Coder System mission and where the role sits on the
project's team.

## Notes

- **Reviewer is separate from PM** — see [ADR 0007](../adrs/0007-reviewer-separated-from-pm.md).
  Reviewer signs off on technical quality; PM signs off on product fit.
- **Consultant vs QA vs SRE.** Consultant watches *the development process
  itself*. QA watches *test coverage and regressions*. SRE watches
  *production behavior*. Open question in design 0002.

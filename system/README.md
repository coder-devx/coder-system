# system/

Knowledge of the Coder system itself.

Everything in this folder describes the **real, current** state of Coder —
what services exist, what repos hold them, what designs they implement, what
roles operate them, and what decisions led there.

| Folder | Source of truth for |
|---|---|
| [`services/`](./services/) | Running services |
| [`repos/`](./repos/) | Code repositories |
| [`designs/`](./designs/) | Design docs (active / wip / deprecated) |
| [`adrs/`](./adrs/) | Architectural decisions (append-only) |
| [`product-specs/`](./product-specs/) | Product features & roadmap |
| [`roles/`](./roles/) | Worker roles and their permissions |
| [`integrations/`](./integrations/) | External systems Coder depends on |
| [`runbooks/`](./runbooks/) | Operational procedures |
| [`glossary.md`](./glossary.md) | Shared vocabulary |

When the system changes, update this folder. When the *shape* of the knowledge
model changes (new artifact type, new frontmatter field, …), update both this
folder **and** [`../template/`](../template/) and write an ADR.

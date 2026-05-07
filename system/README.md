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

## Unstructured archive

[`reports/`](./reports/) holds one-off analyses, audits, and dated
write-ups that don't fit any typed artifact category. Files there
have no frontmatter, no registry, and no validator coverage —
actionable findings should already be folded into the right typed
artifact (spec, ADR, runbook, role task) by the time a report lands.
See [`reports/README.md`](./reports/README.md).

## Operational manifests (root-level)

Two YAML files at this level are **not** knowledge artifacts — they
are operational manifests read by `coder-core` at runtime. They live
at `system/` root because they're system-wide (not per-artifact-type)
and their paths are part of `coder-core`'s API contract. They carry
no frontmatter and are exempt from the validator and the freshness
view.

| File | What it is |
|---|---|
| [`repos.yaml`](./repos.yaml) | Workspace contract — which repos workers may clone, branch, and push. Read by the dispatcher at task pickup. |
| [`managed-workflows.yaml`](./managed-workflows.yaml) | Fleet manifest — which managed GitHub Actions workflows are installed in every managed knowledge repo. Read by the workflow-distribution feature. |

When the system changes, update this folder. When the *shape* of the knowledge
model changes (new artifact type, new frontmatter field, …), update both this
folder **and** [`../template/`](../template/) and write an ADR.

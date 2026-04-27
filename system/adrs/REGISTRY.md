# ADR Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

| ID | Title | Status | Date | File |
|---|---|---|---|---|
| 0001 | Knowledge repo layout — system + template | accepted | 2026-04-08 | [0001-knowledge-repo-layout.md](./0001-knowledge-repo-layout.md) |
| 0002 | YAML registries with generated Markdown views | accepted | 2026-04-08 | [0002-yaml-registries.md](./0002-yaml-registries.md) |
| 0003 | Mermaid for all diagrams | accepted | 2026-04-08 | [0003-mermaid-for-diagrams.md](./0003-mermaid-for-diagrams.md) |
| 0004 | AGENTS.md as the cross-agent contract | accepted | 2026-04-08 | [0004-agents-md-cross-agent-contract.md](./0004-agents-md-cross-agent-contract.md) |
| 0005 | Multi-tenant Coder Core, project-aware in every call | accepted | 2026-04-08 | [0005-multi-tenant-coder-core.md](./0005-multi-tenant-coder-core.md) |
| 0006 | Each role-worker gets its own GCP service account | accepted | 2026-04-08 | [0006-per-role-service-accounts.md](./0006-per-role-service-accounts.md) |
| 0007 | Reviewer is a separate role from Product Manager | accepted | 2026-04-08 | [0007-reviewer-separated-from-pm.md](./0007-reviewer-separated-from-pm.md) |
| 0008 | CI validation of the knowledge repo | accepted | 2026-04-08 | [0008-ci-validation-of-knowledge-repo.md](./0008-ci-validation-of-knowledge-repo.md) |
| 0009 | Each managed project has its own GCP project and GitHub org | accepted | 2026-04-08 | [0009-per-managed-project-cloud-account-and-github-org.md](./0009-per-managed-project-cloud-account-and-github-org.md) |
| 0010 | Every repo (code and knowledge) contains an AGENTS.md | accepted | 2026-04-08 | [0010-agents-md-in-every-repo.md](./0010-agents-md-in-every-repo.md) |
| 0011 | In-process orphan reaper for Cloud Run dispatches | accepted | 2026-04-14 | [0011-orphan-dispatch-reaper.md](./0011-orphan-dispatch-reaper.md) |
| 0012 | Re-prompt only, no programmatic repair, for malformed worker JSON | accepted | 2026-04-15 | [0012-re-prompt-only-worker-output-remediation.md](./0012-re-prompt-only-worker-output-remediation.md) |
| 0013 | Transient retry lives inside the worker, not at the dispatcher | accepted | 2026-04-15 | [0013-worker-level-transient-retry.md](./0013-worker-level-transient-retry.md) |
| 0014 | Knowledge freshness derives from declared affects, not semantic similarity | accepted | 2026-04-17 | [0014-freshness-from-declared-affects.md](./0014-freshness-from-declared-affects.md) |
| 0015 | Ship gate lives in the Coder pipeline, not in GitHub branch protection | accepted | 2026-04-17 | [0015-ship-gate-in-coder-pipeline.md](./0015-ship-gate-in-coder-pipeline.md) |
| 0016 | Worker-authored PR detection via user.type == "Bot" | accepted | 2026-04-27 | [0016-bot-identity-via-user-type.md](./0016-bot-identity-via-user-type.md) |

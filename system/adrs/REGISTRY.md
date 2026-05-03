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
| 0017 | One CI fix-up dispatch per failing SHA, not one per failing check | proposed | 2026-04-28 | [0017-ci-fixup-one-per-sha.md](./0017-ci-fixup-one-per-sha.md) |
| 0018 | Skip divergent managed-workflow files by default; require --force to overwrite | proposed | 2026-04-28 | [0018-managed-workflows-divergent-file-policy.md](./0018-managed-workflows-divergent-file-policy.md) |
| 0019 | Alias-tolerance window closes on fleet completion, not a fixed deadline | proposed | 2026-04-28 | [0019-alias-tolerance-fleet-completion-gate.md](./0019-alias-tolerance-fleet-completion-gate.md) |
| 0020 | Migration runner is a worker-dispatched Cloud Run Job, not a sync API endpoint | proposed | 2026-04-28 | [0020-worker-dispatched-migration-runner.md](./0020-worker-dispatched-migration-runner.md) |
| 0021 | Field removal requires two migrations — deprecate then remove | proposed | 2026-04-28 | [0021-deprecate-then-remove-two-migrations.md](./0021-deprecate-then-remove-two-migrations.md) |
| 0022 | Structural Jaccard for pattern discovery | proposed | 2026-04-28 | [0022-structural-jaccard-for-pattern-discovery.md](./0022-structural-jaccard-for-pattern-discovery.md) |
| 0023 | Admin API + consult endpoint as the pattern surfaces | proposed | 2026-04-28 | [0023-admin-api-and-consult-endpoint-as-pattern-surfaces.md](./0023-admin-api-and-consult-endpoint-as-pattern-surfaces.md) |
| 0024 | `share_patterns` column as the cross-project read enforcement boundary | proposed | 2026-04-28 | [0024-share-patterns-column-as-enforcement-boundary.md](./0024-share-patterns-column-as-enforcement-boundary.md) |
| 0025 | `type: index` for category-rollup artifacts | accepted | 2026-05-03 | [0025-type-index-for-category-rollup-artifacts.md](./0025-type-index-for-category-rollup-artifacts.md) |

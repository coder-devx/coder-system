#!/usr/bin/env python3
"""One-shot back-fill for ADR 0029 (unified generated knowledge index).

Adds a ``summary:`` field to active spec and design artifacts that
don't already carry one. Where a summary was previously expressed in
the per-folder INDEX.md files we're retiring, we lift it verbatim;
where it wasn't, we leave the field absent so render_index.py falls
back to the artifact's ``title``. Operators can backfill the rest as
they touch individual artifacts.

Run from repo root:

    python3 scripts/backfill_summary.py

The script is idempotent — re-running it leaves files with an
existing ``summary:`` untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (kind, id) -> summary. Lifted from the descriptions in
# system/product-specs/INDEX.md and system/designs/INDEX.md as of
# 2026-05-07 (the day before the per-folder indexes were retired).
SUMMARIES: dict[tuple[str, str], str] = {
    # Product specs — categories
    ("spec", "pipeline-operations"): "How tasks flow reliably through a project's pipeline, stay observable, and recover when stalled.",
    ("spec", "worker-roles"): "The team of role-specialised agents that fill a project's pipeline.",
    ("spec", "tenancy-and-access"): "How one Coder deployment serves many projects without crossing wires and attributes every action to a real actor.",
    ("spec", "knowledge-and-admin"): "How a project's knowledge is read, written, kept current, and surfaced to operators.",
    ("spec", "delivery-and-infra"): "How code reaches production and how the system itself stays maintainable.",
    # Product specs — leaves
    ("spec", "task-orchestration"): "Task lifecycle, dispatcher, and stage transitions.",
    ("spec", "observability"): "Per-task telemetry, token costs, and pipeline metrics.",
    ("spec", "self-healing"): "Reaper for stuck tasks past timeout.",
    ("spec", "escalations"): "Three-rung on-call ladder with quiet hours.",
    ("spec", "branch-cleanup"): "Automatic GC of stale Developer feature branches.",
    ("spec", "pm-worker"): "Product Manager worker — owns specs and acceptance.",
    ("spec", "architect-worker"): "Software Architect worker — designs, ADRs, and system shape.",
    ("spec", "team-manager-worker"): "Team Manager worker — decomposes specs into developer tasks.",
    ("spec", "developer-worker"): "Developer worker — code, tests, PRs.",
    ("spec", "reviewer-worker"): "Reviewer worker — technical-quality gate before PM acceptance.",
    ("spec", "multi-tenancy"): "project_id everywhere invariant — no cross-tenant data access.",
    ("spec", "impersonation"): "Short-lived role-scoped bearer tokens for worker actions.",
    ("spec", "service-accounts"): "Per-role GCP service accounts and brokered escalations.",
    ("spec", "audit-log"): "Every mutation recorded with actor, action, before, after.",
    ("spec", "knowledge-api"): "Read-through layer over the knowledge repo with per-project cache.",
    ("spec", "knowledge-freshness"): "Automatic stale-artifact detection and rewrites.",
    ("spec", "admin-panel"): "User-facing SPA for status, debug, override.",
    ("spec", "onboarding"): "How a new project gets wired into Coder.",
    ("spec", "continuous-deployment"): "Push-to-main CD with health checks.",
    ("spec", "tenant-isolation"): "Test-suite harness for the multi-tenancy contract.",
    ("spec", "cold-start-ingestion"): "Bootstrap a new project's knowledge from existing repos.",
    ("spec", "fleet-patterns"): "Surface recurring failure patterns across managed projects.",
    ("spec", "knowledge-schema-migration"): "Migrate managed-project knowledge repos when the template schema changes.",
    ("spec", "managed-workflows"): "Distribute and version managed GitHub Actions across the fleet.",
    ("spec", "mcp-agent-interface"): "Let external agents connect, impersonate, and drive Coder via MCP.",
    ("spec", "oauth-mcp"): "OAuth 2.1 (auth-code + PKCE + DCR) for MCP clients.",
    ("spec", "secret-rotation"): "Automated, audited rotation of project secrets.",

    # Designs — categories and root
    ("design", "system-overview"): "Big-picture engineering view of the Coder system.",
    ("design", "pipeline-operations"): "How tasks flow, how stalls recover, how state surfaces.",
    ("design", "worker-roles"): "The role-typed worker subprocesses, their input contract, and how they compose.",
    ("design", "tenancy-and-access"): "Multi-tenancy enforcement and actor attribution at the engineering layer.",
    ("design", "knowledge-stack"): "How each project's knowledge repo is served, written, and kept fresh.",
    # Designs — leaves
    ("design", "worker-communication"): "Task-state machine, dispatcher protocol, and SSE streaming.",
    ("design", "observability-and-cost-tracking"): "Telemetry, cost accounting, and alerts for the running pipeline.",
    ("design", "self-healing"): "Orphan-task reaper that recovers stuck tasks.",
    ("design", "escalations"): "On-call ladder for unresolved task failures.",
    ("design", "branch-cleanup"): "Stale-branch GC across Developer feature branches.",
    ("design", "pm-worker"): "PM worker engineering view — draft, accept, ship, audit.",
    ("design", "architect-worker"): "Architect worker engineering view — design, audit, ship.",
    ("design", "team-manager-worker"): "Team Manager worker engineering view — decompose.",
    ("design", "developer-worker"): "Developer worker engineering view — implement.",
    ("design", "reviewer-worker"): "Reviewer worker engineering view — review.",
    ("design", "impersonation"): "Short-lived role-scoped tokens — the impersonation mechanism.",
    ("design", "audit-log"): "record_audit_event helper plus audit_events table.",
    ("design", "tenant-isolation"): "Cross-tenant test harness.",
    ("design", "knowledge-repo-model"): "Knowledge repo shape and the typed-artifact contract.",
    ("design", "knowledge-write-api"): "HTTP write surface for the knowledge repo.",
    ("design", "knowledge-freshness"): "Freshness audit and automatic rewrites for stale artifacts.",
    ("design", "coder-core-modular-monolith"): "Module boundaries enforced by import-linter contracts.",
    ("design", "role-prompt-knowledge-layout"): "Per-role and per-mode prompt assembly from the knowledge repo.",
    ("design", "navigation-tree-pattern"): "Hierarchical category tree pattern, generated into system/INDEX.md.",
    ("design", "admin-panel"): "Engineering shape of the admin SPA — pages, data flows, auth.",
    ("design", "continuous-deployment"): "Push-to-main CD with health-checked deploys.",
    ("design", "multi-tenancy"): "project_id propagation and enforcement across services and stores.",
    ("design", "service-accounts"): "Per-role GCP service-account brokering.",
    ("design", "onboarding"): "Engineering wiring for a new project under Coder.",
    ("design", "post-pr-ci-fix-loop"): "Bounded CI-failure fix loop after Developer PRs land.",
    ("design", "automated-secret-rotation"): "Scheduled, audited rotation of project secrets.",
    ("design", "cold-start-ingestion"): "Bootstrap a new project's knowledge from existing repos.",
    ("design", "cross-project-patterns"): "Surface recurring failure patterns across projects.",
    ("design", "graph-aware-retrieval"): "Graph-walking retrieval over knowledge cross-links.",
    ("design", "managed-repo-action-distribution"): "Distribute managed GitHub Actions across the fleet.",
    ("design", "mcp-agent-interface-design"): "MCP surface — let external agents connect, impersonate, and drive Coder.",
    ("design", "model-tier-routing"): "Route tasks to model tiers by complexity and cost.",
    ("design", "oauth-mcp-clients"): "OAuth 2.1 (auth-code + PKCE + DCR) for MCP clients.",
    ("design", "orchestrator-github-state-reconciliation"): "Reconcile pipeline state with GitHub PR state.",
    ("design", "prompt-caching-architecture"): "Prompt caching and shared-context reuse across workers.",
    ("design", "stuck-pipeline-slack-paging"): "Page Slack at the 15-minute stuck-pipeline threshold.",
    ("design", "template-schema-migration"): "Migrate managed-project knowledge repos when the template schema changes.",
    ("design", "token-budgets-and-cost-gates"): "Per-project token budgets and cost-gate enforcement.",
    ("design", "worker-dispatch-durability"): "Move worker subprocesses out of the HTTP service for durability.",
    ("design", "confidence-auto-approval"): "Confidence-scored auto-approval for low-risk worker outputs.",
    ("design", "competitive-intelligence-pipeline"): "Pipeline that surfaces competitor moves into product context.",
    ("design", "cost-regression-alerts"): "Alerts for prompt and per-task cost regressions.",
}

FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
ID_RE = re.compile(r"^id:\s*(.+?)\s*$", re.MULTILINE)
TYPE_RE = re.compile(r"^type:\s*(\w+)\s*$", re.MULTILINE)
SUMMARY_RE = re.compile(r"^summary:\s*(.*?)\s*$", re.MULTILINE)
LAST_VERIFIED_RE = re.compile(r"^(last_verified_at:\s*[^\n]*)$", re.MULTILINE)


def quote(s: str) -> str:
    """Quote a YAML scalar so colons / quotes survive a parse."""
    if any(c in s for c in [":", "#", "'", '"', "\n"]):
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s


def backfill(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return False
    fm = m.group(1)

    type_m = TYPE_RE.search(fm)
    id_m = ID_RE.search(fm)
    if not type_m or not id_m:
        return False
    artifact_type = type_m.group(1)
    artifact_id = id_m.group(1).strip().strip('"').strip("'")

    if artifact_type not in ("spec", "design", "index"):
        return False

    # Treat type:index as a category-rollup artifact — same lookup
    # key as type:spec or type:design depending on which folder it lives in.
    lookup_type = artifact_type
    if artifact_type == "index":
        if "product-specs" in path.parts:
            lookup_type = "spec"
        elif "designs" in path.parts:
            lookup_type = "design"

    summary_m = SUMMARY_RE.search(fm)
    existing = summary_m.group(1).strip() if summary_m else ""
    has_real_summary = existing not in ("", "~", "null", "None")

    if has_real_summary:
        return False

    summary = SUMMARIES.get((lookup_type, artifact_id))
    if summary is None:
        return False

    new_line = f"summary: {quote(summary)}"
    lv_m = LAST_VERIFIED_RE.search(fm)

    if summary_m:
        new_fm = SUMMARY_RE.sub(new_line, fm, count=1)
    elif lv_m:
        # Insert summary line right after last_verified_at:
        new_fm = fm[: lv_m.end()] + "\n" + new_line + fm[lv_m.end():]
    else:
        # Append to frontmatter as a fallback.
        new_fm = fm.rstrip() + "\n" + new_line + "\n"

    new_text = "---\n" + new_fm + "---\n" + text[m.end():]
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    targets: list[Path] = []
    for sub in ("product-specs/active", "designs/active"):
        folder = REPO_ROOT / "system" / sub
        if folder.is_dir():
            targets.extend(p for p in folder.glob("*.md")
                           if p.name not in ("README.md", "REGISTRY.md", "INDEX.md", "_TEMPLATE.md"))

    changed = 0
    skipped_no_summary = 0
    for path in sorted(targets):
        if backfill(path):
            changed += 1
        else:
            text = path.read_text(encoding="utf-8")
            m = FRONTMATTER_RE.match(text)
            if m:
                summary_m = SUMMARY_RE.search(m.group(1))
                if not summary_m or summary_m.group(1).strip() in ("", "~", "null", "None"):
                    skipped_no_summary += 1

    print(f"Backfilled summary on {changed} artifact(s).")
    if skipped_no_summary:
        print(f"Note: {skipped_no_summary} artifact(s) without a curated summary —")
        print("the index renderer will fall back to title for those.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

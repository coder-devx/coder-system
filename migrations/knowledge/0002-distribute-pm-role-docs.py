"""Distribute the Product Manager role docs into every project's knowledge repo.

A NEW project bootstrapped via ``coder project onboard`` after this migration
lands picks up ``system/roles/product-manager/`` automatically from
``template/system/roles/product-manager/``. This migration backfills the
same content into existing project repos that onboarded before the PM
role docs landed in ``template/``.

Idempotent: each ``FileChange`` is only emitted if the destination path is
missing in the project. Projects that already have a copy (e.g. coder-system
self-hosting) become a no-op + template_version bump.

The source content is read at migration time from the sibling
``template/system/roles/product-manager/`` tree in coder-system, so the
docs stay in one place (the template tree) — no embedded string constants
to drift out of sync.
"""

from __future__ import annotations

from pathlib import Path

from coder_core.migrations.knowledge import FileChange, KnowledgeRepoView

NUMBER = 2
SLUG = "distribute-pm-role-docs"
DESCRIPTION = (
    "Backfills system/roles/product-manager/ (role.md, INDEX.md, "
    "tasks/draft.md, tasks/accept.md, tasks/ship.md, tasks/audit.md) "
    "into projects whose knowledge repo predates the PM role docs "
    "landing in coder-system/template/. Idempotent — projects that "
    "already have these files are a no-op."
)
TARGET_VERSION = 2
ALLOW_BATCHING = False  # 6 files; well under default batch size.

# Relative path from this migration file to the canonical template/ tree.
# This file lives at coder-system/migrations/knowledge/0002-...py;
# template/ lives at coder-system/template/. Walking up two directories
# from this file's parent lands at the coder-system repo root.
_TEMPLATE_PM = (
    Path(__file__).resolve().parent.parent.parent
    / "template"
    / "system"
    / "roles"
    / "product-manager"
)

# Relative-to-project paths the migration writes. The keys are
# repo-relative paths in the project's knowledge repo; the values are
# corresponding paths under the source template tree.
_PM_DOC_LAYOUT: dict[str, Path] = {
    "system/roles/product-manager/role.md": _TEMPLATE_PM / "role.md",
    "system/roles/product-manager/INDEX.md": _TEMPLATE_PM / "INDEX.md",
    "system/roles/product-manager/tasks/draft.md": _TEMPLATE_PM / "tasks" / "draft.md",
    "system/roles/product-manager/tasks/accept.md": _TEMPLATE_PM / "tasks" / "accept.md",
    "system/roles/product-manager/tasks/ship.md": _TEMPLATE_PM / "tasks" / "ship.md",
    "system/roles/product-manager/tasks/audit.md": _TEMPLATE_PM / "tasks" / "audit.md",
}


_ROLES_REGISTRY_PATH = "system/roles/registry.yaml"

_PM_REGISTRY_ENTRY = """  - id: product-manager
    name: Product Manager
    status: defined
    owner: ro
    seniority: senior
    dir: product-manager
    file: product-manager/role.md
    tasks:
      - draft
      - accept
      - ship
      - audit
"""


def migrate(repo: KnowledgeRepoView) -> list[FileChange]:
    """For each PM role-doc path the project is missing, generate a
    FileChange that creates it with the canonical content. Also append
    the PM entry to ``system/roles/registry.yaml`` when absent — the
    validator treats the registry as source of truth, so a role file
    without a registry entry would fail validation as an orphan.
    """
    changes: list[FileChange] = []

    # 1) Role docs themselves.
    for project_path, template_path in sorted(_PM_DOC_LAYOUT.items()):
        if repo.list(project_path):
            # Already exists — idempotent skip.
            continue
        if not template_path.is_file():
            # Defensive: if the template source isn't where this migration
            # expects it, abort rather than write empty files. Surfaces as
            # error_kind='migrate_raised' so the operator sees the gap.
            raise FileNotFoundError(
                f"template source missing: {template_path} (migration "
                f"{NUMBER:04d} cannot proceed)"
            )
        content = template_path.read_text(encoding="utf-8")
        changes.append(FileChange(path=project_path, content=content))

    # 2) Roles registry. The registry is the validator's source of truth
    # for which roles exist; a role file landed without a corresponding
    # registry entry would orphan-fail validation. Append the PM entry
    # only when missing — re-running the migration on an updated repo
    # must not duplicate it. The registry is a small YAML file; a
    # naive substring check on ``id: product-manager`` is sufficient
    # because role ids are unique and the field always appears at
    # column 2 inside a list item.
    if repo.list(_ROLES_REGISTRY_PATH):
        try:
            current = repo.read(_ROLES_REGISTRY_PATH)
        except Exception:
            current = ""
        if "id: product-manager" not in current:
            new_content = current.rstrip("\n") + "\n" + _PM_REGISTRY_ENTRY
            changes.append(FileChange(path=_ROLES_REGISTRY_PATH, content=new_content))
    # If the registry file itself is missing, we don't synthesise it —
    # that's a separate bootstrap concern (a project repo without
    # ``system/roles/registry.yaml`` predates the role-registry contract
    # entirely, and the operator should surface that as an onboarding
    # gap rather than have a migration paper over it).

    return changes

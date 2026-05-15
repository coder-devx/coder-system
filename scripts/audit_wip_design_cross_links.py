#!/usr/bin/env python3
"""
Audit cross-link fields in WIP design frontmatter.

For every file under system/designs/wip/ this script checks that every
cross-link field references an ID that exists in the corresponding
registry.  Broken links are emitted as JSON lines to stdout; the script
exits 1 if any are found, 0 otherwise.

Run from repo root:
    python scripts/audit_wip_design_cross_links.py

Requires only PyYAML (already installed in CI).  See spec 0093 AC3.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML not installed. `pip install pyyaml`\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that are NOT knowledge artifacts — mirrors the constant in validate.py.
SKIP_FILENAMES = {
    "README.md", "REGISTRY.md", "ROADMAP.md", "PHASES.md", "HISTORY.md",
    "INDEX.md", "GRAPH.md", "HOWTO.md", "_TEMPLATE.md", "AGENTS.md",
    "CLAUDE.md", "STUDIO_CHARTER.md", "STUDIO_ROADMAP.md", "glossary.md",
    "_common.md", ".gitkeep",
}

# Cross-link frontmatter fields → which artifact type they reference.
# Mirrors coder_core/knowledge/schema.py:100.
CROSS_LINK_FIELDS: dict[str, str] = {
    "decided_by":        "adrs",
    "relates_to_designs": "designs",
    "implements_designs": "designs",
    "related_designs":   "designs",
    "affects_services":  "services",
    "affects_repos":     "repos",
    "implements_specs":  "specs",
    "served_by_designs": "designs",
    "related_specs":     "specs",
    "supersedes":        "adrs",
    "superseded_by":     "adrs",
    "repos":             "repos",
    "hosts_services":    "services",
}

# Maps artifact type name → subfolder under system/.
FOLDER_BY_TYPE: dict[str, str] = {
    "adrs":     "adrs",
    "designs":  "designs",
    "specs":    "product-specs",
    "services": "services",
    "repos":    "repos",
}

# Maps subfolder name → top-level YAML key in that folder's registry.yaml.
_REGISTRY_KEY: dict[str, str] = {
    "adrs":          "adrs",
    "designs":       "designs",
    "product-specs": "specs",
    "services":      "services",
    "repos":         "repos",
}


def _load_registry_ids(system_root: Path, folder: str) -> set[str]:
    """Return all `id` values from system/{folder}/registry.yaml."""
    reg_path = system_root / folder / "registry.yaml"
    if not reg_path.exists():
        return set()
    try:
        data: Any = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return set()
    key = _REGISTRY_KEY.get(folder, folder)
    entries = data.get(key) or []
    if not isinstance(entries, list):
        return set()
    return {str(e["id"]) for e in entries if isinstance(e, dict) and "id" in e}


def build_known_ids(system_root: Path) -> dict[str, set[str]]:
    """Return {type_name: set_of_known_ids} for all cross-link target types.

    For the `repos` type the set is the union of:
      - system/repos/registry.yaml  (id field)
      - system/repos.yaml           (repos[*].name — bridge per dispatcher fix)
    """
    known: dict[str, set[str]] = {}
    for type_name, folder in FOLDER_BY_TYPE.items():
        known[type_name] = _load_registry_ids(system_root, folder)

    # Bridge: repos.yaml names are also valid repo identifiers.
    repos_yaml = system_root / "repos.yaml"
    if repos_yaml.exists():
        try:
            data: Any = yaml.safe_load(repos_yaml.read_text(encoding="utf-8")) or {}
            extra = {
                r["name"]
                for r in (data.get("repos") or [])
                if isinstance(r, dict) and "name" in r
            }
            known["repos"] = known.get("repos", set()) | extra
        except yaml.YAMLError:
            pass

    return known


def parse_frontmatter(path: Path) -> dict[str, Any] | None:
    """Return the frontmatter dict, or None if unparseable."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def main() -> int:
    system_root = REPO_ROOT / "system"
    wip_dir = system_root / "designs" / "wip"

    if not wip_dir.is_dir():
        return 0

    known_ids = build_known_ids(system_root)
    broken = False

    for path in sorted(wip_dir.glob("*.md")):
        if path.name in SKIP_FILENAMES:
            continue
        fm = parse_frontmatter(path)
        if fm is None:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for field_name, target_type in CROSS_LINK_FIELDS.items():
            value = fm.get(field_name)
            if value is None:
                continue
            refs = value if isinstance(value, list) else [value]
            valid = known_ids.get(target_type, set())
            for ref in refs:
                if ref is None or ref == "" or ref == []:
                    continue
                if str(ref) not in valid:
                    print(json.dumps(
                        {
                            "field": field_name,
                            "file": rel,
                            "target_id": str(ref),
                            "target_type": target_type,
                        },
                        sort_keys=True,
                    ))
                    broken = True

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())

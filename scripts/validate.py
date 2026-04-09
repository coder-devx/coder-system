#!/usr/bin/env python3
"""
Validator for the coder-system knowledge repo.

Checks:
  1. Every knowledge MD file under system/ and template/ has parseable
     YAML frontmatter with the required fields for its artifact type.
  2. Every registry.yaml parses.
  3. Every file in an artifact folder is listed in that folder's
     registry.yaml, and every registry entry points at a real file.
  4. Cross-link fields reference IDs that exist.

Run from repo root:
    python3 scripts/validate.py

Exits non-zero on any failure. See ADR 0008.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML not installed. `pip install pyyaml`\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that are NOT knowledge artifacts even though they're MD.
SKIP_FILENAMES = {"README.md", "REGISTRY.md", "ROADMAP.md", "_TEMPLATE.md", "AGENTS.md", "CLAUDE.md", "glossary.md"}

# Required frontmatter fields per artifact type.
REQUIRED_FIELDS: dict[str, set[str]] = {
    "service":     {"id", "name", "type", "status", "owner"},
    "repo":        {"id", "name", "type", "status", "owner", "github"},
    "design":      {"id", "title", "type", "status", "owner", "created"},
    "adr":         {"id", "title", "type", "status", "date", "deciders"},
    "spec":        {"id", "title", "type", "status", "owner", "created"},
    "role":        {"id", "name", "type", "status", "owner"},
    "integration": {"id", "name", "type", "status", "owner", "auth"},
    "runbook":     {"id", "title", "type", "status", "owner", "created"},
}

# Folder → registry key mapping (the YAML top-level list under registry.yaml).
REGISTRY_KEYS = {
    "services":      "services",
    "repos":         "repos",
    "designs":       "designs",
    "adrs":          "adrs",
    "product-specs": "specs",
    "roles":         "roles",
    "integrations":  "integrations",
}

# Cross-link fields → which registry's IDs they reference.
CROSS_LINKS = {
    "decided_by":          "adrs",
    "relates_to_designs":  "designs",
    "implements_designs":  "designs",
    "related_designs":     "designs",
    "affects_services":    "services",
    "affects_repos":       "repos",
    "implements_specs":    "specs",
    "served_by_designs":   "designs",
    "related_specs":       "specs",
    "supersedes":          "adrs",
    "superseded_by":       "adrs",
    "repos":               "repos",
    "hosts_services":      "services",
}

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def parse_frontmatter(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        err(f"{path}: missing frontmatter")
        return None
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        err(f"{path}: unterminated frontmatter")
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as e:
        err(f"{path}: frontmatter YAML error: {e}")
        return None
    if not isinstance(data, dict):
        err(f"{path}: frontmatter must be a YAML mapping")
        return None
    return data


def load_registry(folder: Path) -> dict[str, dict[str, Any]]:
    """Return {id: entry} for a folder's registry.yaml. Empty if missing."""
    reg_path = folder / "registry.yaml"
    if not reg_path.exists():
        return {}
    try:
        data = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        err(f"{reg_path}: YAML error: {e}")
        return {}
    key = REGISTRY_KEYS.get(folder.name)
    if key is None:
        return {}
    entries = data.get(key) or []
    if not isinstance(entries, list):
        err(f"{reg_path}: '{key}' must be a list")
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or "id" not in entry:
            err(f"{reg_path}: entry missing 'id': {entry!r}")
            continue
        out[str(entry["id"])] = entry
    return out


def collect_registries(root: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """Return {folder_name: {id: entry}} for every artifact folder under root."""
    registries: dict[str, dict[str, dict[str, Any]]] = {}
    for name in REGISTRY_KEYS:
        folder = root / name
        if folder.is_dir():
            registries[name] = load_registry(folder)
        else:
            registries[name] = {}
    return registries


def iter_md_files(root: Path):
    for path in root.rglob("*.md"):
        if path.name in SKIP_FILENAMES:
            continue
        yield path


def validate_section(section_root: Path, section_label: str) -> None:
    """Validate either system/ or template/."""
    if not section_root.is_dir():
        return

    registries = collect_registries(section_root)
    # Build {registry_key: set of all known ids} for cross-link checks.
    # Note: CROSS_LINKS target values are registry *keys* (e.g. "specs"), not
    # folder names (e.g. "product-specs"), so key this dict by the YAML key
    # via REGISTRY_KEYS rather than by folder name.
    known_ids = {
        REGISTRY_KEYS[name]: set(entries.keys())
        for name, entries in registries.items()
    }

    # Track files referenced by registries so we can detect orphans.
    referenced: dict[str, set[Path]] = {name: set() for name in REGISTRY_KEYS}
    for folder_name, entries in registries.items():
        folder = section_root / folder_name
        for entry_id, entry in entries.items():
            file_field = entry.get("file")
            if not file_field:
                # designs/specs may live in active/wip/deprecated subfolders;
                # registry should set 'file' relative to the folder.
                continue
            target = folder / file_field
            if not target.exists():
                err(f"{folder/'registry.yaml'}: entry '{entry_id}' points at missing file: {file_field}")
            else:
                referenced[folder_name].add(target.resolve())

    # Walk every MD file and validate frontmatter + cross-links.
    for md in iter_md_files(section_root):
        data = parse_frontmatter(md)
        if data is None:
            continue
        artifact_type = data.get("type")
        if artifact_type not in REQUIRED_FIELDS:
            err(f"{md}: unknown or missing 'type' (got {artifact_type!r})")
            continue
        missing = REQUIRED_FIELDS[artifact_type] - set(data.keys())
        if missing:
            err(f"{md}: missing required frontmatter fields: {sorted(missing)}")

        # Cross-link checks.
        for field, target_registry in CROSS_LINKS.items():
            if field not in data or data[field] is None:
                continue
            value = data[field]
            ids = value if isinstance(value, list) else [value]
            for ref in ids:
                if ref is None or ref == []:
                    continue
                if str(ref) not in known_ids.get(target_registry, set()):
                    err(f"{md}: {field} references unknown {target_registry} id: {ref!r}")

    # Orphan check: files in artifact folders not listed in their registry.
    for folder_name in REGISTRY_KEYS:
        folder = section_root / folder_name
        if not folder.is_dir():
            continue
        for md in iter_md_files(folder):
            if md.resolve() in referenced[folder_name]:
                continue
            # Subfolders (active/wip/deprecated) — only flag if registry is non-empty.
            # Empty registries are normal in template/.
            if registries[folder_name]:
                err(f"{md}: not listed in {folder/'registry.yaml'}")


def main() -> int:
    validate_section(REPO_ROOT / "system",   "system")
    validate_section(REPO_ROOT / "template", "template")

    if errors:
        sys.stderr.write(f"\n{len(errors)} validation error(s):\n")
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        return 1

    print("OK — knowledge repo is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

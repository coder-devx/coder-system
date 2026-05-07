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
  5. AGENTS.md rule 6: designs/active and product-specs/active filenames
     are subject-slugs, not numbered.
  6. Duplicate-draft detector: two wip/ files with the same normalized
     title are almost certainly the same problem in fragments — pick
     one canonical and deprecate the rest.
  7. REGISTRY.md drift detector: designs/REGISTRY.md and
     product-specs/REGISTRY.md must match what scripts/render_registry.py
     would produce from registry.yaml.

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
# ``_common.md`` is the worker-prompt preamble (design 0057); not a
# stand-alone artifact — its content is prepended to every worker
# system prompt at runtime.
# ``INDEX.md`` is the curated navigation entry point per artifact-type
# folder (design 0062); narrative view over the registry, not a
# knowledge artifact in its own right.
SKIP_FILENAMES = {"README.md", "REGISTRY.md", "ROADMAP.md", "PHASES.md", "HISTORY.md", "INDEX.md", "GRAPH.md", "_TEMPLATE.md", "AGENTS.md", "CLAUDE.md", "glossary.md", "_common.md"}

# Required frontmatter fields per artifact type. Spec 0043 adds
# ``last_verified_at`` to every non-ADR type — ADRs are append-only
# and their freshness is binary (superseded or not).
REQUIRED_FIELDS: dict[str, set[str]] = {
    "service":     {"id", "name", "type", "status", "owner", "last_verified_at"},
    "repo":        {"id", "name", "type", "status", "owner", "github", "last_verified_at"},
    "design":      {"id", "title", "type", "status", "owner", "created", "last_verified_at", "parent"},
    "adr":         {"id", "title", "type", "status", "date", "deciders"},
    "spec":        {"id", "title", "type", "status", "owner", "created", "last_verified_at", "parent"},
    # ADR 0025: category-rollup artifacts use ``type: index``. Same
    # frontmatter shape as a spec; the body has different required
    # sections enforced below.
    "index":       {"id", "title", "type", "status", "owner", "created", "last_verified_at", "parent"},
    "role":        {"id", "name", "type", "status", "owner", "last_verified_at"},
    "integration": {"id", "name", "type", "status", "owner", "auth", "last_verified_at"},
    "runbook":     {"id", "title", "type", "status", "owner", "created", "last_verified_at"},
}

# Required body sections per type. Kept narrow on purpose — only
# enforced where deviation has bitten us. ``index`` files are the
# first to use this; everything else stays unconstrained at the body
# level (the template carries the convention).
REQUIRED_SECTIONS: dict[str, list[str]] = {
    "index": [
        "## What this category covers",
        "## Components",
        "## Cross-cutting concerns",
        "## Links",
    ],
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
    "runbooks":      "runbooks",
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


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str] | None:
    """Return (frontmatter, body) or None on malformed input."""
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
    body = text[end + len("\n---\n"):]
    return data, body


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
        # Per design 0057: ``roles/<role>/tasks/<mode>.md`` files are
        # per-mode prompt contracts, not stand-alone knowledge artifacts.
        # Their content is fetched directly by the dispatcher and
        # concatenated into the worker's system prompt.
        if path.parent.name == "tasks" and path.parent.parent.parent.name == "roles":
            continue
        # ``reports/`` is the unstructured archive for time-bound
        # analyses (see system/reports/README.md). Files there carry
        # no frontmatter and intentionally bypass validation.
        if "reports" in path.relative_to(root).parts:
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
        parsed = parse_frontmatter(md)
        if parsed is None:
            continue
        data, body = parsed
        artifact_type = data.get("type")
        if artifact_type not in REQUIRED_FIELDS:
            err(f"{md}: unknown or missing 'type' (got {artifact_type!r})")
            continue
        missing = REQUIRED_FIELDS[artifact_type] - set(data.keys())
        if missing:
            err(f"{md}: missing required frontmatter fields: {sorted(missing)}")

        # Body-level structure check for types that have required
        # sections. Match on the H2 heading verbatim (the template
        # spells them out in full).
        for required_heading in REQUIRED_SECTIONS.get(artifact_type, []):
            if required_heading not in body:
                err(f"{md}: missing required section: {required_heading!r}")

        # Spec 0043: ``last_verified_at`` must be a parseable date
        # (YYYY-MM-DD) and cannot be in the future. ADRs are exempt —
        # their freshness is binary (superseded or not).
        if artifact_type != "adr" and "last_verified_at" in data:
            import datetime as _dt

            raw = data["last_verified_at"]
            parsed: _dt.date | None = None
            if isinstance(raw, _dt.date):
                parsed = raw
            elif isinstance(raw, str):
                try:
                    parsed = _dt.date.fromisoformat(raw)
                except ValueError:
                    err(f"{md}: last_verified_at is not a YYYY-MM-DD date: {raw!r}")
            else:
                err(f"{md}: last_verified_at must be a date string, got {type(raw).__name__}")
            if parsed is not None and parsed > _dt.date.today():
                err(f"{md}: last_verified_at is in the future: {parsed.isoformat()}")

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


def check_active_not_numbered(section_root: Path) -> None:
    """AGENTS.md rule 6: active designs and specs are subject-named.
    A filename like ``active/0051-foo.md`` is a lifecycle violation —
    it should be ``active/foo.md``.
    """
    for folder_name in ("designs", "product-specs"):
        active = section_root / folder_name / "active"
        if not active.is_dir():
            continue
        for md in active.glob("*.md"):
            if md.name in SKIP_FILENAMES:
                continue
            stem = md.stem
            if len(stem) >= 5 and stem[:4].isdigit() and stem[4] == "-":
                err(f"{md}: numbered filename in active/ violates AGENTS.md rule 6 — rename to subject-slug")


def check_wip_duplicate_titles(section_root: Path) -> None:
    """Catch the 'multiple drafts of the same problem' failure mode.

    Two wip/ files whose titles normalize to the same string are
    almost certainly the same problem written twice. Deprecate one
    and link from the other.
    """
    import re

    def normalize(t: str) -> str:
        return re.sub(r"[\W_]+", " ", t.lower()).strip()

    for folder_name in ("designs", "product-specs"):
        wip = section_root / folder_name / "wip"
        if not wip.is_dir():
            continue
        seen: dict[str, Path] = {}
        for md in sorted(wip.glob("*.md")):
            if md.name in SKIP_FILENAMES:
                continue
            parsed = parse_frontmatter(md)
            if parsed is None:
                continue
            data, _body = parsed
            title = data.get("title")
            if not isinstance(title, str):
                continue
            norm = normalize(title)
            if not norm:
                continue
            if norm in seen:
                err(
                    f"{md}: duplicate title matches {seen[norm].name} — "
                    "deprecate one draft and link from the other"
                )
            else:
                seen[norm] = md


def check_registry_md_synced() -> None:
    """REGISTRY.md must match what scripts/render_registry.py produces.
    Catches drift between the YAML source of truth and the human view.
    """
    import subprocess

    renderer = REPO_ROOT / "scripts" / "render_registry.py"
    if not renderer.exists():
        return  # renderer is optional infrastructure
    result = subprocess.run(
        [sys.executable, str(renderer), "--check"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("drift:"):
            target = line[len("drift:"):].strip()
            err(f"{target}: out of sync with registry.yaml — run scripts/render_registry.py")


def check_index_md_synced() -> None:
    """system/INDEX.md must match what scripts/render_index.py produces.
    Same drift-check pattern as REGISTRY.md (ADR 0029).
    """
    import subprocess

    renderer = REPO_ROOT / "scripts" / "render_index.py"
    if not renderer.exists():
        return
    result = subprocess.run(
        [sys.executable, str(renderer), "--check"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("drift:"):
            target = line[len("drift:"):].strip()
            err(f"{target}: out of sync with parent: / summary: frontmatter — run scripts/render_index.py")


def check_graph_md_synced() -> None:
    """system/GRAPH.md must match what scripts/render_graph.py produces."""
    import subprocess

    renderer = REPO_ROOT / "scripts" / "render_graph.py"
    if not renderer.exists():
        return
    result = subprocess.run(
        [sys.executable, str(renderer), "--check"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("drift:"):
            target = line[len("drift:"):].strip()
            err(f"{target}: out of sync with cross-link frontmatter — run scripts/render_graph.py")


def check_shared_id_parents_match(section_root: Path) -> None:
    """Per ADR 0029: when a spec and design share an id (the shared-id
    pool from ADR 0026 — e.g. ``pipeline-operations`` exists in both
    folders), their ``parent:`` values must agree. Otherwise the
    unified index can't decide where to put the node.
    """
    spec_parents: dict[str, tuple[Path, str | None]] = {}
    design_parents: dict[str, tuple[Path, str | None]] = {}

    for folder, sink in (("product-specs", spec_parents),
                         ("designs", design_parents)):
        active = section_root / folder / "active"
        if not active.is_dir():
            continue
        for md in active.glob("*.md"):
            if md.name in SKIP_FILENAMES:
                continue
            parsed = parse_frontmatter(md)
            if parsed is None:
                continue
            data, _ = parsed
            artifact_id = data.get("id")
            if not isinstance(artifact_id, str):
                continue
            raw = data.get("parent")
            if raw is None or (isinstance(raw, str) and raw.strip() in ("", "~", "null")):
                parent: str | None = None
            elif isinstance(raw, str):
                parent = raw.strip()
            else:
                parent = None
            sink[artifact_id] = (md, parent)

    for artifact_id in sorted(set(spec_parents) & set(design_parents)):
        sp_path, sp_parent = spec_parents[artifact_id]
        dp_path, dp_parent = design_parents[artifact_id]
        if sp_parent != dp_parent:
            err(
                f"{dp_path}: parent={dp_parent!r} disagrees with "
                f"{sp_path.name}'s parent={sp_parent!r} — shared-id "
                "spec+design pairs must have matching parents (ADR 0029)"
            )


def main() -> int:
    validate_section(REPO_ROOT / "system",   "system")
    validate_section(REPO_ROOT / "template", "template")
    for root in (REPO_ROOT / "system", REPO_ROOT / "template"):
        if root.is_dir():
            check_active_not_numbered(root)
            check_wip_duplicate_titles(root)
            check_shared_id_parents_match(root)
    check_registry_md_synced()
    check_index_md_synced()
    check_graph_md_synced()

    if errors:
        sys.stderr.write(f"\n{len(errors)} validation error(s):\n")
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        return 1

    print("OK — knowledge repo is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

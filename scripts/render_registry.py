#!/usr/bin/env python3
"""
Generate REGISTRY.md from registry.yaml for every artifact-type folder
that has both. The YAML is the source of truth (AGENTS.md rule 2);
this renderer keeps the human-readable view consistent with it.

Run from repo root:

    python3 scripts/render_registry.py            # render all folders
    python3 scripts/render_registry.py --check    # exit 1 on drift, no writes

The renderer is idempotent. Hand edits to REGISTRY.md will be lost on
the next run — edit registry.yaml instead.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML not installed. `pip install pyyaml`\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM = REPO_ROOT / "system"
TEMPLATE = REPO_ROOT / "template"

# Folders this renderer owns. The remaining artifact-type folders
# (services/, repos/, adrs/, roles/, integrations/, runbooks/) have
# bespoke REGISTRY.md formats with extra columns or notes — they stay
# hand-edited until someone takes the time to fold them in here.
FOLDERS = ("designs", "product-specs")


def _norm(s: Any) -> str:
    return str(s).strip("'\"") if s is not None else ""


def _resolve_link(root: Path, base_folder: str, target_id: str) -> str | None:
    """Find the path to a referenced artifact by id, returning a relative
    href from the rendered REGISTRY.md (which sits at base_folder/REGISTRY.md).
    """
    target = _norm(target_id)
    if not target:
        return None
    # numeric IDs may live in wip / deprecated / active (rare for active)
    if target.isdigit() and len(target) == 4:
        for sub in ("wip", "deprecated", "active"):
            for f in (root / base_folder / sub).glob(f"{target}-*.md"):
                return f"./{sub}/{f.name}"
        return None
    # subject slug: active or deprecated
    for sub in ("active", "deprecated"):
        f = root / base_folder / sub / f"{target}.md"
        if f.exists():
            return f"./{sub}/{f.name}"
    return None


def _cross_link(root: Path, kind: str, target_id: str) -> str:
    """Render a markdown link to an artifact in another folder, or fall
    back to the bare id if it can't be resolved."""
    target = _norm(target_id)
    if not target:
        return "—"
    base = {
        "design":  "designs",
        "spec":    "product-specs",
        "adr":     "adrs",
        "service": "services",
        "repo":    "repos",
    }[kind]
    href = _resolve_link(root, base, target)
    if href is None:
        return target
    # rewrite href as a sibling-folder reference
    return f"[{target}](../{base}/{href[2:]})"


def _adr_link(root: Path, aid: Any) -> str:
    aid = _norm(aid).zfill(4)
    for f in (root / "adrs").glob(f"{aid}-*.md"):
        return f"[{aid}](../adrs/{f.name})"
    return aid


def _row(cells: Iterable[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def render_designs(root: Path) -> str:
    data = yaml.safe_load((root / "designs" / "registry.yaml").read_text())
    items = data.get("designs", [])
    active, wip, dep = [], [], []
    for d in items:
        did = _norm(d["id"])
        title = d["title"]
        owner = d.get("owner", "ro")
        impl = d.get("implements_specs") or []
        impl_md = ", ".join(_cross_link(root, "spec", x) for x in impl) if impl else "—"
        decided = d.get("decided_by") or []
        decided_md = ", ".join(_adr_link(root, x) for x in decided) if decided else "—"
        href = f"./{d['file']}"
        if d.get("folder") == "active":
            slug = Path(d["file"]).stem
            active.append((slug, _row([f"[{slug}]({href})", title, owner, impl_md, decided_md])))
        elif d.get("folder") == "wip":
            wip.append((did, _row([f"[{did}]({href})", title, owner, impl_md, decided_md])))
        else:
            dep.append((did, _row([f"[{did}]({href})", title, "—", "—"])))
    active.sort(); wip.sort(); dep.sort()
    out: list[str] = []
    out.append("# Designs Registry\n")
    out.append("> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.\n")
    out.append("## Active — subject-named logical components\n")
    out.append("Logical components of the Coder system as it exists today.\n")
    out.append(_row(["Slug", "Title", "Owner", "Implements specs", "Decided by"]))
    out.append("|---|---|---|---|---|")
    out.extend(r for _, r in active)
    out.append("\n## WIP — numbered, roadmap-aligned\n")
    out.append(_row(["ID", "Title", "Owner", "Implements specs", "Decided by"]))
    out.append("|---|---|---|---|---|")
    out.extend(r for _, r in wip)
    out.append("\n## Deprecated\n")
    if dep:
        out.append(_row(["ID", "Title", "Deprecated at", "Reason"]))
        out.append("|---|---|---|---|")
        out.extend(r for _, r in dep)
    else:
        out.append("_None yet._")
    out.append("")
    return "\n".join(out)


def render_specs(root: Path) -> str:
    data = yaml.safe_load((root / "product-specs" / "registry.yaml").read_text())
    items = data.get("specs", [])
    active, wip, dep = [], [], []
    for s in items:
        sid = _norm(s["id"])
        title = s["title"]
        owner = s.get("owner", "ro")
        served = s.get("served_by_designs") or []
        served_md = ", ".join(_cross_link(root, "design", x) for x in served) if served else "—"
        href = f"./{s['file']}"
        if s.get("folder") == "active":
            slug = Path(s["file"]).stem
            active.append((slug, _row([f"[{slug}]({href})", title, owner, served_md])))
        elif s.get("folder") == "wip":
            wip.append((sid, _row([f"[{sid}]({href})", title, owner, served_md])))
        else:
            dep.append((sid, _row([f"[{sid}]({href})", title, "—"])))
    active.sort(); wip.sort(); dep.sort()
    out: list[str] = []
    out.append("# Product Specs Registry\n")
    out.append("> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.\n")
    out.append("## Active — subject-named logical components\n")
    out.append("Components of the Coder system as it exists today. Ship history lives")
    out.append("in each component's `## Evolution` section and in git.\n")
    out.append(_row(["Slug", "Title", "Owner", "Served by designs"]))
    out.append("|---|---|---|---|")
    out.extend(r for _, r in active)
    out.append("\n## WIP — numbered, roadmap-aligned\n")
    out.append(_row(["ID", "Title", "Owner", "Served by designs"]))
    out.append("|---|---|---|---|")
    out.extend(r for _, r in wip)
    out.append("\n## Deprecated\n")
    if dep:
        out.append(_row(["ID", "Title", "Reason"]))
        out.append("|---|---|---|")
        out.extend(r for _, r in dep)
    else:
        out.append("_None yet._")
    out.append("")
    return "\n".join(out)


def render_one(root: Path, folder: str) -> str | None:
    if folder == "designs":
        return render_designs(root)
    if folder == "product-specs":
        return render_specs(root)
    return None


def render_all(check: bool = False) -> int:
    drift = 0
    for root in (SYSTEM, TEMPLATE):
        if not root.exists():
            continue
        for folder in FOLDERS:
            if not (root / folder).is_dir():
                continue
            if not (root / folder / "registry.yaml").exists():
                continue
            rendered = render_one(root, folder)
            if not rendered:
                continue
            target = root / folder / "REGISTRY.md"
            current = target.read_text() if target.exists() else ""
            if rendered != current:
                if check:
                    print(f"drift: {target.relative_to(REPO_ROOT)}")
                    drift += 1
                else:
                    target.write_text(rendered)
                    print(f"wrote: {target.relative_to(REPO_ROOT)}")
    if check and drift:
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 1 on any drift; do not write")
    args = ap.parse_args()
    return render_all(check=args.check)


if __name__ == "__main__":
    sys.exit(main())

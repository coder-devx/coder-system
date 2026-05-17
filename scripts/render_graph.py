#!/usr/bin/env python3
"""Generate ``system/GRAPH.md`` — the cross-link graph view.

While ``system/INDEX.md`` (ADR 0029) renders the parent-child taxonomy,
the GRAPH view shows the *non-tree* relationships: which designs serve
which specs, which ADRs decided which designs, which active artifacts
share ``related_*`` cross-links. The graph reveals dependency and
overlap patterns the tree can't.

Generated, drift-checked. Edit the underlying frontmatter (the
``served_by_designs`` / ``implements_specs`` / ``decided_by`` /
``related_*`` fields on each artifact) — never edit the rendered file.

Run from repo root:

    python3 scripts/render_graph.py            # write system/GRAPH.md
    python3 scripts/render_graph.py --check    # exit 1 on drift
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML not installed. `pip install pyyaml`\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM = REPO_ROOT / "system"
GRAPH_PATH = SYSTEM / "GRAPH.md"

# Categories to bucket per-category sub-graphs by. The five product
# categories cover most surface; a small "Other" bucket catches the
# rest (system-overview meta, orphans).
CATEGORY_ORDER = (
    "pipeline-operations",
    "worker-roles",
    "tenancy-and-access",
    "knowledge-and-admin",
    "delivery-and-infra",
)


def parse_frontmatter(path: Path) -> dict[str, Any] | None:
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


def _norm(v: Any) -> list[str]:
    """Normalise a frontmatter list-or-scalar field into a list of strings."""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    if isinstance(v, str):
        s = v.strip()
        return [s] if s and s not in ("~", "null", "[]") else []
    return []


def collect() -> dict[str, dict[str, Any]]:
    """Return {(folder, id): {title, parent, summary, edges...}} for active artifacts."""
    out: dict[str, dict[str, Any]] = {}
    for folder in ("product-specs", "designs"):
        base = SYSTEM / folder / "active"
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            if path.name in ("README.md", "REGISTRY.md", "INDEX.md", "_TEMPLATE.md"):
                continue
            fm = parse_frontmatter(path)
            if fm is None:
                continue
            if fm.get("status") != "active":
                continue
            artifact_id = str(fm.get("id"))
            kind = "spec" if folder == "product-specs" else "design"
            key = f"{kind}:{artifact_id}"
            parent_raw = fm.get("parent")
            if isinstance(parent_raw, str) and parent_raw.strip() not in ("", "~", "null"):
                parent = parent_raw.strip()
            else:
                parent = None
            out[key] = {
                "id": artifact_id,
                "kind": kind,
                "title": str(fm.get("title") or artifact_id),
                "summary": str(fm.get("summary") or "").strip() or None,
                "parent": parent,
                "served_by_designs": _norm(fm.get("served_by_designs")),
                "implements_specs": _norm(fm.get("implements_specs")),
                "decided_by": _norm(fm.get("decided_by")),
                "related_designs": _norm(fm.get("related_designs")),
                "related_specs": _norm(fm.get("related_specs")),
            }
    return out


def category_for(node_key: str, nodes: dict[str, dict[str, Any]]) -> str:
    """Walk parent chain to a top-level ancestor; return that ancestor's id."""
    seen: set[str] = set()
    key = node_key
    while True:
        if key in seen:
            return "other"
        seen.add(key)
        n = nodes.get(key)
        if n is None or n["parent"] is None:
            return n["id"] if n else "other"
        # parent is a bare id; resolve to the spec or design version
        parent = n["parent"]
        spec_key = f"spec:{parent}"
        design_key = f"design:{parent}"
        if spec_key in nodes:
            key = spec_key
        elif design_key in nodes:
            key = design_key
        else:
            return parent  # parent isn't in active — bucket by the bare id


def render_mermaid_for_category(
    category: str,
    member_keys: list[str],
    nodes: dict[str, dict[str, Any]],
) -> list[str]:
    lines: list[str] = ["```mermaid", "flowchart LR"]

    # Node aliases (a-Z + digits, must start with letter for Mermaid)
    alias: dict[str, str] = {}
    for i, key in enumerate(sorted(member_keys)):
        alias[key] = f"n{i:03d}"

    # Emit nodes with kind tag
    for key in sorted(member_keys):
        n = nodes[key]
        label = f"{n['kind']}<br/>{n['id']}"
        shape_open, shape_close = ("[", "]") if n["kind"] == "spec" else ("(", ")")
        lines.append(f"  {alias[key]}{shape_open}\"{label}\"{shape_close}")

    # Edges: served_by + decided_by + related_*
    members_set = set(member_keys)

    def _has(other_key: str) -> bool:
        return other_key in members_set

    for key in sorted(member_keys):
        n = nodes[key]
        if n["kind"] == "spec":
            for design_id in n["served_by_designs"]:
                target = f"design:{design_id}"
                if _has(target):
                    lines.append(f"  {alias[key]} -->|served by| {alias[target]}")
            for spec_id in n["related_specs"]:
                target = f"spec:{spec_id}"
                if _has(target) and target != key:
                    lines.append(f"  {alias[key]} -.->|related| {alias[target]}")
        else:  # design
            for spec_id in n["implements_specs"]:
                target = f"spec:{spec_id}"
                if _has(target):
                    lines.append(f"  {alias[target]} -->|served by| {alias[key]}")
            for design_id in n["related_designs"]:
                target = f"design:{design_id}"
                if _has(target) and target != key:
                    lines.append(f"  {alias[key]} -.->|related| {alias[target]}")

    lines.append("```")
    return lines


def render_adr_table(nodes: dict[str, dict[str, Any]]) -> list[str]:
    """ADR fan-out: which artifacts cite each ADR."""
    by_adr: dict[str, list[str]] = defaultdict(list)
    for key, n in nodes.items():
        for adr_id in n["decided_by"]:
            by_adr[adr_id].append(key)
    if not by_adr:
        return []
    lines = [
        "## ADR fan-out",
        "",
        "Which active artifacts cite each ADR via `decided_by`. Use this",
        "to spot ADRs whose decisions ripple into multiple components.",
        "",
        "| ADR | Cited by |",
        "|---|---|",
    ]
    for adr_id in sorted(by_adr.keys()):
        cite_links = ", ".join(
            f"[{nodes[k]['kind']}/{nodes[k]['id']}]"
            f"(./{('product-specs' if nodes[k]['kind'] == 'spec' else 'designs')}"
            f"/active/{nodes[k]['id']}.md)"
            for k in sorted(by_adr[adr_id])
        )
        lines.append(f"| [{adr_id}](./adrs/{adr_id}-*.md) | {cite_links} |")
    lines.append("")
    return lines


def render(nodes: dict[str, dict[str, Any]]) -> str:
    # Bucket nodes by category
    buckets: dict[str, list[str]] = defaultdict(list)
    for key in nodes:
        cat = category_for(key, nodes)
        buckets[cat].append(key)

    lines: list[str] = []
    lines.append("# Coder system — cross-link graph")
    lines.append("")
    lines.append(
        "> Generated from `served_by_designs`, `implements_specs`, "
        "`decided_by`, and `related_*` frontmatter on each active "
        "artifact. Hand edits are lost on the next "
        "`scripts/render_graph.py` run. The taxonomy tree lives in "
        "[`INDEX.md`](./INDEX.md); this file shows the **non-tree** "
        "relationships."
    )
    lines.append("")
    lines.append(
        "Mermaid notation: `[spec]` rectangle, `(design)` rounded. "
        "Solid `-->` is `served_by_designs` / `implements_specs` "
        "(the spec/design pair that realises a contract). "
        "Dashed `-.->` is `related_*` (sibling cross-link)."
    )
    lines.append("")

    for cat in CATEGORY_ORDER:
        members = buckets.get(cat, [])
        if not members:
            continue
        cat_node = nodes.get(f"spec:{cat}") or nodes.get(f"design:{cat}")
        title = cat_node["title"] if cat_node else cat
        lines.append(f"## {title}")
        lines.append("")
        lines.extend(render_mermaid_for_category(cat, members, nodes))
        lines.append("")

    leftover = sorted(b for b in buckets if b not in CATEGORY_ORDER)
    if leftover:
        lines.append("## Other")
        lines.append("")
        for cat in leftover:
            members = buckets[cat]
            cat_node = nodes.get(f"spec:{cat}") or nodes.get(f"design:{cat}")
            title = cat_node["title"] if cat_node else cat
            lines.append(f"### {title}")
            lines.append("")
            lines.extend(render_mermaid_for_category(cat, members, nodes))
            lines.append("")

    lines.extend(render_adr_table(nodes))

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="Exit 1 on drift; do not write.")
    args = ap.parse_args()

    nodes = collect()
    rendered = render(nodes)

    if args.check:
        existing = GRAPH_PATH.read_text(encoding="utf-8") if GRAPH_PATH.exists() else ""
        if existing != rendered:
            print(f"drift: {GRAPH_PATH.relative_to(REPO_ROOT)}")
            return 1
        return 0

    GRAPH_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote: {GRAPH_PATH.relative_to(REPO_ROOT)} "
          f"({len(nodes)} active artifacts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

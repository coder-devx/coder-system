#!/usr/bin/env python3
"""Generate ``system/INDEX.md`` from spec + design registries.

The unified knowledge index is the single navigation entry point for
product specs and designs (ADR 0029). It is generated — same lifecycle
as REGISTRY.md — from:

- ``system/product-specs/registry.yaml`` and
  ``system/designs/registry.yaml`` (the artifact set).
- Each artifact's frontmatter ``parent:``, ``summary:``, ``status:``,
  and ``title:`` fields.

Active artifacts only. WIPs are listed in ``registry.yaml`` and
tracked in ``ROADMAP.md``; including them in the navigation tree
would conflate roadmap detail with current-state grounding.

Run from repo root:

    python3 scripts/render_index.py            # write system/INDEX.md
    python3 scripts/render_index.py --check    # exit 1 on drift, no writes

Hand edits to ``system/INDEX.md`` are lost on the next run. Edit the
underlying frontmatter (``summary``, ``parent``, ``title``) instead.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML not installed. `pip install pyyaml`\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM = REPO_ROOT / "system"
INDEX_PATH = SYSTEM / "INDEX.md"

# Top-level ordering. Alphabetical is the deterministic default; this
# list bumps the five user-facing category ids to the front in a
# canonical order that reads better than alphabetical for new readers.
# Top-level entries not listed here fall through to alphabetical at
# the bottom of the index.
TOP_LEVEL_ORDER = (
    "system-overview",
    "pipeline-operations",
    "worker-roles",
    "tenancy-and-access",
    "knowledge-and-admin",
    "delivery-and-infra",
)

# Folder name → artifact-kind label used in the rendered output.
KIND_LABEL = {"product-specs": "spec", "designs": "design"}
# Folder name → relative path under system/ used when linking.
FOLDER_REL = {"product-specs": "product-specs", "designs": "designs"}


@dataclass
class Artifact:
    artifact_id: str
    folder: str           # "product-specs" | "designs"
    file_rel: str         # relative path under the folder, e.g. active/foo.md
    title: str
    summary: str | None
    parent: str | None
    status: str
    type: str             # "spec" | "design" | "index"

    @property
    def kind(self) -> str:
        # type:index lives in either folder; report kind by folder for
        # rendering, since spec-vs-design is the user-facing distinction.
        return KIND_LABEL[self.folder]

    @property
    def link(self) -> str:
        return f"./{FOLDER_REL[self.folder]}/{self.file_rel}"

    @property
    def display(self) -> str:
        return self.summary if self.summary else self.title

    @property
    def node_key(self) -> tuple[str, str]:
        """A spec and a design with the same id share a category node."""
        return (self.artifact_id, self.kind)


@dataclass
class Node:
    """A category node: 0–1 spec + 0–1 design + ordered children."""
    artifact_id: str
    spec: Artifact | None = None
    design: Artifact | None = None
    children: list["Node"] = field(default_factory=list)

    @property
    def title(self) -> str:
        # Prefer the spec's title — it tends to read more product-y.
        if self.spec:
            return self.spec.title
        if self.design:
            return self.design.title
        return self.artifact_id

    @property
    def summary(self) -> str | None:
        if self.spec and self.spec.summary:
            return self.spec.summary
        if self.design and self.design.summary:
            return self.design.summary
        return None

    @property
    def has_children(self) -> bool:
        return bool(self.children)


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


def load_artifacts(folder: str) -> list[Artifact]:
    base = SYSTEM / folder
    reg_path = base / "registry.yaml"
    if not reg_path.exists():
        return []
    data = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    key = "specs" if folder == "product-specs" else "designs"
    entries = data.get(key) or []

    out: list[Artifact] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        file_rel = entry.get("file")
        if not file_rel or not file_rel.startswith("active/"):
            # The index renders active artifacts only.
            continue
        artifact_id = str(entry.get("id"))
        target = base / file_rel
        if not target.exists():
            continue
        fm = parse_frontmatter(target)
        if fm is None:
            continue
        if fm.get("status") != "active":
            continue
        artifact_type = str(fm.get("type") or "")
        summary_raw = fm.get("summary")
        summary: str | None = None
        if isinstance(summary_raw, str):
            stripped = summary_raw.strip()
            if stripped and stripped not in ("~", "null", "None"):
                summary = stripped
        parent_raw = fm.get("parent")
        parent: str | None
        if parent_raw is None:
            parent = None
        elif isinstance(parent_raw, str):
            stripped = parent_raw.strip()
            parent = stripped if stripped and stripped not in ("~", "null") else None
        else:
            parent = None
        out.append(Artifact(
            artifact_id=artifact_id,
            folder=folder,
            file_rel=file_rel,
            title=str(fm.get("title") or artifact_id),
            summary=summary,
            parent=parent,
            status=str(fm.get("status") or "active"),
            type=artifact_type,
        ))
    return out


def build_tree(artifacts: list[Artifact]) -> tuple[list[Node], list[Artifact]]:
    """Return (top_level_nodes, orphans).

    Each Node groups same-id spec + design pairs. Orphans are:
      - artifacts whose ``parent:`` references an unknown id
      - artifacts with ``parent: ~`` that aren't ``type: index``
        and aren't on the explicit ``TOP_LEVEL_ORDER`` allow-list

    Per ADR 0029 the navigation tree's top level is the five
    category-rollup ``type: index`` artifacts plus the explicitly
    anchored entries in ``TOP_LEVEL_ORDER``. Anything else with
    ``parent: ~`` is treated as a missing parent rather than as a
    top-level pillar — otherwise a typo or a forgotten parent would
    silently promote a regular artifact to a category headline next
    to "Pipeline operations".
    """
    nodes: dict[str, Node] = {}
    for a in artifacts:
        node = nodes.setdefault(a.artifact_id, Node(artifact_id=a.artifact_id))
        if a.kind == "spec":
            node.spec = a
        else:
            node.design = a

    top_level_allowed = set(TOP_LEVEL_ORDER)

    def may_be_top_level(a: Artifact) -> bool:
        return a.type == "index" or a.artifact_id in top_level_allowed

    top_level: list[Node] = []
    orphans: list[Artifact] = []
    for a in artifacts:
        node = nodes[a.artifact_id]
        if a.parent is None:
            if may_be_top_level(a):
                if node not in top_level:
                    top_level.append(node)
            else:
                orphans.append(a)
            continue
        parent_node = nodes.get(a.parent)
        if parent_node is None:
            orphans.append(a)
            continue
        if node is not parent_node and node not in parent_node.children:
            parent_node.children.append(node)

    # Deduplicate top_level: a node may have been added via spec and
    # design instances pointing at parent=None.
    seen: set[str] = set()
    deduped: list[Node] = []
    for n in top_level:
        if n.artifact_id in seen:
            continue
        seen.add(n.artifact_id)
        deduped.append(n)

    # Order: TOP_LEVEL_ORDER first, then alphabetical fallback.
    rank = {aid: i for i, aid in enumerate(TOP_LEVEL_ORDER)}
    deduped.sort(key=lambda n: (rank.get(n.artifact_id, len(rank)), n.artifact_id))

    # Sort children alphabetically by id within each node.
    def _sort(n: Node) -> None:
        n.children.sort(key=lambda c: c.artifact_id)
        for c in n.children:
            _sort(c)
    for n in deduped:
        _sort(n)

    return deduped, orphans


def render_node(node: Node, depth: int, lines: list[str]) -> None:
    indent = "  " * depth
    parts: list[str] = []
    if node.spec:
        parts.append(f"[{node.artifact_id}]({node.spec.link}) (spec)")
    if node.design:
        parts.append(f"[{node.artifact_id}]({node.design.link}) (design)")
    if not parts:
        parts.append(f"`{node.artifact_id}` (no resolved artifact)")
    head = " · ".join(parts)
    summary = f" — {node.summary}" if node.summary else ""
    lines.append(f"{indent}- {head}{summary}")
    for child in node.children:
        render_node(child, depth + 1, lines)


def render_top_level(node: Node, lines: list[str]) -> None:
    title = node.title
    lines.append(f"## {title}")
    lines.append("")
    if node.summary:
        lines.append(node.summary)
        lines.append("")

    links: list[str] = []
    if node.spec:
        links.append(f"- Spec: [{node.artifact_id}]({node.spec.link})")
    if node.design:
        links.append(f"- Design: [{node.artifact_id}]({node.design.link})")
    if links:
        lines.extend(links)
        lines.append("")

    if node.has_children:
        for child in node.children:
            render_node(child, depth=0, lines=lines)
        lines.append("")


def render_orphans(orphans: list[Artifact], lines: list[str]) -> None:
    if not orphans:
        return
    lines.append("## Unparented artifacts")
    lines.append("")
    lines.append(
        "These artifacts declare a `parent:` that doesn't resolve in the "
        "active surface. Re-parent them or remove the orphan reference."
    )
    lines.append("")
    for a in sorted(orphans, key=lambda a: a.artifact_id):
        summary = f" — {a.summary}" if a.summary else ""
        lines.append(f"- [{a.artifact_id}]({a.link}) ({a.kind}, parent: `{a.parent}`){summary}")
    lines.append("")


def render(top_level: list[Node], orphans: list[Artifact]) -> str:
    lines: list[str] = []
    lines.append("# Coder system — index")
    lines.append("")
    lines.append(
        "> Generated from `product-specs/registry.yaml` + "
        "`designs/registry.yaml` and the `parent:` / `summary:` "
        "frontmatter on each active artifact (ADR 0029). Hand edits "
        "are lost on the next `scripts/render_index.py` run."
    )
    lines.append("")
    lines.append(
        "Workers (PM, Architect, Reviewer, Team Manager) and humans "
        "should start here when grounding on the existing system. "
        "WIPs and deprecated artifacts are not listed — see "
        "`registry.yaml` for the full set and `ROADMAP.md` for "
        "in-flight work."
    )
    lines.append("")
    for node in top_level:
        render_top_level(node, lines)
    render_orphans(orphans, lines)
    body = "\n".join(lines).rstrip() + "\n"
    return body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="Exit 1 on drift; do not write.")
    args = ap.parse_args()

    artifacts = load_artifacts("product-specs") + load_artifacts("designs")
    top_level, orphans = build_tree(artifacts)
    rendered = render(top_level, orphans)

    if args.check:
        existing = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
        if existing != rendered:
            print(f"drift: {INDEX_PATH.relative_to(REPO_ROOT)}")
            return 1
        return 0

    INDEX_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote: {INDEX_PATH.relative_to(REPO_ROOT)} "
          f"({len(top_level)} top-level, {len(artifacts)} artifacts)")
    if orphans:
        print(f"warning: {len(orphans)} unparented artifact(s) — see "
              f"the trailing 'Unparented' section in the rendered index.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

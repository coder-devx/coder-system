#!/usr/bin/env python3
"""Surface knowledge freshness from ``last_verified_at`` frontmatter.

Walks every knowledge artifact under ``system/`` (and optionally
``template/``), reads ``last_verified_at``, and prints a stalest-first
report so we can see at a glance which active surfaces have drifted.

ADRs are excluded — their freshness is binary (superseded or not),
not date-driven (see scripts/validate.py).

Run from repo root:

    python3 scripts/freshness.py                  # full report (default)
    python3 scripts/freshness.py --top 20         # top-N stalest only
    python3 scripts/freshness.py --over 90        # only files staler than N days
    python3 scripts/freshness.py --type spec      # filter by frontmatter type
    python3 scripts/freshness.py --json           # machine-readable output
    python3 scripts/freshness.py --section template

Exit code is 0 unless ``--fail-over N`` is passed and at least one
artifact exceeds N days, in which case the script exits 1 (useful as
a CI signal once the team picks a staleness budget).
"""
from __future__ import annotations

import argparse
import datetime as _dt
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

SKIP_FILENAMES = {
    "README.md", "REGISTRY.md", "ROADMAP.md", "PHASES.md", "HISTORY.md",
    "INDEX.md", "GRAPH.md", "HOWTO.md",
    "_TEMPLATE.md", "AGENTS.md", "CLAUDE.md", "glossary.md", "_common.md",
}

ARTIFACT_FOLDERS = (
    "services", "repos", "designs", "product-specs",
    "roles", "integrations", "runbooks",
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


def iter_artifact_files(section_root: Path):
    for folder in ARTIFACT_FOLDERS:
        base = section_root / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            if path.name in SKIP_FILENAMES:
                continue
            if path.parent.name == "tasks" and path.parent.parent.parent.name == "roles":
                continue
            yield path


def collect(section_root: Path, type_filter: str | None) -> list[dict[str, Any]]:
    today = _dt.date.today()
    rows: list[dict[str, Any]] = []
    for path in iter_artifact_files(section_root):
        data = parse_frontmatter(path)
        if data is None:
            continue
        artifact_type = data.get("type")
        if artifact_type == "adr":
            continue
        if type_filter and artifact_type != type_filter:
            continue
        raw = data.get("last_verified_at")
        verified: _dt.date | None = None
        if isinstance(raw, _dt.date):
            verified = raw
        elif isinstance(raw, str):
            try:
                verified = _dt.date.fromisoformat(raw)
            except ValueError:
                pass
        age = (today - verified).days if verified else None
        rows.append({
            "path": str(path.relative_to(REPO_ROOT)),
            "type": artifact_type,
            "id": data.get("id") or data.get("title") or path.stem,
            "last_verified_at": verified.isoformat() if verified else None,
            "age_days": age,
            "status": data.get("status"),
        })
    rows.sort(
        key=lambda r: float("inf") if r["age_days"] is None else r["age_days"],
        reverse=True,
    )
    return rows


def render_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no artifacts matched)"
    headers = ("Age", "Verified", "Type", "Status", "ID", "Path")
    formatted: list[tuple[str, ...]] = []
    for r in rows:
        age = "—" if r["age_days"] is None else f"{r['age_days']}d"
        verified = r["last_verified_at"] or "MISSING"
        formatted.append((
            age, verified, str(r["type"] or "—"),
            str(r["status"] or "—"), str(r["id"]), r["path"],
        ))
    widths = [
        max(len(h), max((len(row[i]) for row in formatted), default=0))
        for i, h in enumerate(headers)
    ]
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in formatted:
        lines.append("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--section", choices=("system", "template"), default="system")
    ap.add_argument("--type", dest="type_filter",
                    help="Filter by frontmatter type (spec, design, service, …).")
    ap.add_argument("--top", type=int, help="Show only top-N stalest rows.")
    ap.add_argument("--over", type=int,
                    help="Show only rows with age > N days (missing dates included).")
    ap.add_argument("--fail-over", type=int,
                    help="Exit 1 if any row exceeds N days (CI signal).")
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON instead of a table.")
    args = ap.parse_args()

    section = REPO_ROOT / args.section
    if not section.is_dir():
        sys.stderr.write(f"error: {section} does not exist\n")
        return 2

    rows = collect(section, args.type_filter)

    if args.over is not None:
        rows = [r for r in rows if r["age_days"] is None or r["age_days"] > args.over]

    if args.top is not None:
        rows = rows[: args.top]

    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render_table(rows))

    if args.fail_over is not None:
        breached = [r for r in rows
                    if r["age_days"] is not None and r["age_days"] > args.fail_over]
        if breached:
            sys.stderr.write(
                f"\n{len(breached)} artifact(s) exceed {args.fail_over}-day freshness budget.\n"
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

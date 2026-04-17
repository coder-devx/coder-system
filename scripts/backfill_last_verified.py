#!/usr/bin/env python3
"""One-shot back-fill for spec 0043 (knowledge freshness signals).

Adds ``last_verified_at`` to the frontmatter of every knowledge
artifact that doesn't already carry it. The value is the file's
most recent git commit date (`git log -1 --format=%cs -- <path>`),
which is the best local proxy for "when was this last known to
reflect reality". Falls back to today when a file has no git
history.

Scope:
    * specs, designs, services, repos, roles, integrations, runbooks
    * under both ``system/`` and ``template/``

Excluded:
    * ADRs (append-only — spec 0043 exempts them; freshness is
      binary: superseded or not)
    * glossary.md (atemporal by definition)
    * README.md / REGISTRY.md / _TEMPLATE.md (not artifacts)

Run from repo root:

    python3 scripts/backfill_last_verified.py

The script is idempotent — re-running it leaves files with an
existing ``last_verified_at`` untouched.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKIP_FILENAMES = {
    "README.md",
    "REGISTRY.md",
    "ROADMAP.md",
    "_TEMPLATE.md",
    "AGENTS.md",
    "CLAUDE.md",
    "glossary.md",
}
# ADRs are append-only (spec 0043); freshness is binary there.
EXCLUDED_DIRS = {"adrs"}


def git_last_commit_date(path: Path) -> str | None:
    """Return the date of the most recent git commit touching ``path``."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None
    value = out.stdout.strip()
    return value or None


def parse_frontmatter(text: str) -> tuple[str, str] | None:
    """Split ``---\\n...\\n---\\n`` frontmatter from the body.

    Returns ``(frontmatter, body)`` on success; ``None`` when the
    file has no frontmatter block.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    frontmatter = text[4:end]
    body = text[end + 5 :]
    return frontmatter, body


def has_last_verified_at(frontmatter: str) -> bool:
    return bool(re.search(r"^last_verified_at:", frontmatter, flags=re.MULTILINE))


def inject_last_verified_at(frontmatter: str, value: str) -> str:
    """Insert ``last_verified_at: <value>`` into the frontmatter.

    Placement heuristic: right after the ``updated:`` field when
    present (so the two dates live together), else right after
    ``created:``, else appended to the end. Preserves every other
    line verbatim.
    """
    lines = frontmatter.split("\n")
    new_line = f"last_verified_at: {value}"
    for anchor in ("updated", "created"):
        for i, line in enumerate(lines):
            if line.startswith(f"{anchor}:"):
                lines.insert(i + 1, new_line)
                return "\n".join(lines)
    # No anchor — append (avoid trailing blank line disruption).
    if lines and lines[-1].strip() == "":
        lines.insert(len(lines) - 1, new_line)
    else:
        lines.append(new_line)
    return "\n".join(lines)


def should_process(path: Path) -> bool:
    if path.name in SKIP_FILENAMES:
        return False
    if path.suffix != ".md":
        return False
    # Skip anything inside an excluded dir (e.g. any path containing
    # ``/adrs/``).
    parts = set(path.parts)
    if parts & EXCLUDED_DIRS:
        return False
    return True


def process_file(path: Path, today: str) -> bool:
    """Process ``path``; return True when the file was modified."""
    text = path.read_text()
    parsed = parse_frontmatter(text)
    if parsed is None:
        # No frontmatter — not a knowledge artifact.
        return False
    frontmatter, body = parsed
    if has_last_verified_at(frontmatter):
        return False
    stamp = git_last_commit_date(path) or today
    new_frontmatter = inject_last_verified_at(frontmatter, stamp)
    path.write_text(f"---\n{new_frontmatter}\n---\n{body}")
    return True


def main() -> int:
    today = date.today().isoformat()
    roots = [REPO_ROOT / "system", REPO_ROOT / "template"]
    processed = 0
    skipped = 0
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            if not should_process(path):
                skipped += 1
                continue
            if process_file(path, today):
                processed += 1
                print(f"stamped {path.relative_to(REPO_ROOT)}")
            else:
                skipped += 1
    print(f"\nback-fill complete: {processed} stamped, {skipped} skipped (already stamped / excluded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

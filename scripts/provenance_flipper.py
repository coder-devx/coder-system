"""Core logic for the flip-cold-start-provenance GitHub Action.

This module is the testable source of truth for the Python logic that is
also embedded inline in
``template/.github/workflows/flip-cold-start-provenance.yml``.
When modifying the Action's inline script, keep this module in sync.

Tests live in ``tests/workflows/test_flip_cold_start_provenance.py``.
"""
from __future__ import annotations

import re


def parse_frontmatter(text: str) -> tuple[str, str] | None:
    """Return ``(frontmatter_str, body_str)`` or ``None`` when absent.

    The frontmatter is the content between the first and second ``---``
    delimiters (exclusive of the delimiters themselves).  The body is
    everything after the closing ``---\\n``.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    return text[4:end], text[end + 5:]


def has_provenance_to_flip(frontmatter: str) -> bool:
    """True when the frontmatter declares a cold-start artifact that hasn't
    yet been marked as human-edited.

    Requires both:
    - an ``ingestion_provenance:`` key (top-level in the frontmatter), and
    - an indented ``human_edited: false`` line within that block.
    """
    if not re.search(r"^ingestion_provenance:", frontmatter, re.MULTILINE):
        return False
    return bool(
        re.search(r"^\s+human_edited:\s*false\s*$", frontmatter, re.MULTILINE)
    )


def needs_flip(before_text: str, after_text: str) -> bool:
    """Return ``True`` when ``after_text`` should have ``human_edited``
    flipped to ``true``.

    All three conditions must hold:

    1. ``after_text`` has a frontmatter block containing
       ``ingestion_provenance.human_edited: false``.
    2. ``before_text`` also has a frontmatter block (i.e. the file existed
       before the PR; new files have no before-state to diff against).
    3. The body (text after the closing ``---``) differs between the two
       versions — a frontmatter-only edit does **not** trigger a flip.
    """
    after_parsed = parse_frontmatter(after_text)
    if after_parsed is None:
        return False
    after_fm, after_body = after_parsed

    if not has_provenance_to_flip(after_fm):
        return False

    before_parsed = parse_frontmatter(before_text)
    if before_parsed is None:
        return False
    _, before_body = before_parsed

    return before_body != after_body


def flip_human_edited(text: str) -> str:
    """Return ``text`` with ``human_edited: false`` rewritten to
    ``human_edited: true`` inside the frontmatter block.

    Only the first occurrence within the frontmatter is changed; the body
    is left untouched.  If ``text`` has no frontmatter the original string
    is returned unchanged.
    """
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    fm = text[4:end]
    new_fm = re.sub(
        r"^(\s+human_edited:)\s*false\s*$",
        r"\1 true",
        fm,
        flags=re.MULTILINE,
        count=1,
    )
    return "---\n" + new_fm + text[end:]

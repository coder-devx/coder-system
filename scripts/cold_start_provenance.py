#!/usr/bin/env python3
"""
Pure helper functions for the flip-cold-start-provenance GitHub Action.

These functions are extracted here so they can be unit-tested independently
of the Action runner environment. The Action YAML
(template/.github/workflows/flip-cold-start-provenance.yml) embeds the same
logic inline as a Python heredoc — keep the two in sync when making changes.

Spec 0045 AC5 / AC6.
"""
from __future__ import annotations

import re


def parse_frontmatter(text: str) -> tuple[str, str] | None:
    """Split YAML frontmatter from the file body.

    Returns ``(frontmatter_content, body)`` where *frontmatter_content* is
    the text between the first and second ``---`` delimiters (without the
    delimiters themselves), and *body* is everything after the closing ``---``.
    Returns ``None`` if the file has no valid frontmatter block.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    return text[4:end], text[end + 5:]


def has_ingestion_provenance(frontmatter: str) -> bool:
    """Return True if the frontmatter contains an ``ingestion_provenance:`` key."""
    return bool(re.search(r"^ingestion_provenance:", frontmatter, re.MULTILINE))


def human_edited_is_false(frontmatter: str) -> bool:
    """Return True if ``human_edited: false`` appears (indented) in the frontmatter."""
    return bool(re.search(r"^\s+human_edited:\s*false\s*$", frontmatter, re.MULTILINE))


def body_changed(before_text: str, after_text: str) -> bool:
    """Return True if the body (non-frontmatter content) differs between the two versions."""
    before_parsed = parse_frontmatter(before_text)
    after_parsed = parse_frontmatter(after_text)
    before_body = before_parsed[1] if before_parsed else before_text
    after_body = after_parsed[1] if after_parsed else after_text
    return before_body != after_body


def should_flip(before_text: str | None, after_text: str) -> bool:
    """Return True if this file's ``human_edited`` flag should be flipped to ``true``.

    All four conditions must hold:

    1. *after_text* has valid frontmatter with an ``ingestion_provenance`` block.
    2. ``human_edited`` is currently ``false`` in that frontmatter.
    3. *before_text* is not ``None`` — the file existed before the merge commit
       (newly added cold-start files are not flipped; they haven't been
       human-edited yet).
    4. The body (non-frontmatter lines) changed between *before_text* and
       *after_text* — at least one line outside the ``---`` block was edited.
    """
    parsed = parse_frontmatter(after_text)
    if parsed is None:
        return False
    frontmatter, _ = parsed
    if not has_ingestion_provenance(frontmatter):
        return False
    if not human_edited_is_false(frontmatter):
        return False
    if before_text is None:
        return False
    return body_changed(before_text, after_text)


def flip_human_edited(text: str) -> str:
    """Rewrite ``human_edited: false`` to ``human_edited: true`` in the frontmatter.

    Only touches the frontmatter block; the body is returned verbatim.
    """
    parsed = parse_frontmatter(text)
    if parsed is None:
        return text
    frontmatter, body = parsed
    new_fm = re.sub(
        r"^(\s+human_edited:)\s*false\s*$",
        r"\1 true",
        frontmatter,
        flags=re.MULTILINE,
    )
    return f"---\n{new_fm}\n---\n{body}"

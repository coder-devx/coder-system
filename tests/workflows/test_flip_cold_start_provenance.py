"""Unit tests for the flip-cold-start-provenance GitHub Action logic.

The helper functions under test live in ``scripts/provenance_flipper.py``
and are embedded verbatim in
``template/.github/workflows/flip-cold-start-provenance.yml``.

Covered acceptance criteria:
  AC5 — post-merge Action flips human_edited from false to true when the
        body of a cold-started artifact is edited.
  AC6 — re-run safety: already-flipped files (human_edited: true) are
        skipped, so re-runs never overwrite human edits.
"""
import sys
from pathlib import Path

# Allow import from scripts/ without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from provenance_flipper import flip_human_edited, needs_flip  # noqa: E402

# ── shared fixture content ────────────────────────────────────────────────────

# A realistic cold-started artifact with human_edited: false.
_COLD_START_FRONTMATTER = """\
---
id: "0001"
title: Example design
type: design
status: active
owner: ro
created: 2026-05-01
last_verified_at: 2026-05-01
ingestion_provenance:
  human_edited: false
  confidence: 0.8
  source_batch: services
---
"""

BODY_A = "# Example\n\nOriginal body text.\n"
BODY_B = "# Example\n\nEdited body text — human touched this.\n"


# ── needs_flip tests ──────────────────────────────────────────────────────────


def test_detects_human_edit():
    """Body changed + human_edited: false → needs_flip returns True."""
    before = _COLD_START_FRONTMATTER + BODY_A
    after = _COLD_START_FRONTMATTER + BODY_B
    assert needs_flip(before, after) is True


def test_frontmatter_only_edit_not_flagged():
    """Frontmatter changed but body unchanged → needs_flip returns False.

    A commit that only tweaks metadata (e.g. updates confidence score)
    without touching the body is *not* a human edit of the artifact's
    content and must not trigger a flip.
    """
    fm_updated = _COLD_START_FRONTMATTER.replace("confidence: 0.8", "confidence: 0.95")
    before = fm_updated + BODY_A
    after = _COLD_START_FRONTMATTER + BODY_A  # body identical
    assert needs_flip(before, after) is False


def test_already_true_skipped():
    """human_edited: true already set → needs_flip returns False (idempotent).

    Ensures re-runs of the Action or the seed script never flip a file
    that a human has already touched and the Action already recorded.
    """
    fm_flipped = _COLD_START_FRONTMATTER.replace("human_edited: false", "human_edited: true")
    before = _COLD_START_FRONTMATTER + BODY_A
    after = fm_flipped + BODY_B
    assert needs_flip(before, after) is False


def test_no_provenance_block_skipped():
    """File without ingestion_provenance: → needs_flip returns False.

    Human-authored files never carry the provenance block; the Action
    must leave them untouched regardless of how the body changed.
    """
    fm_human_authored = """\
---
id: "0002"
title: Human-authored design
type: design
status: active
owner: ro
created: 2026-05-01
last_verified_at: 2026-05-01
---
"""
    before = fm_human_authored + BODY_A
    after = fm_human_authored + BODY_B
    assert needs_flip(before, after) is False


# ── flip_human_edited tests ───────────────────────────────────────────────────


def test_flip_rewrites_false_to_true():
    """flip_human_edited rewrites the flag and leaves everything else alone."""
    text = _COLD_START_FRONTMATTER + BODY_A
    result = flip_human_edited(text)
    assert "human_edited: true" in result
    assert "human_edited: false" not in result
    # Body must be preserved verbatim.
    assert result.endswith(BODY_A)


def test_flip_is_idempotent():
    """Calling flip_human_edited twice produces the same result as once."""
    text = _COLD_START_FRONTMATTER + BODY_A
    once = flip_human_edited(text)
    twice = flip_human_edited(once)
    assert once == twice

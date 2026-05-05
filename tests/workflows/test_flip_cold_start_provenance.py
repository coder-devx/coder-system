"""
Unit tests for the flip-cold-start-provenance helper logic.

Tests the pure functions from scripts/cold_start_provenance.py which are
mirrored inline in template/.github/workflows/flip-cold-start-provenance.yml.

Covers spec 0045 AC5 (post-merge Action flips human_edited) and AC6
(re-run safety relies on the flag being correct after the flip).
"""
import sys
from pathlib import Path

# Make scripts/ importable without an installed package.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from cold_start_provenance import (  # type: ignore[import]
    flip_human_edited,
    should_flip,
)

# ── shared fixtures ───────────────────────────────────────────────────────────

_FRONTMATTER_WITH_PROVENANCE = """\
---
id: my-service
name: My Service
type: service
status: active
owner: ro
last_verified_at: 2026-04-19
ingestion_provenance:
  source_paths: ["src/"]
  source_commit: abc123
  ingested_at: "2026-04-19T12:00:00Z"
  prompt_id: cold_start_v1
  model: claude-sonnet-4-6
  confidence: 80
  human_edited: false
---
"""

_FRONTMATTER_NO_PROVENANCE = """\
---
id: my-service
name: My Service
type: service
status: active
owner: ro
last_verified_at: 2026-04-19
---
"""

_BODY_A = "# My Service\n\nOriginal body text.\n"
_BODY_B = "# My Service\n\nEdited body text — clearly human.\n"


def _file(frontmatter_block: str, body: str) -> str:
    """Compose a complete file string from a frontmatter block and body."""
    return frontmatter_block + body


# ── tests ─────────────────────────────────────────────────────────────────────


def test_detects_human_edit():
    """should_flip returns True when the body changed and human_edited is false."""
    before = _file(_FRONTMATTER_WITH_PROVENANCE, _BODY_A)
    after = _file(_FRONTMATTER_WITH_PROVENANCE, _BODY_B)
    assert should_flip(before, after) is True


def test_frontmatter_only_edit_not_flagged():
    """should_flip returns False when only frontmatter lines changed (body identical)."""
    modified_fm = _FRONTMATTER_WITH_PROVENANCE.replace(
        "last_verified_at: 2026-04-19",
        "last_verified_at: 2026-05-01",
    )
    before = _file(_FRONTMATTER_WITH_PROVENANCE, _BODY_A)
    after = _file(modified_fm, _BODY_A)
    assert should_flip(before, after) is False


def test_already_true_skipped():
    """should_flip returns False when human_edited is already true."""
    fm_already_true = _FRONTMATTER_WITH_PROVENANCE.replace(
        "  human_edited: false", "  human_edited: true"
    )
    before = _file(_FRONTMATTER_WITH_PROVENANCE, _BODY_A)
    after = _file(fm_already_true, _BODY_B)
    assert should_flip(before, after) is False


def test_no_provenance_block_skipped():
    """should_flip returns False when the file has no ingestion_provenance block."""
    before = _file(_FRONTMATTER_NO_PROVENANCE, _BODY_A)
    after = _file(_FRONTMATTER_NO_PROVENANCE, _BODY_B)
    assert should_flip(before, after) is False


def test_new_file_skipped():
    """should_flip returns False for new files (before_text is None)."""
    after = _file(_FRONTMATTER_WITH_PROVENANCE, _BODY_A)
    assert should_flip(None, after) is False


def test_flip_human_edited_rewrites_flag():
    """flip_human_edited correctly rewrites the flag and preserves the rest."""
    original = _file(_FRONTMATTER_WITH_PROVENANCE, _BODY_A)
    result = flip_human_edited(original)
    assert "human_edited: true" in result
    assert "human_edited: false" not in result
    # Body must be unchanged.
    assert result.endswith(_BODY_A)

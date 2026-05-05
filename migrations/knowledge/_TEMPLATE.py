# migrations/knowledge/_TEMPLATE.py
#
# Annotated example of a Python knowledge-repo migration file.
# Copy this to a new file named `00NN-kebab-slug.py` (e.g. `0003-add-criticality.py`)
# and fill in every required field.  Fields marked "optional" may be omitted.
#
# The migration SDK is pure: you may only import from
# `coder_core.migrations.knowledge` and the Python standard library.
# No imports from other coder_core modules are permitted — the CI
# import-boundary check enforces this.

# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

# NUMBER — unique, monotonically increasing integer.
# Must be exactly 4 digits wide in the filename (00NN) and match this value.
# No two migrations may share the same NUMBER; the coder-system CI validator
# catches collisions before merge.
NUMBER = 0  # replace with the actual migration number, e.g. 3

# SLUG — short, lowercase, hyphen-separated description of what the migration does.
# Used in branch names (`template-migration/00NN-<slug>-bK`) and PR titles.
# Keep it under 40 characters so branch names stay readable.
SLUG = "example-slug"

# DESCRIPTION — one or two sentences explaining what this migration does and why.
# Shown verbatim in PR bodies opened by the runner and in `coder migrate status`
# output.  Write for the project-repo operator who will review the PR.
DESCRIPTION = (
    "Example migration: adds the 'criticality' field with a default of 'standard' "
    "to every service artifact."
)

# TARGET_VERSION — the template_version value that repos will reach after this
# migration merges.  Must equal the previous migration's TARGET_VERSION + 1.
# The runner bumps `system/repos.yaml`'s `template_version` to this value
# unconditionally when the final (or only) batch merges.
TARGET_VERSION = 0  # replace with the actual target, e.g. 3

# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------

# ALLOW_BATCHING — set to True if this migration can be split across multiple
# PRs when the number of file changes exceeds `template_migration_max_files_per_pr`
# (default 50).  When False (the default), the runner aborts with
# error_kind='batch_required' if the change set is too large.
#
# Use True for additive or rename migrations that touch many files uniformly
# (safe to split).  Use False (or omit) for migrations where partial application
# would leave the repo in an inconsistent intermediate state.
ALLOW_BATCHING = False  # set to True for safe-to-split migrations

# AFFECTS — list of repo-relative glob patterns that describe which paths this
# migration reads or modifies.  The runner uses this to populate the
# KnowledgeRepoView snapshot, fetching only these paths from the GitHub API
# instead of the whole repo tree.
#
# Use specific patterns to minimise API calls; leave broad for complex migrations.
# If omitted, the runner fetches the full repo tree (slow on large repos).
AFFECTS = [
    "system/services/*.md",
    # "system/designs/active/*.md",
]

# EXPECTED_NONEMPTY_AT_LEAST_ONE_PROJECT — when True, the runner raises
# error_kind='suspicious_noop' if every project in the fleet produces an empty
# FileChange list.  Use for migrations that should always have work to do on at
# least one real project (catches copy-paste errors where AFFECTS is wrong).
# Default: False.
EXPECTED_NONEMPTY_AT_LEAST_ONE_PROJECT = False

# VALIDATOR_ALIASES — required for any rename migration.
# Maps old field name → new field name.  The coder-system CI validator reads
# this dict from every migration file and adds alias tolerance to the knowledge
# repo's validator while any managed project's template_version is below
# TARGET_VERSION.  The alias window closes when fleet adoption reaches 100%
# (the runner then sets `retired_at` in `system/migrations/validator-aliases.yaml`).
#
# Only include this field for rename migrations; omit it for additive/removal
# migrations.
#
# Example (rename affects_services → relates_to_services):
# VALIDATOR_ALIASES = {"affects_services": "relates_to_services"}
VALIDATOR_ALIASES = {}  # omit or leave empty for non-rename migrations

# ---------------------------------------------------------------------------
# Required: migrate() function
# ---------------------------------------------------------------------------

from coder_core.migrations.knowledge import KnowledgeRepoView, FileChange  # noqa: E402

# You may also import:
#   MoveFile   — rename a file (updates registry.yaml cross-links automatically)
#   DeleteFile — remove a file (removes it from registry.yaml as well)
# from coder_core.migrations.knowledge import MoveFile, DeleteFile


def migrate(repo: KnowledgeRepoView) -> list[FileChange]:
    """
    Inspect the repo view and return a list of changes to apply.

    KnowledgeRepoView exposes:
      repo.list(glob)           -> list[str]  of matching repo-relative paths
      repo.read(path)           -> str        raw file content (raises if not found)
      repo.parse_frontmatter(path) -> dict    parsed YAML frontmatter (raises on parse error)
      repo.repo_path            -> str        owner/repo for logging

    Return types:
      FileChange(path, content)  — create or replace a file with new content
      MoveFile(src, dst)         — rename src to dst (registry cross-links updated by runner)
      DeleteFile(path)           — delete path (registry entry removed by runner)

    Rules:
      - Read only via repo.*; never reach for GitHub, the DB, or the network.
      - Return changes in deterministic order (sort by path before returning).
      - If nothing needs changing for this project, return [] — the runner opens
        a no-op PR that only bumps template_version in repos.yaml.
      - Raise ValueError (or any exception) to abort: the runner records
        error_kind='migrate_raised' and opens no PR for this project.
    """
    changes: list[FileChange] = []

    for path in sorted(repo.list("system/services/*.md")):
        fm = repo.parse_frontmatter(path)

        # Skip files that already have the field — make the migration idempotent.
        if "criticality" in fm:
            continue

        # Insert the new field.  Preserve the original content and inject the
        # new key after the last existing frontmatter key.
        raw = repo.read(path)
        # Simple approach: append the key before the closing `---`.
        # For real migrations, use a proper YAML-aware insert to preserve order.
        new_content = raw.replace(
            "\n---\n",
            "\ncriticality: standard\n---\n",
            1,  # only first occurrence (closing frontmatter delimiter)
        )
        changes.append(FileChange(path=path, content=new_content))

    return changes

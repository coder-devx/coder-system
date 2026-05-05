# migrations/knowledge/_TEMPLATE.py
#
# Annotated example Python migration file.
# Copy this to a new file named `00NN-your-slug.py` and fill in each field.
# Lines beginning with `#` are comments explaining each field — remove or
# keep them in your copy.  The runner strips comments before execution.
#
# Imports: only import from `coder_core.migrations.knowledge`.  Reaching
# into any other coder_core module is a CI import-boundary violation.
from coder_core.migrations.knowledge import (
    KnowledgeRepoView,
    FileChange,
    MoveFile,
    DeleteFile,
)

# ---------------------------------------------------------------------------
# Required metadata fields
# ---------------------------------------------------------------------------

# NUMBER — integer, unique across all migration files.
# The runner orders migrations by NUMBER; gaps are allowed but never reused.
# The CI validator rejects duplicate NUMBERs on coder-system PR merge.
NUMBER = 1  # replace with the next available migration number

# SLUG — kebab-case string, 2–5 words.
# Used in branch names: template-migration/00NN-<slug>[-bK]
# and in PR titles: "template-migration: 00NN-<slug>".
# Keep it stable after merge — changing it after fleet adoption breaks
# branch naming expectations on any in-flight retry.
SLUG = "example-migration"

# DESCRIPTION — one-sentence human-readable summary.
# Appears in the PR body and in `coder migrate status` output.
# Write it from the reader's perspective: what state change does this produce?
DESCRIPTION = "Example migration: describe what artifact field this adds, renames, or removes."

# TARGET_VERSION — integer.
# The template_version written to repos.yaml after this migration merges.
# Must equal NUMBER for migrations that ship in isolation (the common case).
# Equal to a *higher* number only when two migrations are batched into one
# NUMBER via a design ADR — an unusual pattern, prefer separate migrations.
TARGET_VERSION = 1  # usually == NUMBER

# ---------------------------------------------------------------------------
# Optional metadata fields
# ---------------------------------------------------------------------------

# ALLOW_BATCHING — bool, default False.
# If the migration produces more than `template_migration_max_files_per_pr`
# (default 50) FileChange objects the runner will:
#   False (default): abort with error_kind='batch_required'.  Use this for
#     migrations that must apply atomically (e.g., a rename + cross-link fix).
#   True: split into batches of ≤ 50 files each.  The final batch carries the
#     repos.yaml template_version bump; earlier batches note "version bump in
#     batch N/N."  Use this for purely additive changes where partial
#     application is safe (e.g., adding a new optional field to 200 services).
ALLOW_BATCHING = False

# AFFECTS — list of glob patterns relative to the repo root.
# The runner fetches *only* these paths from GitHub when constructing the
# KnowledgeRepoView, keeping snapshot time proportional to scope.
# Omit (or set to None) to fetch the full repo tree — acceptable for small
# repos but slow at fleet scale.
AFFECTS = [
    "system/services/*.md",
    "system/services/registry.yaml",
]

# EXPECTED_NONEMPTY_AT_LEAST_ONE_PROJECT — bool, default False.
# When True, the runner aborts with error_kind='suspicious_noop' if every
# managed project returns an empty FileChange list.  Use this for migrations
# that must produce output on at least one real project (e.g., a field rename
# that would be vacuous if every artifact already had the new name).
# Leave False (default) for no-op baseline migrations or migrations that are
# legitimately skippable on all projects.
EXPECTED_NONEMPTY_AT_LEAST_ONE_PROJECT = False

# VALIDATOR_ALIASES — dict mapping old field name → new field name.
# Required for any rename migration.  The CI validator on coder-system reads
# this dict from every migration file and writes the entries into
# system/migrations/validator-aliases.yaml so both names are accepted while
# the fleet is mid-migration (ADR 0019).
# Omit (or set to {}) for additive or remove-only migrations.
# Example for a field rename migration:
#   VALIDATOR_ALIASES = {"affects_services": "relates_to_services"}
VALIDATOR_ALIASES = {}

# ---------------------------------------------------------------------------
# migrate(repo) — the migration entry point
# ---------------------------------------------------------------------------
#
# Arguments:
#   repo: KnowledgeRepoView — a read-only snapshot of the project repo.
#     Provides:
#       repo.artifacts(glob)  — iterate artifacts matching a glob pattern.
#         Each artifact has:
#           .path     (str)  — repo-relative path, e.g. "system/services/foo.md"
#           .content  (str)  — raw file content (frontmatter + body)
#           .frontmatter (dict) — parsed YAML frontmatter
#       repo.file(path)       — returns a single file's content (str | None)
#
# Return value:
#   list[FileChange | MoveFile | DeleteFile]
#
#   FileChange(path, content) — write (or overwrite) a file.
#     Use this to add a key to frontmatter, rename an enum value, or
#     make any in-place edit.  The runner diffs against the current tree;
#     unchanged content produces no diff line in the PR.
#
#   MoveFile(old_path, new_path, content=None) — rename a file.
#     The runner deletes old_path and creates new_path.  If content is
#     provided it is used as the new file's content; if omitted the existing
#     content is copied verbatim.  The SDK refuses MoveFile against paths in
#     active/, wip/, or deprecated/ (forbidden_path error).
#
#   DeleteFile(path) — remove a file from the repo.
#     Use only with extreme caution and an ADR rationale.  Prefer MoveFile
#     to deprecated/ over outright deletion.
#
# Idempotency requirement:
#   Running migrate(repo) twice on the same repo must produce the same
#   FileChange list.  The runner can be dispatched multiple times; the
#   idempotency check (template_migrations row) prevents double-application
#   but your migrate() function must still be safe to call repeatedly.
#   Typical pattern: check if the artifact already has the new field/value
#   before adding it.


def migrate(repo: KnowledgeRepoView) -> list[FileChange | MoveFile | DeleteFile]:
    changes: list[FileChange | MoveFile | DeleteFile] = []

    for artifact in repo.artifacts("system/services/*.md"):
        fm = artifact.frontmatter

        # Idempotency guard: skip if this artifact already has the new field.
        if "new_field" in fm:
            continue

        # Example: insert a new optional field with a default value.
        # Edit the raw content so that field order and comments are preserved.
        new_content = artifact.content.replace(
            "owner: ro\n",
            "owner: ro\nnew_field: default-value\n",
            1,  # replace only the first occurrence
        )
        changes.append(FileChange(path=artifact.path, content=new_content))

    return changes

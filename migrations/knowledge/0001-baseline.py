NUMBER = 1
SLUG = "baseline"
DESCRIPTION = "Baseline migration: records template_version=1 for projects at version 0. No artifact changes."
TARGET_VERSION = 1

from coder_core.migrations.knowledge import KnowledgeRepoView, FileChange

def migrate(repo: KnowledgeRepoView) -> list[FileChange]:
    return []  # no-op; template_version bump is applied by the runner unconditionally

#!/usr/bin/env python3
"""Seed flip-cold-start-provenance.yml into every managed knowledge repo.

One-time script for spec 0045, stage 3. Copies
``template/.github/workflows/flip-cold-start-provenance.yml`` from this
repo into every existing managed knowledge repo that doesn't already have
it, by opening a PR via the GitHub Contents API (using ``gh``).

When spec 0052's ``coder managed-workflows sync`` helper ships, this
script should be retired in favour of:

    coder managed-workflows sync --workflow flip-cold-start-provenance

Usage (from repo root):

    python3 scripts/seed_cold_start_action.py [--dry-run] [--project SLUG]

Environment variables:

    CODER_ADMIN_TOKEN  — admin JWT for the coder-core API
    CODER_BASE_URL     — base URL of coder-core, e.g.
                         https://coder-core-abc123-uc.a.run.app
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_TEMPLATE = (
    REPO_ROOT / "template" / ".github" / "workflows" / "flip-cold-start-provenance.yml"
)
WORKFLOW_DEST = ".github/workflows/flip-cold-start-provenance.yml"
PR_BRANCH = "managed-workflow/add-flip-cold-start-provenance"
PR_TITLE = "managed-workflow: install flip-cold-start-provenance"
PR_BODY = """\
Installs the `flip-cold-start-provenance` Action (spec 0045, stage 3).

After any PR merges into `main`, this workflow checks for cold-started
knowledge artifacts (`ingestion_provenance.human_edited: false`) whose
body was edited by the merge. For each such file it rewrites
`human_edited: false` → `human_edited: true` and pushes a follow-up
commit attributed to `coder-system-bot`.

This is a managed workflow distributed by `coder-system` (spec 0052).
Do not hand-edit — changes are overwritten by the next sync.
"""


def _api_get(url: str, token: str) -> list | dict:
    """GET ``url`` with bearer auth, return parsed JSON."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_projects(base_url: str, token: str) -> list[dict]:
    """Return the list of projects from the coder-core API."""
    return _api_get(f"{base_url.rstrip('/')}/v1/projects", token)


def knowledge_repo_for(project: dict) -> str | None:
    """Return the ``owner/repo`` slug for the project's knowledge repo."""
    return (
        project.get("github_knowledge_repo")
        or project.get("knowledge_repo")
        or None
    )


def workflow_exists(repo: str) -> bool:
    """True if the workflow file is already present in ``repo``."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/{WORKFLOW_DEST}"],
        capture_output=True,
    )
    return result.returncode == 0


def open_pr(repo: str, workflow_content: str, dry_run: bool) -> str | None:
    """Open a PR adding the workflow file to ``repo``.

    Returns the PR URL, or ``None`` on dry-run.
    """
    if dry_run:
        print(f"  [dry-run] would open PR in {repo}")
        return None

    # Resolve the default branch and its tip SHA.
    default_branch = subprocess.run(
        ["gh", "api", f"repos/{repo}", "--jq", ".default_branch"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    base_sha = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/refs/heads/{default_branch}",
         "--jq", ".object.sha"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    # Create (or reset) the working branch.
    # A 422 means the ref already exists; ignore it and reuse the branch.
    create = subprocess.run(
        ["gh", "api", "--method", "POST", f"repos/{repo}/git/refs",
         "--field", f"ref=refs/heads/{PR_BRANCH}",
         "--field", f"sha={base_sha}"],
        capture_output=True,
    )
    if create.returncode != 0 and b"Reference already exists" not in create.stderr:
        raise subprocess.CalledProcessError(create.returncode, create.args, create.stderr)

    # PUT the workflow file on the branch.
    encoded = base64.b64encode(workflow_content.encode()).decode()
    subprocess.run(
        ["gh", "api", "--method", "PUT",
         f"repos/{repo}/contents/{WORKFLOW_DEST}",
         "--field", f"message={PR_TITLE}",
         "--field", f"content={encoded}",
         "--field", f"branch={PR_BRANCH}"],
        capture_output=True, check=True,
    )

    # Open the PR.
    result = subprocess.run(
        ["gh", "pr", "create",
         "--repo", repo,
         "--base", default_branch,
         "--head", PR_BRANCH,
         "--title", PR_TITLE,
         "--body", PR_BODY],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making any API calls",
    )
    parser.add_argument(
        "--project",
        metavar="SLUG",
        help="Limit to a single project (matched against slug or id)",
    )
    args = parser.parse_args()

    base_url = os.environ.get("CODER_BASE_URL", "").rstrip("/")
    token = os.environ.get("CODER_ADMIN_TOKEN", "")
    if not base_url or not token:
        sys.stderr.write(
            "error: CODER_BASE_URL and CODER_ADMIN_TOKEN must be set\n"
        )
        return 1

    if not WORKFLOW_TEMPLATE.exists():
        sys.stderr.write(f"error: template not found: {WORKFLOW_TEMPLATE}\n")
        return 1

    workflow_content = WORKFLOW_TEMPLATE.read_text()

    print("Fetching project list from coder-core...")
    try:
        projects = get_projects(base_url, token)
    except urllib.error.URLError as exc:
        sys.stderr.write(f"error: could not reach coder-core: {exc}\n")
        return 1

    if args.project:
        projects = [
            p for p in projects
            if p.get("slug") == args.project or str(p.get("id")) == args.project
        ]
        if not projects:
            sys.stderr.write(
                f"error: no project found with slug/id: {args.project!r}\n"
            )
            return 1

    print(f"Found {len(projects)} project(s)\n")

    opened = 0
    skipped = 0
    errors = 0

    for project in projects:
        repo = knowledge_repo_for(project)
        slug = project.get("slug") or project.get("id") or repo or "?"
        if not repo:
            print(f"  {slug}: no knowledge_repo configured — skip")
            skipped += 1
            continue

        if not args.dry_run and workflow_exists(repo):
            print(f"  {slug} ({repo}): already installed — skip")
            skipped += 1
            continue

        print(f"  {slug} ({repo}): installing...")
        try:
            pr_url = open_pr(repo, workflow_content, args.dry_run)
            if pr_url:
                print(f"    PR: {pr_url}")
            opened += 1
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or b"").decode().strip()
            sys.stderr.write(f"  {slug}: error — {err or exc}\n")
            errors += 1

    print(
        f"\nDone: {opened} PR(s) opened, {skipped} skipped (already installed"
        f"), {errors} error(s)"
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
One-time seed script for spec 0045 (cold-start ingestion).

Copies ``template/.github/workflows/flip-cold-start-provenance.yml`` into
every existing managed knowledge repo that doesn't already have it, by
opening a PR against each repo via the GitHub Contents API.

Run once as part of the spec 0045 release. The sweep must complete before
any project can invoke ``coder project ingest`` (see spec 0045 Decisions).

Usage::

    CODER_ADMIN_TOKEN=<token> GITHUB_TOKEN=<token> \\
        python3 scripts/seed_cold_start_action.py

    # dry run — print what would be done, no API calls
    CODER_ADMIN_TOKEN=<token> GITHUB_TOKEN=<token> \\
        python3 scripts/seed_cold_start_action.py --dry-run

    # limit to a single project
    CODER_ADMIN_TOKEN=<token> GITHUB_TOKEN=<token> \\
        python3 scripts/seed_cold_start_action.py --project coder

Environment variables::

    CODER_ADMIN_TOKEN   admin JWT for the coder-core API
    CODER_BASE_URL      base URL of coder-core (default: http://localhost:8080)
    GITHUB_TOKEN        GitHub token with contents:write on managed repos
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_TEMPLATE = (
    REPO_ROOT / "template" / ".github" / "workflows" / "flip-cold-start-provenance.yml"
)
WORKFLOW_DEST = ".github/workflows/flip-cold-start-provenance.yml"
BRANCH_NAME = "chore/seed-flip-cold-start-provenance"
DEFAULT_BASE_URL = "http://localhost:8080"


# ── GitHub API helpers ────────────────────────────────────────────────────────


def _gh(
    path: str,
    token: str,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> dict | list | None:
    """Make a GitHub API request. Returns parsed JSON or None on 404."""
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} → {exc.code}: {body_text}") from exc


def file_exists(org: str, repo: str, path: str, token: str) -> bool:
    return _gh(f"/repos/{org}/{repo}/contents/{path}", token) is not None


def get_default_branch_sha(org: str, repo: str, token: str) -> tuple[str, str]:
    """Return (default_branch_name, head_sha)."""
    info = _gh(f"/repos/{org}/{repo}", token)
    if info is None:
        raise RuntimeError(f"repo {org}/{repo} not found")
    branch = info["default_branch"]
    ref = _gh(f"/repos/{org}/{repo}/git/ref/heads/{branch}", token)
    if ref is None:
        raise RuntimeError(f"ref heads/{branch} not found in {org}/{repo}")
    return branch, ref["object"]["sha"]


# ── coder-core API helper ─────────────────────────────────────────────────────


def get_projects(base_url: str, admin_token: str) -> list[dict]:
    url = f"{base_url}/v1/projects"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        print(f"error: GET /v1/projects → {exc.code}: {body_text}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"error: cannot reach {url}: {exc.reason}", file=sys.stderr)
        sys.exit(1)


# ── seed logic ────────────────────────────────────────────────────────────────


def seed_repo(
    org: str,
    repo: str,
    workflow_content: str,
    github_token: str,
    *,
    dry_run: bool,
) -> str | None:
    """Ensure the workflow file is present in *org/repo*. Returns PR URL or None."""
    if dry_run:
        print(f"    [dry-run] would open PR in {org}/{repo} to add {WORKFLOW_DEST}")
        return None

    if file_exists(org, repo, WORKFLOW_DEST, github_token):
        print(f"    already present — skip")
        return None

    # Create the feature branch (ignore error if it already exists).
    default_branch, head_sha = get_default_branch_sha(org, repo, github_token)
    try:
        _gh(
            f"/repos/{org}/{repo}/git/refs",
            github_token,
            method="POST",
            body={"ref": f"refs/heads/{BRANCH_NAME}", "sha": head_sha},
        )
    except RuntimeError as exc:
        # 422 = branch already exists; treat as non-fatal.
        if "422" not in str(exc):
            raise

    # Add the workflow file to the branch.
    content_b64 = base64.b64encode(workflow_content.encode()).decode()
    _gh(
        f"/repos/{org}/{repo}/contents/{WORKFLOW_DEST}",
        github_token,
        method="PUT",
        body={
            "message": "chore: add flip-cold-start-provenance Action (spec 0045)",
            "content": content_b64,
            "branch": BRANCH_NAME,
            "committer": {
                "name": "coder-system-bot",
                "email": "coder-system-bot@users.noreply.github.com",
            },
        },
    )

    # Open the PR.
    pr = _gh(
        f"/repos/{org}/{repo}/pulls",
        github_token,
        method="POST",
        body={
            "title": "chore: add flip-cold-start-provenance Action (spec 0045)",
            "body": (
                "Adds `.github/workflows/flip-cold-start-provenance.yml` as part of "
                "the spec 0045 (cold-start ingestion) release.\n\n"
                "After each PR merges, this Action inspects changed files and flips "
                "`ingestion_provenance.human_edited` to `true` on any cold-started "
                "artifact whose body was edited by the merge commit. This makes "
                "cold-start re-runs safe — they will never overwrite a human-edited "
                "artifact (spec 0045 AC5, AC6).\n\n"
                "Seeded by `scripts/seed_cold_start_action.py` in coder-system."
            ),
            "head": BRANCH_NAME,
            "base": default_branch,
        },
    )
    return pr["html_url"] if pr else None


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making API calls",
    )
    parser.add_argument(
        "--project",
        metavar="SLUG",
        help="Limit to a single project by slug or id",
    )
    args = parser.parse_args()

    admin_token = os.environ.get("CODER_ADMIN_TOKEN")
    if not admin_token:
        print("error: CODER_ADMIN_TOKEN env var not set", file=sys.stderr)
        return 1

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("error: GITHUB_TOKEN env var not set", file=sys.stderr)
        return 1

    base_url = os.environ.get("CODER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    if not WORKFLOW_TEMPLATE.exists():
        print(f"error: template not found: {WORKFLOW_TEMPLATE}", file=sys.stderr)
        return 1
    workflow_content = WORKFLOW_TEMPLATE.read_text()

    projects = get_projects(base_url, admin_token)
    if args.project:
        projects = [
            p for p in projects
            if p.get("slug") == args.project or p.get("id") == args.project
        ]
        if not projects:
            print(f"error: project {args.project!r} not found in registry", file=sys.stderr)
            return 1

    print(f"seeding flip-cold-start-provenance into {len(projects)} project(s)...")
    if args.dry_run:
        print("[dry-run mode — no API calls will be made]\n")

    errors = 0
    for project in projects:
        knowledge_repo = project.get("knowledge_repo") or project.get("knowledge_repo_slug")
        slug = project.get("slug") or project.get("id") or "(unknown)"

        if not knowledge_repo:
            print(f"  skip {slug}: no knowledge_repo field in project record")
            continue
        if "/" not in knowledge_repo:
            print(
                f"  skip {slug}: knowledge_repo {knowledge_repo!r} is not in org/repo format"
            )
            continue

        org, repo = knowledge_repo.split("/", 1)
        print(f"  {slug} ({org}/{repo})")

        try:
            pr_url = seed_repo(org, repo, workflow_content, github_token, dry_run=args.dry_run)
            if pr_url:
                print(f"    opened PR: {pr_url}")
        except Exception as exc:  # noqa: BLE001
            print(f"    error: {exc}", file=sys.stderr)
            errors += 1

    status = "done" if errors == 0 else f"done with {errors} error(s)"
    print(f"\n{status}.")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

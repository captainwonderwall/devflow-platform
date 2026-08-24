import json
import subprocess
import sys

from devflow_sdk.branch_name import parse_branch

WORKTRUNK_INSTALL_HINT = (
    "ERROR: worktrunk (wt) not found. Install it with:\n"
    "  brew install worktrunk\n"
    "Then set up shell integration: wt config shell install"
)


def check_worktrunk() -> None:
    """Exit 1 with an install hint if the wt CLI is not available."""
    try:
        subprocess.run(["wt", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print(WORKTRUNK_INSTALL_HINT, file=sys.stderr)
        sys.exit(1)


def query_worktrees() -> list | None:
    """Return parsed wt list --format json output, or None on any failure."""
    try:
        result = subprocess.run(
            ["wt", "list", "--format", "json"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def list_worktrees() -> list:
    """Return the parsed wt list --format json payload, or exit 1 on failure."""
    try:
        result = subprocess.run(
            ["wt", "list", "--format", "json"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        print(WORKTRUNK_INSTALL_HINT, file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0:
        print(f"ERROR: 'wt list' failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"ERROR: 'wt list' returned invalid JSON:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)


def _branch_matches(branch, issue_id, source):
    parsed = parse_branch(branch)
    if not parsed:
        return False
    if parsed["source"] != source:
        return False
    return parsed["id"].lower() == issue_id.lower()


def find_matching_worktrees(issue_id, source, worktrees=None):
    """Return a list of {branch, path} dicts for worktrees whose branch matches
    the given issue id and source ("github" or "jira").

    Excludes the main worktree.
    """
    if worktrees is None:
        worktrees = list_worktrees()

    matches = []
    for wt in worktrees:
        if wt.get("is_main"):
            continue
        branch = wt.get("branch")
        if _branch_matches(branch, str(issue_id), source):
            matches.append({"branch": branch, "path": wt.get("path")})
    return matches


def is_dirty(path):
    """Return True if the worktree at `path` has uncommitted changes
    (staged, modified, or untracked files); False otherwise, including if
    the underlying git command itself fails (fail-open)."""
    try:
        result = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True,
        )
    except OSError:
        return False
    return bool(result.stdout.strip())

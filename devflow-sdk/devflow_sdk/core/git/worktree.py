# devflow_sdk/core/git/worktree.py
import json
import os
import subprocess
import sys

from devflow_sdk.core.prompts import confirm, select, Choice


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
    from devflow_sdk.core.git._worktrunk import WORKTRUNK_INSTALL_HINT
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


def is_dirty(path: str) -> bool:
    """Return True if the worktree at path has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True,
        )
    except OSError:
        return False
    return bool(result.stdout.strip())


def get_repo_root() -> str:
    """Return the root of the main worktree (not necessarily cwd)."""
    result = subprocess.run(
        ["wt", "list", "--format", "json"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        try:
            for wt in json.loads(result.stdout):
                if wt.get("is_main"):
                    return wt["path"]
        except (json.JSONDecodeError, KeyError):
            pass

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR: Not inside a git repository.", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def _find_worktree_path(branch: str) -> str | None:
    worktrees = query_worktrees()
    if worktrees is None:
        return None
    for wt in worktrees:
        if wt.get("branch") == branch:
            return wt.get("path")
    return None


def _detect_incoming_commits(branch: str) -> None:
    subprocess.run(
        ["git", "fetch", "origin", branch],
        capture_output=True, text=True,
    )
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{branch}..origin/{branch}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return
    try:
        count = int(result.stdout.strip())
    except ValueError:
        return
    if count == 0:
        return
    print(f"Remote has {count} commit(s) that '{branch}' does not have.")
    choice = select(
        "What would you like to do?",
        choices=[
            Choice("Pull latest changes", value="pull"),
            Choice("Continue without pulling", value="skip"),
        ],
    )
    if choice == "pull":
        subprocess.run(
            ["git", "fetch", "origin", f"{branch}:{branch}"],
            capture_output=True, text=True,
        )


def _branch_exists_locally(branch: str) -> bool:
    result = subprocess.run(
        ["git", "branch", "--list", branch],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git branch --list failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return bool(result.stdout.strip())


def create_worktree(branch: str) -> str | None:
    """Create or switch to a worktree for branch. Returns the worktree path."""
    if _branch_exists_locally(branch):
        _detect_incoming_commits(branch)
        print(f"Branch '{branch}' already exists.")
        if not confirm(f"Switch to existing branch '{branch}'?"):
            print("Aborted.")
            sys.exit(0)
        print(f"Switching to worktree for '{branch}'...")
        result = subprocess.run(["wt", "switch", "--no-cd", branch], text=True)
        if result.returncode != 0:
            sys.exit(1)
        return _find_worktree_path(branch)

    print(f"Creating worktree for '{branch}' (pre-start hooks may take a few minutes)...")
    result = subprocess.run(["wt", "switch", "--create", "--no-cd", branch], text=True)
    if result.returncode != 0:
        sys.exit(1)
    return _find_worktree_path(branch)

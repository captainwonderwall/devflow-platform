import json
import os
import subprocess
import sys

from devflow_sdk.worktrunk import check_worktrunk, query_worktrees
from devflow_sdk.prompts import confirm


def get_repo_root():
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


def _find_worktree_path(branch):
    worktrees = query_worktrees()
    if worktrees is None:
        return None
    for wt in worktrees:
        if wt.get("branch") == branch:
            return wt.get("path")
    return None


def _persist_branch_for_shell(branch):
    branch_file = os.path.join(os.path.expanduser("~"), ".start-issue-branch")
    try:
        with open(branch_file, "w") as f:
            f.write(branch)
    except OSError as e:
        print(
            f"WARNING: Could not persist branch name for shell: {e}\n"
            "The worktree was created successfully, but shell integration will not "
            "switch to it automatically.",
            file=sys.stderr,
        )


def _branch_exists_locally(branch):
    result = subprocess.run(
        ["git", "branch", "--list", branch],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git branch --list failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return bool(result.stdout.strip())


def create_worktree(branch):
    if _branch_exists_locally(branch):
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

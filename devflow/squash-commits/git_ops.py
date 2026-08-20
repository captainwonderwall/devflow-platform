#!/usr/bin/env python3
"""Pure git helpers for squash-commits. No AI or UI concerns."""
import subprocess
import sys


def _run_git(args):
    return subprocess.run(["git"] + args, capture_output=True, text=True)


def current_branch():
    result = _run_git(["branch", "--show-current"])
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_base_branch():
    """Detect the branch's target/base branch: origin/HEAD, falling back to
    the GitHub default branch via `gh`, falling back to 'main'."""
    result = _run_git(["rev-parse", "--abbrev-ref", "origin/HEAD"])
    if result.returncode == 0:
        value = result.stdout.strip()
        if value and "/" in value and value != "origin/HEAD":
            return value.split("/", 1)[1]

    try:
        gh_result = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef",
             "--jq", ".defaultBranchRef.name"],
            capture_output=True,
            text=True,
        )
        if gh_result.returncode == 0:
            branch = gh_result.stdout.strip()
            if branch:
                return branch
    except (FileNotFoundError, OSError):
        pass

    print(
        "WARNING: Could not detect default branch from origin/HEAD or "
        "GitHub; assuming 'main'.",
        file=sys.stderr,
    )
    return "main"


def is_dirty():
    result = _run_git(["status", "--porcelain"])
    return bool(result.stdout.strip())


def commits_ahead(base):
    result = _run_git(["rev-list", "--count", f"{base}..HEAD"])
    output = result.stdout.strip()
    if result.returncode != 0 or not output.isdigit():
        return 0
    return int(output)


def stash_push():
    result = _run_git(
        ["stash", "push", "--include-untracked", "-m", "squash-commits-autostash"]
    )
    return result.returncode == 0


def stash_pop():
    result = _run_git(["stash", "pop"])
    return result.returncode == 0


def log_for_prompt(base):
    result = _run_git(["log", f"{base}..HEAD", "--format=%s%n%b"])
    return result.stdout.strip() if result.returncode == 0 else ""


def diff_stat(base):
    result = _run_git(["diff", f"{base}..HEAD", "--stat"])
    return result.stdout.strip() if result.returncode == 0 else ""


def soft_reset_and_commit(base, message):
    reset_result = _run_git(["reset", "--soft", base])
    if reset_result.returncode != 0:
        return False
    commit_result = _run_git(["commit", "-m", message])
    return commit_result.returncode == 0


def force_push_with_lease(branch):
    result = _run_git(["push", "--force-with-lease", "origin", branch])
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output

import json
import subprocess
import sys


def get_main_branch(worktrees):
    """Return the branch name of the worktree marked is_main, or None if not found."""
    for wt in worktrees:
        if wt.get("is_main"):
            return wt.get("branch")
    return None


def _is_ancestor(repo_root, branch, target_ref):
    """Return True if branch is a git ancestor of target_ref (fast-forward/merge-commit merges).

    Exits the process with an error if the underlying git command fails
    unexpectedly (i.e. neither "is an ancestor" nor "is not an ancestor").
    """
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", branch, target_ref],
        cwd=repo_root, capture_output=True, text=True,
    )
    if result.returncode in (0, 1):
        return result.returncode == 0

    print(
        f"ERROR: could not determine merge status of '{branch}' against "
        f"'{target_ref}':\n{result.stderr}",
        file=sys.stderr,
    )
    sys.exit(1)


def _check_gh_merged_pr(repo_root, branch, main_branch):
    """Return True/False/None indicating whether `branch` has a merged PR on GitHub.

    Uses `gh pr list --state merged --head <branch> --base <main_branch>`, which
    finds merged PRs by their original head branch name even after the remote branch
    has been deleted (GitHub retains PR metadata independent of the branch's lifetime).
    The --base filter ensures we only match PRs merged into main_branch, not into
    some other base (e.g. a release branch).

    Returns None (inconclusive) if `gh` is not installed, the command fails
    (e.g. not authenticated, no network), or its output isn't valid JSON --
    the caller should fall through to another detection method in that case.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--head", branch,
             "--base", main_branch, "--json", "number,mergedAt"],
            cwd=repo_root, capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    return bool(prs)


def _git_patch_id(repo_root, diff_text):
    """Return the patch-id string for the given diff text, or None if diff_text is empty."""
    if not diff_text.strip():
        return None
    result = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=repo_root, input=diff_text, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(
            f"ERROR: 'git patch-id --stable' failed (exit {result.returncode}):\n"
            f"{result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not result.stdout.strip():
        return None
    return result.stdout.split()[0]


def _patch_id_matches(repo_root, branch, target_ref):
    """Return True if a commit added to target_ref reproduces branch's net diff.

    This detects squash merges: GitHub's squash commit has a net diff against
    its parent that (barring manual edits during merge) matches the branch's
    cumulative diff since the merge-base, so their `git patch-id` values match.

    Exits the process with an error if the underlying git commands fail
    unexpectedly (there are no further fallbacks after this tier).
    """
    merge_base_result = subprocess.run(
        ["git", "merge-base", branch, target_ref],
        cwd=repo_root, capture_output=True, text=True,
    )
    if merge_base_result.returncode != 0:
        print(
            f"ERROR: could not find merge-base of '{branch}' and '{target_ref}':\n"
            f"{merge_base_result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)
    merge_base = merge_base_result.stdout.strip()

    branch_diff = subprocess.run(
        ["git", "diff", f"{merge_base}...{branch}"],
        cwd=repo_root, capture_output=True, text=True,
    )
    if branch_diff.returncode != 0:
        print(
            f"ERROR: could not diff '{branch}' against '{merge_base}':\n"
            f"{branch_diff.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)
    branch_patch_id = _git_patch_id(repo_root, branch_diff.stdout)
    if branch_patch_id is None:
        return False

    log_result = subprocess.run(
        ["git", "log", "--no-merges", "--format=%H", f"{merge_base}..{target_ref}"],
        cwd=repo_root, capture_output=True, text=True,
    )
    if log_result.returncode != 0:
        print(
            f"ERROR: could not list commits between '{merge_base}' and "
            f"'{target_ref}':\n{log_result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)
    candidate_commits = [c for c in log_result.stdout.splitlines() if c.strip()]

    for commit in candidate_commits:
        show_result = subprocess.run(
            ["git", "show", commit],
            cwd=repo_root, capture_output=True, text=True,
        )
        if show_result.returncode != 0:
            continue
        candidate_patch_id = _git_patch_id(repo_root, show_result.stdout)
        if candidate_patch_id is not None and candidate_patch_id == branch_patch_id:
            return True

    return False


def is_merged(repo_root, branch, main_branch):
    """Return True if branch has been merged into main_branch.

    Checks three tiers in order, short-circuiting on the first definitive
    "merged" answer:
      1. git ancestor check (fast-forward / merge-commit / rebase merges).
      2. GitHub PR lookup via `gh` (handles squash merges; works even after
         the remote branch has been deleted).
      3. git patch-id comparison against all non-merge commits reachable from
         target_ref since the merge-base (a git-only fallback used when `gh`
         is unavailable or fails).

    Best-effort fetches origin/<main_branch> first so all tiers reflect the
    remote state rather than a possibly-stale local ref. Falls back to the
    local main_branch ref if the fetch fails (e.g. offline).
    """
    fetch = subprocess.run(
        ["git", "fetch", "origin", main_branch],
        cwd=repo_root, capture_output=True, text=True,
    )

    if fetch.returncode == 0:
        target_ref = f"origin/{main_branch}"
    else:
        target_ref = main_branch

    if _is_ancestor(repo_root, branch, target_ref):
        return True

    # _patch_id_matches still runs even when _check_gh_merged_pr returns False (not just None),
    # because the branch may have been merged without a tracked PR (e.g. direct push) — intentional.
    if _check_gh_merged_pr(repo_root, branch, main_branch):
        return True

    return _patch_id_matches(repo_root, branch, target_ref)

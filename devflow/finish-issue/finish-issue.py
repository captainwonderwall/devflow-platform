#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)   # Homebrew: shared/ is sibling of finish-issue.py
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)    # Dev: shared/ is at repo root

from devflow_sdk.ticket_info import fetch
from devflow_sdk.prompts import select, text
from devflow_sdk.issue_context import remove_issue_context, read_issue_context
from devflow_sdk.shell_function_check import check_shell_function
from devflow_sdk.worktrunk import check_worktrunk, list_worktrees, find_matching_worktrees, is_dirty
from shell_state import (
    _persist_branch_for_shell,
    _persist_worktree_for_shell,
    _persist_force_for_shell,
    _persist_worktree_path_for_shell,
    _clear_force_marker_for_shell,
)
from merge_check import get_main_branch, is_merged


def _cwd_inside_worktree(worktree_path, cwd=None):
    """Return True if the current working directory is inside worktree_path.

    A Python subprocess can never change its parent shell's directory (see
    docs/superpowers/specs/2026-08-10-finish-issue-worktree-switch-design.md).
    If we blindly `wt remove` a worktree while the calling shell is sitting
    inside it, the shell is left pointed at a now-deleted git worktree,
    breaking any subsequent git command (and often the shell prompt itself)
    with "fatal: not a git repository". This check lets us refuse instead.
    """
    cwd = os.path.realpath(cwd if cwd is not None else os.getcwd())
    worktree_path = os.path.realpath(worktree_path)
    return cwd == worktree_path or cwd.startswith(worktree_path + os.sep)


DIRTY_ABORT = "Abort"
DIRTY_DROP = "Drop uncommitted changes and continue"


def resolve_dirty_choice(choice):
    """Map the raw questionary.select() return value to 'abort' or 'drop'.
    Ctrl+C returns None from questionary, which we treat as 'abort'."""
    if choice == DIRTY_DROP:
        return "drop"
    return "abort"


def prompt_dirty_tree_choice(branch):
    return select(
        f"Worktree for '{branch}' has uncommitted changes. What do you want to do?",
        [DIRTY_ABORT, DIRTY_DROP],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Finish a JIRA or GitHub issue by removing its worktree "
                     "once the associated branch has been merged."
    )
    parser.add_argument(
        "issue",
        nargs="?",
        default=None,
        help="JIRA issue key (e.g. VDP-46625) or GitHub issue number (e.g. 33). "
             "If omitted, the issue is read from the worktree's stored context.",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    check_worktrunk()
    check_shell_function(
        "# >>> finish-issue shell integration >>>",
        f"ERROR: finish-issue shell function is not installed or is out of date.\n"
        f"Re-run the installer: {os.path.join(SCRIPT_DIR, 'install.sh')}\n"
        "Then restart your shell or run: source {rc_path}",
        required_content=["command finish-issue --prepare", ".finish-issue-force"],
    )

    if args.issue:
        issue = fetch(args.issue)
    else:
        issue = read_issue_context(os.getcwd())
        if issue is None:
            issue_arg = text("Enter JIRA issue key or GitHub issue number:")
            if issue_arg is None:
                sys.exit(1)
            issue = fetch(issue_arg)

    print(f"Issue: {issue['source'].upper()} {issue['id']}: {issue['title']}")

    worktrees = list_worktrees()
    matches = find_matching_worktrees(issue['id'], issue['source'], worktrees=worktrees)

    if not matches:
        print(f"ERROR: No worktree found matching issue '{issue['id']}'.", file=sys.stderr)
        sys.exit(1)

    if len(matches) > 1:
        print(
            f"ERROR: Multiple worktrees match issue '{issue['id']}':",
            file=sys.stderr,
        )
        for m in matches:
            print(f"  {m['branch']} -> {m['path']}", file=sys.stderr)
        print(
            "Please remove the correct one manually, e.g.: wt remove <branch>",
            file=sys.stderr,
        )
        sys.exit(1)

    match = matches[0]
    branch, path = match["branch"], match["path"]

    if not path:
        print(f"ERROR: Could not determine path for worktree '{branch}'.", file=sys.stderr)
        sys.exit(1)

    main_branch = get_main_branch(worktrees)
    if not main_branch:
        print("ERROR: Could not determine the main branch from 'wt list'.", file=sys.stderr)
        sys.exit(1)

    if not is_merged(path, branch, main_branch):
        print(
            f"Branch '{branch}' is not yet merged into '{main_branch}'. "
            f"Merge it first, then re-run finish-issue.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Branch '{branch}' is merged into '{main_branch}'.")

    force_remove = False
    if is_dirty(path):
        choice = resolve_dirty_choice(prompt_dirty_tree_choice(branch))
        if choice == "abort":
            print(
                f"Aborted: worktree '{path}' has uncommitted changes. "
                f"Commit, stash, or discard them, then re-run finish-issue.",
                file=sys.stderr,
            )
            sys.exit(1)
        force_remove = True

    if args.prepare:
        ok = _persist_branch_for_shell(main_branch)
        ok = _persist_worktree_for_shell(branch) and ok
        ok = _clear_force_marker_for_shell() and ok
        if force_remove:
            ok = _persist_force_for_shell() and ok
            ok = _persist_worktree_path_for_shell(path) and ok
        remove_issue_context(path)
        sys.exit(0 if ok else 1)

    if _cwd_inside_worktree(path):
        issue_id = issue["id"]
        print(
            f"ERROR: You are currently inside the worktree for '{branch}' ({path}), "
            f"and finish-issue was invoked without shell integration (a plain Python "
            f"subprocess can never change your shell's directory). Removing it now "
            f"would leave your shell pointed at a deleted git worktree.\n\n"
            f"Fix: restart your shell (or run 'source ~/.zshrc' / 'source ~/.bashrc') "
            f"so it picks up the finish-issue shell function, then re-run "
            f"'finish-issue {issue_id}'. If the shell function isn't installed yet, "
            f"run the shell installer first (e.g. 'finish-issue/install.sh') and THEN "
            f"restart your shell — re-running the installer alone will not update a "
            f"terminal that is already open.\n"
            f"Alternatively, 'cd' out of this worktree first and re-run finish-issue.",
            file=sys.stderr,
        )
        sys.exit(1)

    remove_issue_context(path)
    print(f"Removing worktree...")
    if force_remove:
        # Pre-clean uncommitted changes so wt remove can proceed without --force,
        # preserving wt's own unmerged-branch guard (--force would bypass it).
        subprocess.run(
            ["git", "-C", path, "reset", "--hard", "HEAD"],
            capture_output=True, check=False,
        )
        subprocess.run(
            ["git", "-C", path, "clean", "-fd"],
            capture_output=True, check=False,
        )
    cmd = ["wt", "remove", branch]
    result = subprocess.run(cmd, stdout=None, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"ERROR: '{' '.join(cmd)}' failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"Removed worktree and branch '{branch}'.")
    _persist_branch_for_shell(main_branch)


if __name__ == "__main__":
    main()

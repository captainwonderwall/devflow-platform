#!/usr/bin/env python3
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)   # Homebrew: shared/ is sibling of continue-issue.py
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)    # Dev: shared/ is at repo root

from devflow_sdk.core.prompts import select
from devflow_sdk.core.shell_function_check import check_shell_function
from devflow_sdk.core.git.worktree import _cwd_inside_worktree
from devflow_sdk.domain.workspace import check_manager, find_for_issue
from devflow_sdk.domain.ide import prompt_and_open_ide
from devflow_sdk.core.git.shell_state import _persist_continue_branch_for_shell
from devflow_sdk.worktree_state import list_tracked_worktrees


def main():
    parser = argparse.ArgumentParser(
        description="Continue work on an issue by switching to its worktree."
    )
    parser.add_argument(
        "issue",
        nargs="?",
        default=None,
        help="JIRA issue key (e.g. VDP-46625) or GitHub issue number (e.g. 33). "
             "If omitted, a picker is shown.",
    )
    args = parser.parse_args()

    check_manager()
    check_shell_function(
        "# >>> continue-issue shell integration >>>",
        f"ERROR: continue-issue shell function is not installed or is out of date.\n"
        f"Re-run the installer: {os.path.join(SCRIPT_DIR, 'install.sh')}\n"
        "Then restart your shell or run: source {rc_path}",
        required_content=["command continue-issue", ".continue-issue-branch"],
    )

    tracked = list_tracked_worktrees()

    if args.issue:
        issue_arg = args.issue.strip()
        matches = [e for e in tracked if e.ticket_id.lower() == issue_arg.lower()]
        if not matches:
            print(f"ERROR: No tracked worktree found for '{issue_arg}'.", file=sys.stderr)
            print(f"Run 'start-issue {issue_arg}' to create a worktree for it.", file=sys.stderr)
            sys.exit(1)
        entry = matches[0]
    else:
        available = [e for e in tracked if not _cwd_inside_worktree(e.path)]
        if not available:
            print("No other tracked worktrees found.")
            sys.exit(0)
        labels = [f"{e.ticket_id} ({e.source}) → {e.path}" for e in available]
        label_to_entry = dict(zip(labels, available))
        chosen_label = select("Select a worktree to continue:", labels, single=True)
        if chosen_label is None:
            sys.exit(1)
        entry = label_to_entry[chosen_label]

    workspace_matches = find_for_issue(entry.ticket_id, entry.source)
    if not workspace_matches:
        print(
            f"ERROR: Worktree for '{entry.ticket_id}' is tracked in state but not found in git. "
            f"It may have been removed manually.",
            file=sys.stderr,
        )
        sys.exit(1)

    workspace = workspace_matches[0]
    branch = workspace.branch
    path = workspace.path or entry.path

    prompt_and_open_ide(path)

    if not _persist_continue_branch_for_shell(branch):
        sys.exit(1)

    print(f"Switching to worktree for '{entry.ticket_id}'...")


if __name__ == "__main__":
    main()

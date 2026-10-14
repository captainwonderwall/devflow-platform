#!/usr/bin/env python3
import argparse
import atexit
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)   # Homebrew: shared/ is sibling of finish-issue.py
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)    # Dev: shared/ is at repo root

from devflow_sdk.domain.issue import fetch, remove_issue_context
from devflow_sdk.domain.ide import close_intellij_project
from devflow_sdk.core.prompts import select, checkbox
from devflow_sdk.worktree_state import list_tracked_worktrees
from devflow_sdk.core.shell_function_check import check_shell_function
from devflow_sdk.core.git.worktree import query_worktrees, is_dirty, _cwd_inside_worktree
from devflow_sdk.domain.workspace import check_manager, find_for_issue
from devflow_sdk.core.git.shell_state import (
    _persist_branch_for_shell,
    _persist_worktree_for_shell,
    _persist_force_for_shell,
    _persist_force_delete_for_shell,
    _persist_worktree_path_for_shell,
    _clear_force_marker_for_shell,
)
from devflow_sdk.core.git.merge_check import get_main_branch, is_merged, _branch_from_origin_head
from devflow_sdk.worktree_state import remove_worktree
from devflow_sdk.core.ui import status, success, error, info
from devflow_sdk.core.summary import summary



DIRTY_ABORT = "Abort"
DIRTY_DROP = "Drop uncommitted changes and continue"

UNMERGED_ABORT = "Abort"
UNMERGED_FORCE = "Force delete (branch not merged)"

INTELLIJ_CONTINUE = "Continue anyway (IntelliJ stays open)"
INTELLIJ_SKIP = "Skip this issue"


def resolve_dirty_choice(choice):
    """Map the raw questionary.select() return value to 'abort' or 'drop'.
    Ctrl+C returns None from questionary, which we treat as 'abort'."""
    if choice == DIRTY_DROP:
        return "drop"
    return "abort"


def resolve_unmerged_choice(choice):
    """Map the raw questionary.select() return value to 'abort' or 'force'.
    Ctrl+C returns None from questionary, which we treat as 'abort'."""
    if choice == UNMERGED_FORCE:
        return "force"
    return "abort"


def prompt_dirty_tree_choice(branch):
    return select(
        f"Worktree for '{branch}' has uncommitted changes. What do you want to do?",
        [DIRTY_ABORT, DIRTY_DROP],
        single=True,
    )


def prompt_unmerged_choice(branch, main_branch):
    return select(
        f"Branch '{branch}' is not yet merged into '{main_branch}'. What do you want to do?",
        [UNMERGED_ABORT, UNMERGED_FORCE],
        single=True,
    )


def _close_intellij_for_issue(path, issue_id):
    """
    Attempt to close IntelliJ IDEA for the worktree at `path`.
    Returns True to continue processing the issue, False to skip it.
    """
    result = close_intellij_project(path)
    if result == "not_running":
        return True
    if result == "closed":
        status("Closed IntelliJ IDEA project.")
        return True
    choice = select(
        f"Could not close IntelliJ IDEA for '{issue_id}'. What would you like to do?",
        [INTELLIJ_CONTINUE, INTELLIJ_SKIP],
        single=True,
    )
    return choice == INTELLIJ_CONTINUE


def _finish_one(issue_id, issue_source, branch, path, main_branch, prepare):
    """
    Execute merge/dirty checks and worktree removal for a single issue.
    Returns True on success, False if the user aborted.
    """
    force_delete = False
    if not is_merged(path, branch, main_branch):
        choice = resolve_unmerged_choice(prompt_unmerged_choice(branch, main_branch))
        if choice == "abort":
            error(f"Aborted: branch '{branch}' is not yet merged into '{main_branch}'. "
                  f"Merge it first, or re-run finish-issue and choose force delete.")
            return False
        force_delete = True
    else:
        status(f"Branch '{branch}' is merged into '{main_branch}'.")

    force_remove = False
    if is_dirty(path):
        choice = resolve_dirty_choice(prompt_dirty_tree_choice(branch))
        if choice == "abort":
            error(f"Aborted: worktree '{path}' has uncommitted changes. "
                  f"Commit, stash, or discard them, then re-run finish-issue.")
            return False
        force_remove = True

    if prepare:
        ok = _persist_branch_for_shell(main_branch)
        ok = _persist_worktree_for_shell(branch) and ok
        ok = _clear_force_marker_for_shell() and ok
        if force_remove:
            ok = _persist_force_for_shell() and ok
        if force_delete:
            ok = _persist_force_delete_for_shell() and ok
        ok = _persist_worktree_path_for_shell(path) and ok
        remove_issue_context(path)
        remove_worktree(path)
        return ok

    if _cwd_inside_worktree(path):
        error(f"You are currently inside the worktree for '{branch}' ({path}), "
              f"and finish-issue was invoked without shell integration (a plain Python "
              f"subprocess can never change your shell's directory). Removing it now "
              f"would leave your shell pointed at a deleted git worktree.\n\n"
              f"Fix: restart your shell (or run 'source ~/.zshrc' / 'source ~/.bashrc') "
              f"so it picks up the finish-issue shell function, then re-run "
              f"'finish-issue {issue_id}'. If the shell function isn't installed yet, "
              f"run the shell installer first (e.g. 'finish-issue/install.sh') and THEN "
              f"restart your shell — re-running the installer alone will not update a "
              f"terminal that is already open.\n"
              f"Alternatively, 'cd' out of this worktree first and re-run finish-issue.")
        return False

    remove_issue_context(path)
    remove_worktree(path)
    status(f"Removing worktree...")
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
    cmd = ["wt", "remove"] + (["--force"] if force_delete else []) + [branch]
    result = subprocess.run(cmd, stdout=None, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        error(f"'{' '.join(cmd)}' failed:\n{result.stderr}")
        return False

    # wt remove deletes tracked files but may leave gitignored files (e.g. .idea/).
    # Remove the directory entirely if it still exists.
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)

    success(f"Removed worktree and branch '{branch}'.")
    summary.add("Branch deleted", branch)
    summary.add("Worktree removed", path)
    _persist_branch_for_shell(main_branch)
    return True


def main():
    atexit.register(summary.print_summary)

    parser = argparse.ArgumentParser(
        description="Finish one or more JIRA or GitHub issues by removing their worktrees "
                     "once the associated branches have been merged."
    )
    parser.add_argument(
        "issue",
        nargs="*",
        default=None,
        help="JIRA issue key (e.g. VDP-46625) or GitHub issue number (e.g. 33). "
             "Accepts multiple keys to finish a batch. "
             "If omitted, the issue is read from the worktree's stored context.",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    check_manager()
    check_shell_function(
        "# >>> finish-issue shell integration >>>",
        f"ERROR: finish-issue shell function is not installed or is out of date.\n"
        f"Re-run the installer: {os.path.join(SCRIPT_DIR, 'install.sh')}\n"
        "Then restart your shell or run: source {rc_path}",
        required_content=["command finish-issue --prepare", ".finish-issue-force", "finish-issue-worktree-path", 'rm -rf "$_worktree_path"', "finish-issue-force-delete", "wt -C"],
    )

    tracked = list_tracked_worktrees()

    # ── Resolve which issues to process ──────────────────────────────────────
    if args.issue:
        issues_to_process = []
        for key in args.issue:
            issue = fetch(key)
            issues_to_process.append((issue['id'], issue['source']))
            info(f"Issue: {issue['source'].upper()} {issue['id']}: {issue['title']}")
    else:
        cwd_entry = next(
            (e for e in tracked if _cwd_inside_worktree(e.path)),
            None,
        )
        if cwd_entry is not None:
            issues_to_process = [(cwd_entry.ticket_id, cwd_entry.source)]
            info(f"Issue: {cwd_entry.source.upper()} {cwd_entry.ticket_id}")
        else:
            if not tracked:
                info("No tracked worktrees found.")
                sys.exit(0)
            labels = [f"{e.ticket_id} ({e.source}) → {e.path}" for e in tracked]
            label_to_entry = {f"{e.ticket_id} ({e.source}) → {e.path}": e for e in tracked}
            chosen_labels = checkbox("Select worktrees to finish:", labels)
            if chosen_labels is None:
                sys.exit(1)
            issues_to_process = []
            for label in chosen_labels:
                entry = label_to_entry[label]
                issues_to_process.append((entry.ticket_id, entry.source))
                info(f"Issue: {entry.source.upper()} {entry.ticket_id}")

    multi = len(issues_to_process) > 1
    # --prepare (shell cwd-switch) only applies when finishing a single issue.
    use_prepare = args.prepare and not multi

    # ── Process each issue ───────────────────────────────────────────────────
    skipped = []

    for issue_id, issue_source in issues_to_process:
        if multi:
            info(f"\n--- {issue_source.upper()} {issue_id} ---")

        worktrees = query_worktrees()

        if worktrees is not None:
            matches = find_for_issue(issue_id, issue_source)
            if not matches:
                error(f"No worktree found matching issue '{issue_id}'.")
                skipped.append(issue_id)
                continue
            if len(matches) > 1:
                error(f"Multiple worktrees match issue '{issue_id}':")
                for m in matches:
                    error(f"  {m.branch} -> {m.path}")
                error("Please remove the correct one manually, e.g.: wt remove <branch>")
                skipped.append(issue_id)
                continue
            match = matches[0]
            branch, path = match.branch, match.path
            if not path:
                error(f"Could not determine path for worktree '{branch}'.")
                skipped.append(issue_id)
                continue
        else:
            state_entry = next(
                (e for e in tracked if e.ticket_id.lower() == issue_id.lower()),
                None,
            )
            if state_entry is None:
                error(f"No tracked worktree found for '{issue_id}'.")
                skipped.append(issue_id)
                continue
            path = state_entry.path
            _branch_result = subprocess.run(
                ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True,
            )
            if _branch_result.returncode != 0 or not _branch_result.stdout.strip():
                error(f"Could not determine branch for worktree at '{path}'.")
                skipped.append(issue_id)
                continue
            branch = _branch_result.stdout.strip()

        if worktrees is not None:
            main_branch = get_main_branch(worktrees, path)
        else:
            _main_result = subprocess.run(
                ["git", "-C", path, "rev-parse", "--abbrev-ref", "origin/HEAD"],
                capture_output=True, text=True,
            )
            ref = _main_result.stdout.strip() if _main_result.returncode == 0 else ""
            main_branch = _branch_from_origin_head(ref)

        if not main_branch:
            error(f"Could not determine the main branch for '{issue_id}'.")
            skipped.append(issue_id)
            continue

        if not _close_intellij_for_issue(path, issue_id):
            skipped.append(issue_id)
            continue

        if not _finish_one(issue_id, issue_source, branch, path, main_branch, use_prepare):
            skipped.append(issue_id)

    if skipped:
        if multi:
            error(f"\nSkipped {len(skipped)} issue(s): {', '.join(skipped)}")
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()

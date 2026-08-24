import os
import sys


def _persist_branch_for_shell(branch):
    branch_file = os.path.join(os.path.expanduser("~"), ".finish-issue-branch")
    try:
        with open(branch_file, "w") as f:
            f.write(branch)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist branch name for shell: {e}\n"
            "The worktree was removed successfully, but shell integration will not "
            "switch back to the main branch automatically.",
            file=sys.stderr,
        )
        return False


def _persist_worktree_for_shell(worktree_name):
    remove_file = os.path.join(os.path.expanduser("~"), ".finish-issue-remove")
    try:
        with open(remove_file, "w") as f:
            f.write(worktree_name)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist worktree name for shell: {e}\n"
            f"Run 'wt remove {worktree_name}' manually.",
            file=sys.stderr,
        )
        return False


def _persist_force_for_shell():
    force_file = os.path.join(os.path.expanduser("~"), ".finish-issue-force")
    try:
        open(force_file, "w").close()
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist force-remove flag for shell: {e}\n"
            f"Pre-cleaning uncommitted changes before 'wt remove' will be skipped; "
            f"'wt remove' may then refuse to proceed.",
            file=sys.stderr,
        )
        return False


def _persist_worktree_path_for_shell(path):
    path_file = os.path.join(os.path.expanduser("~"), ".finish-issue-worktree-path")
    try:
        with open(path_file, "w") as f:
            f.write(path)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist worktree path for shell: {e}\n"
            f"Pre-cleaning uncommitted changes before 'wt remove' will be skipped; "
            f"'wt remove' may then refuse to proceed.",
            file=sys.stderr,
        )
        return False


def _clear_force_marker_for_shell():
    force_file = os.path.join(os.path.expanduser("~"), ".finish-issue-force")
    path_file = os.path.join(os.path.expanduser("~"), ".finish-issue-worktree-path")
    try:
        for f in (force_file, path_file):
            if os.path.exists(f):
                os.remove(f)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not clear stale force-remove marker for shell: {e}\n"
            f"A previous run's --force choice may incorrectly apply to this run; "
            f"remove ~/.finish-issue-force manually if 'wt remove' behaves unexpectedly.",
            file=sys.stderr,
        )
        return False

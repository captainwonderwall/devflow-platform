# devflow_sdk/core/git/shell_state.py
import os
import sys


def _persist_continue_branch_for_shell(branch: str, path: str) -> bool:
    """Write the selected branch and worktree path for shell integration."""
    branch_file = os.path.join(os.path.expanduser("~"), ".continue-issue-branch")
    path_file = os.path.join(os.path.expanduser("~"), ".continue-issue-worktree-path")
    try:
        if os.path.exists(branch_file):
            os.remove(branch_file)
        with open(path_file, "w") as f:
            f.write(path)
        with open(branch_file, "w") as f:
            f.write(branch)
        return True
    except OSError as e:
        for marker in (branch_file, path_file):
            try:
                os.remove(marker)
            except OSError:
                pass
        print(
            f"WARNING: Could not persist worktree selection for shell: {e}\n"
            "The worktree was found successfully, but shell integration will not "
            "switch to it automatically.",
            file=sys.stderr,
        )
        return False


def _persist_start_branch_for_shell(branch: str, path: str) -> bool:
    """Write the new branch and worktree path for shell integration."""
    branch_file = os.path.join(os.path.expanduser("~"), ".start-issue-branch")
    path_file = os.path.join(os.path.expanduser("~"), ".start-issue-worktree-path")
    try:
        if os.path.exists(branch_file):
            os.remove(branch_file)
        with open(path_file, "w") as f:
            f.write(path)
        with open(branch_file, "w") as f:
            f.write(branch)
        return True
    except OSError as e:
        for marker in (branch_file, path_file):
            try:
                os.remove(marker)
            except OSError:
                pass
        print(
            f"WARNING: Could not persist worktree selection for shell: {e}\n"
            "The worktree was created successfully, but shell integration will not "
            "switch to it automatically.",
            file=sys.stderr,
        )
        return False


def _persist_branch_for_shell(branch: str) -> bool:
    """Write main branch to ~/.finish-issue-branch for shell integration."""
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


def _persist_worktree_for_shell(worktree_name: str) -> bool:
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


def _persist_force_for_shell() -> bool:
    force_file = os.path.join(os.path.expanduser("~"), ".finish-issue-force")
    try:
        open(force_file, "w").close()
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist force-remove flag for shell: {e}\n"
            "Pre-cleaning uncommitted changes before 'wt remove' will be skipped.",
            file=sys.stderr,
        )
        return False


def _persist_force_delete_for_shell() -> bool:
    force_delete_file = os.path.join(os.path.expanduser("~"), ".finish-issue-force-delete")
    try:
        open(force_delete_file, "w").close()
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist force-delete flag for shell: {e}\n"
            "The 'wt remove --force' flag will not be passed; removal may fail for unmerged branches.",
            file=sys.stderr,
        )
        return False


def _persist_worktree_path_for_shell(path: str) -> bool:
    path_file = os.path.join(os.path.expanduser("~"), ".finish-issue-worktree-path")
    try:
        with open(path_file, "w") as f:
            f.write(path)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist worktree path for shell: {e}\n"
            "Pre-cleaning uncommitted changes before 'wt remove' will be skipped.",
            file=sys.stderr,
        )
        return False


def _clear_force_marker_for_shell() -> bool:
    force_file = os.path.join(os.path.expanduser("~"), ".finish-issue-force")
    force_delete_file = os.path.join(os.path.expanduser("~"), ".finish-issue-force-delete")
    path_file = os.path.join(os.path.expanduser("~"), ".finish-issue-worktree-path")
    try:
        for f in (force_file, force_delete_file, path_file):
            if os.path.exists(f):
                os.remove(f)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not clear stale force-remove marker for shell: {e}",
            file=sys.stderr,
        )
        return False

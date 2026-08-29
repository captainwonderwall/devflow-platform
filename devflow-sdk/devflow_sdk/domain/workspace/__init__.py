from devflow_sdk.core.branch_name import parse_branch
from devflow_sdk.core.git import check_worktrunk
from devflow_sdk.core.git.worktree import create_worktree, list_worktrees


def check_manager() -> None:
    """Exit with install hint if the workspace manager (wt) is not available."""
    check_worktrunk()


def create(branch: str) -> str | None:
    """Create or switch to a worktree for branch. Returns the worktree path."""
    return create_worktree(branch)


def find_for_issue(issue_id: str, source: str) -> list[dict]:
    """Return worktrees whose branch matches issue_id and source.

    source is 'github' or 'jira'. Excludes the main worktree.
    """
    worktrees = list_worktrees()
    matches = []
    for wt in worktrees:
        if wt.get("is_main"):
            continue
        branch = wt.get("branch")
        parsed = parse_branch(branch)
        if (parsed
                and parsed["source"] == source
                and parsed["id"].lower() == str(issue_id).lower()):
            matches.append({"branch": branch, "path": wt.get("path")})
    return matches


def list_workspaces() -> list:
    """Return all non-main worktrees."""
    return [wt for wt in list_worktrees() if not wt.get("is_main")]

from dataclasses import dataclass

from devflow_sdk.core.branch_name import parse_branch
from devflow_sdk.core.git import check_worktrunk
from devflow_sdk.core.git.worktree import create_worktree, list_worktrees


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    """A normalized worktree record exposed by the workspace domain."""

    branch: str | None
    path: str | None
    is_main: bool

    @classmethod
    def from_worktree(cls, worktree: dict) -> "Workspace":
        """Normalize one raw worktrunk record at the domain boundary."""
        branch = worktree.get("branch")
        return cls(
            branch=branch if isinstance(branch, str) else None,
            path=worktree.get("path") if isinstance(worktree.get("path"), str) else None,
            is_main=bool(worktree.get("is_main")),
        )

    def matches_issue(self, issue_id: str, source: str) -> bool:
        """Return whether this non-main workspace belongs to an issue."""
        if self.is_main or self.branch is None:
            return False
        parsed = parse_branch(self.branch)
        return bool(
            parsed
            and parsed["source"] == source.lower()
            and parsed["id"].lower() == str(issue_id).lower()
        )

    def __getitem__(self, key: str) -> str | bool | None:
        """Keep the established mapping-shaped SDK boundary during migration."""
        if key not in {"branch", "path", "is_main"}:
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default: object = None) -> str | bool | object:
        """Provide dict-like access for existing CLI consumers."""
        try:
            return self[key]
        except KeyError:
            return default


def _workspaces() -> list[Workspace]:
    """Load and normalize worktrees once at the domain boundary."""
    return [Workspace.from_worktree(worktree) for worktree in list_worktrees()]


def check_manager() -> None:
    """Exit with install hint if the workspace manager (wt) is not available."""
    check_worktrunk()


def create(branch: str) -> str | None:
    """Create or switch to a worktree for branch. Returns the worktree path."""
    return create_worktree(branch)


def find_for_issue(issue_id: str, source: str) -> list[Workspace]:
    """Return worktrees whose branch matches issue_id and source.

    source is 'github' or 'jira'. Excludes the main worktree.
    """
    return [
        workspace
        for workspace in _workspaces()
        if workspace.matches_issue(issue_id, source)
    ]


def list_workspaces() -> list[Workspace]:
    """Return all non-main worktrees."""
    return [workspace for workspace in _workspaces() if not workspace.is_main]


__all__ = [
    "Workspace",
    "check_manager",
    "create",
    "find_for_issue",
    "list_workspaces",
]

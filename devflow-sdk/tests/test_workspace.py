from unittest.mock import patch, MagicMock
import pytest
from devflow_sdk.domain.workspace import Workspace, create, find_for_issue, list_workspaces


FAKE_WORKTREES = [
    {"is_main": True, "branch": "main", "path": "/repo"},
    {"is_main": False, "branch": "feat/gh42-my-feature", "path": "/repo/feat-gh42"},
    {"is_main": False, "branch": "fix/gh99-other-bug", "path": "/repo/fix-gh99"},
    {"is_main": False, "branch": "fix/jira-VDP-123-jira-issue", "path": "/repo/fix-VDP-123"},
]


def test_find_for_issue_github_matches():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("42", "github")
    assert len(result) == 1
    assert result[0].branch == "feat/gh42-my-feature"
    assert result[0].path == "/repo/feat-gh42"


def test_find_for_issue_jira_matches():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("VDP-123", "jira")
    assert len(result) == 1
    assert result[0].branch == "fix/jira-VDP-123-jira-issue"


def test_find_for_issue_no_match_returns_empty():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("999", "github")
    assert result == []


def test_find_for_issue_excludes_main_worktree():
    worktrees = [{"is_main": True, "branch": "main", "path": "/repo"}]
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=worktrees):
        result = find_for_issue("42", "github")
    assert result == []


def test_find_for_issue_case_insensitive():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("vdp-123", "jira")
    assert len(result) == 1


def test_list_workspaces_excludes_main():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = list_workspaces()
    assert all(not workspace.is_main for workspace in result)
    assert len(result) == 3


def test_workspace_normalizes_adapter_record():
    workspace = Workspace._from_worktree({"branch": 42, "path": None, "is_main": 1})
    assert workspace.branch is None
    assert workspace.path is None
    assert workspace.is_main is True


def test_create_returns_workspace():
    with patch("devflow_sdk.domain.workspace.create_worktree", return_value="/repo/feature"):
        result = create("feat/wt/gh42-feature")
    assert result == Workspace(
        branch="feat/wt/gh42-feature",
        path="/repo/feature",
        is_main=False,
    )


def test_create_returns_none_when_adapter_does_not_return_path():
    with patch("devflow_sdk.domain.workspace.create_worktree", return_value=None):
        assert create("feat/wt/gh42-feature") is None


def test_create_passes_base_to_wt_switch_create():
    """When base is provided, --base <base> is passed to wt switch --create."""
    with patch("devflow_sdk.core.git.worktree._branch_exists_locally", return_value=False), \
         patch("devflow_sdk.core.git.worktree._find_worktree_path", return_value="/repos/wt/child"), \
         patch("devflow_sdk.core.git.worktree.subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
        result = create("feat/wt/child-branch", base="feat/wt/parent-branch")
    call_args = mock_run.call_args[0][0]
    assert "--base" in call_args
    assert "feat/wt/parent-branch" in call_args


def test_create_without_base_omits_base_flag():
    """When base is not provided, --base is not passed to wt switch --create."""
    with patch("devflow_sdk.core.git.worktree._branch_exists_locally", return_value=False), \
         patch("devflow_sdk.core.git.worktree._find_worktree_path", return_value="/repos/wt/child"), \
         patch("devflow_sdk.core.git.worktree.subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
        result = create("feat/wt/child-branch")
    call_args = mock_run.call_args[0][0]
    assert "--base" not in call_args

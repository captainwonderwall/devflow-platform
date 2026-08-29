from unittest.mock import patch
import pytest
from devflow_sdk.domain.workspace import find_for_issue, list_workspaces


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
    assert result[0]["branch"] == "feat/gh42-my-feature"
    assert result[0]["path"] == "/repo/feat-gh42"


def test_find_for_issue_jira_matches():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("VDP-123", "jira")
    assert len(result) == 1
    assert result[0]["branch"] == "fix/jira-VDP-123-jira-issue"


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
    assert all(not wt.get("is_main") for wt in result)
    assert len(result) == 3

# devflow-sdk/tests/test_worktree.py
import json
from unittest.mock import patch, MagicMock
import pytest

from devflow_sdk.core.git.worktree import (
    query_worktrees, list_worktrees, is_dirty, get_repo_root,
)
from devflow_sdk.core.git import check_worktrunk


def test_query_worktrees_returns_parsed_json():
    fake_output = json.dumps([{"branch": "main", "is_main": True}])
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
        result = query_worktrees()
    assert result == [{"branch": "main", "is_main": True}]


def test_query_worktrees_returns_none_on_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = query_worktrees()
    assert result is None


def test_is_dirty_true_when_porcelain_has_output():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=" M somefile.py\n")
        assert is_dirty("/some/path") is True


def test_is_dirty_false_when_clean():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert is_dirty("/some/path") is False


def test_check_worktrunk_exits_when_wt_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SystemExit):
            check_worktrunk()

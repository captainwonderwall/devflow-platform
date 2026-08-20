import json
import subprocess
import unittest
from unittest.mock import patch, MagicMock


from devflow_sdk.worktrunk import check_worktrunk, list_worktrees, query_worktrees

_WORKTREES = [
    {"branch": "main", "path": "/repos/main", "is_main": True},
    {"branch": "feat/wt/gh33-add-finish-issue-script", "path": "/repos/33", "is_main": False},
]


class TestCheckWorktrunk(unittest.TestCase):
    def test_exits_when_wt_not_found(self):
        with patch("devflow_sdk.worktrunk.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(SystemExit):
                check_worktrunk()

    def test_exits_when_wt_fails(self):
        with patch("devflow_sdk.worktrunk.subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, "wt")):
            with self.assertRaises(SystemExit):
                check_worktrunk()

    def test_succeeds_when_wt_found(self):
        with patch("devflow_sdk.worktrunk.subprocess.run", return_value=MagicMock(returncode=0)):
            check_worktrunk()  # must not raise


class TestQueryWorktrees(unittest.TestCase):
    def test_returns_parsed_json(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=0, stdout=json.dumps(_WORKTREES)),
        ):
            result = query_worktrees()
        self.assertEqual(result, _WORKTREES)

    def test_returns_none_on_failure(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=1, stderr="boom"),
        ):
            self.assertIsNone(query_worktrees())

    def test_returns_none_on_invalid_json(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="not json"),
        ):
            self.assertIsNone(query_worktrees())

    def test_returns_none_when_wt_not_found(self):
        with patch("devflow_sdk.worktrunk.subprocess.run", side_effect=FileNotFoundError):
            self.assertIsNone(query_worktrees())


class TestListWorktrees(unittest.TestCase):
    def test_returns_parsed_json(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=0, stdout=json.dumps(_WORKTREES)),
        ):
            result = list_worktrees()
        self.assertEqual(result, _WORKTREES)

    def test_exits_on_failure(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=1, stderr="boom"),
        ):
            with self.assertRaises(SystemExit):
                list_worktrees()

    def test_exits_on_invalid_json(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="not json"),
        ):
            with self.assertRaises(SystemExit):
                list_worktrees()

    def test_exits_when_wt_not_found(self):
        with patch("devflow_sdk.worktrunk.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(SystemExit):
                list_worktrees()


if __name__ == "__main__":
    unittest.main()

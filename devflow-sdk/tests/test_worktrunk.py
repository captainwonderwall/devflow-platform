import json
import subprocess
import unittest
from unittest.mock import patch, MagicMock


from devflow_sdk.worktrunk import (
    check_worktrunk, list_worktrees, query_worktrees,
    _branch_matches, find_matching_worktrees, is_dirty,
)

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


_FULL_WORKTREES = [
    {"branch": "main", "path": "/repos/main", "is_main": True},
    {"branch": "feat/wt/gh33-add-finish-issue-script", "path": "/repos/33", "is_main": False},
    {"branch": "feat/wt/gh330-unrelated-issue", "path": "/repos/330", "is_main": False},
    {"branch": "fix/wt/jira-VDP-46625-jira-thing", "path": "/repos/jira", "is_main": False},
]


class TestBranchMatches(unittest.TestCase):
    def test_github_numeric_exact_match(self):
        self.assertTrue(_branch_matches("feat/gh33-add-finish-issue-script", "33", "github"))

    def test_github_numeric_does_not_match_different_number(self):
        self.assertFalse(_branch_matches("feat/gh33-add-finish-issue-script", "3", "github"))

    def test_jira_key_match_case_insensitive_branch(self):
        self.assertTrue(_branch_matches("fix/jira-vdp-46625-jira-thing", "VDP-46625", "jira"))

    def test_no_match(self):
        self.assertFalse(_branch_matches("feat/gh99-other", "33", "github"))

    def test_none_branch_returns_false(self):
        self.assertFalse(_branch_matches(None, "33", "github"))

    def test_source_mismatch_returns_false(self):
        self.assertFalse(_branch_matches("feat/gh42-add-export-button", "42", "jira"))

    def test_old_format_branch_returns_false(self):
        self.assertFalse(_branch_matches("feat/33-add-finish-issue-script", "33", "github"))


class TestFindMatchingWorktrees(unittest.TestCase):
    def test_finds_exact_github_issue_excluding_main(self):
        matches = find_matching_worktrees("33", "github", worktrees=_FULL_WORKTREES)
        self.assertEqual(matches, [{"branch": "feat/wt/gh33-add-finish-issue-script", "path": "/repos/33"}])

    def test_finds_jira_issue(self):
        matches = find_matching_worktrees("VDP-46625", "jira", worktrees=_FULL_WORKTREES)
        self.assertEqual(matches, [{"branch": "fix/wt/jira-VDP-46625-jira-thing", "path": "/repos/jira"}])

    def test_no_matches_returns_empty_list(self):
        matches = find_matching_worktrees("999", "github", worktrees=_FULL_WORKTREES)
        self.assertEqual(matches, [])

    def test_calls_list_worktrees_when_not_provided(self):
        with patch("devflow_sdk.worktrunk.list_worktrees", return_value=_FULL_WORKTREES) as mock_list:
            matches = find_matching_worktrees("33", "github")
        mock_list.assert_called_once()
        self.assertEqual(matches, [{"branch": "feat/wt/gh33-add-finish-issue-script", "path": "/repos/33"}])


class TestIsDirty(unittest.TestCase):
    def test_returns_true_when_status_has_output(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=0, stdout=" M some/file.py\n"),
        ) as mock_run:
            self.assertTrue(is_dirty("/repos/feat-52"))
        mock_run.assert_called_once_with(
            ["git", "-C", "/repos/feat-52", "status", "--porcelain"],
            capture_output=True, text=True,
        )

    def test_returns_false_when_status_is_empty(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=0, stdout=""),
        ):
            self.assertFalse(is_dirty("/repos/feat-52"))

    def test_returns_false_when_status_is_only_whitespace(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="\n"),
        ):
            self.assertFalse(is_dirty("/repos/feat-52"))

    def test_returns_false_on_git_failure(self):
        with patch(
            "devflow_sdk.worktrunk.subprocess.run",
            return_value=MagicMock(returncode=128, stdout=""),
        ):
            self.assertFalse(is_dirty("/repos/missing"))

    def test_returns_false_on_oserror(self):
        with patch("devflow_sdk.worktrunk.subprocess.run", side_effect=OSError):
            self.assertFalse(is_dirty("/repos/missing"))


if __name__ == "__main__":
    unittest.main()

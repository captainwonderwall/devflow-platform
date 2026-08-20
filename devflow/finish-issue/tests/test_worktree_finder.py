import json
import sys
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

from worktree_finder import (
    check_worktrunk,
    list_worktrees,
    find_matching_worktrees,
    _branch_matches,
    _persist_branch_for_shell,
    _persist_worktree_for_shell,
    _persist_force_for_shell,
    _clear_force_marker_for_shell,
    is_dirty,
)

_WORKTREES = [
    {"branch": "main", "path": "/repos/main", "is_main": True},
    {"branch": "feat/wt/gh33-add-finish-issue-script", "path": "/repos/33", "is_main": False},
    {"branch": "feat/wt/gh330-unrelated-issue", "path": "/repos/330", "is_main": False},
    {"branch": "fix/wt/jira-VDP-46625-jira-thing", "path": "/repos/jira", "is_main": False},
]


class TestCheckWorktrunk(unittest.TestCase):
    def test_exits_when_wt_not_found(self):
        with patch("devflow_sdk.worktrunk.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(SystemExit):
                check_worktrunk()

    def test_succeeds_when_wt_found(self):
        with patch("devflow_sdk.worktrunk.subprocess.run", return_value=MagicMock(returncode=0)):
            check_worktrunk()  # must not raise


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
        # same id, wrong source: a jira key "42" shaped like a github id shouldn't match
        self.assertFalse(_branch_matches("feat/gh42-add-export-button", "42", "jira"))

    def test_old_format_branch_returns_false(self):
        self.assertFalse(_branch_matches("feat/33-add-finish-issue-script", "33", "github"))


class TestFindMatchingWorktrees(unittest.TestCase):
    def test_finds_exact_github_issue_excluding_main(self):
        matches = find_matching_worktrees("33", "github", worktrees=_WORKTREES)
        self.assertEqual(matches, [{"branch": "feat/wt/gh33-add-finish-issue-script", "path": "/repos/33"}])

    def test_finds_jira_issue(self):
        matches = find_matching_worktrees("VDP-46625", "jira", worktrees=_WORKTREES)
        self.assertEqual(matches, [{"branch": "fix/wt/jira-VDP-46625-jira-thing", "path": "/repos/jira"}])

    def test_no_matches_returns_empty_list(self):
        matches = find_matching_worktrees("999", "github", worktrees=_WORKTREES)
        self.assertEqual(matches, [])

    def test_calls_list_worktrees_when_not_provided(self):
        with patch("worktree_finder.list_worktrees", return_value=_WORKTREES) as mock_list:
            matches = find_matching_worktrees("33", "github")
        mock_list.assert_called_once()
        self.assertEqual(matches, [{"branch": "feat/wt/gh33-add-finish-issue-script", "path": "/repos/33"}])


class TestPersistBranchForShell(unittest.TestCase):
    def test_writes_branch_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("worktree_finder.os.path.expanduser", return_value=tmpdir):
                _persist_branch_for_shell("main")
            branch_file = os.path.join(tmpdir, ".finish-issue-branch")
            self.assertTrue(os.path.exists(branch_file))
            with open(branch_file) as f:
                self.assertEqual(f.read(), "main")

    def test_overwrites_stale_branch_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            branch_file = os.path.join(tmpdir, ".finish-issue-branch")
            with open(branch_file, "w") as f:
                f.write("old-branch")
            with patch("worktree_finder.os.path.expanduser", return_value=tmpdir):
                _persist_branch_for_shell("main")
            with open(branch_file) as f:
                self.assertEqual(f.read(), "main")

    def test_oserror_emits_warning_and_does_not_raise(self):
        with patch("builtins.open", side_effect=OSError("disk full")), \
             patch("sys.stderr") as mock_stderr:
            _persist_branch_for_shell("main")
        mock_stderr.write.assert_called()


class TestPersistWorktreeForShell(unittest.TestCase):
    def test_writes_branch_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("worktree_finder.os.path.expanduser", return_value=tmpdir):
                _persist_worktree_for_shell("feat/47-something")
            remove_file = os.path.join(tmpdir, ".finish-issue-remove")
            self.assertTrue(os.path.exists(remove_file))
            with open(remove_file) as f:
                self.assertEqual(f.read(), "feat/47-something")

    def test_overwrites_stale_remove_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            remove_file = os.path.join(tmpdir, ".finish-issue-remove")
            with open(remove_file, "w") as f:
                f.write("old-branch")
            with patch("worktree_finder.os.path.expanduser", return_value=tmpdir):
                _persist_worktree_for_shell("feat/47-something")
            with open(remove_file) as f:
                self.assertEqual(f.read(), "feat/47-something")

    def test_oserror_emits_warning_and_does_not_raise(self):
        with patch("builtins.open", side_effect=OSError("disk full")), \
             patch("sys.stderr") as mock_stderr:
            _persist_worktree_for_shell("feat/47-something")
        mock_stderr.write.assert_called()


class TestPersistForceForShell(unittest.TestCase):
    def test_writes_empty_marker_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("worktree_finder.os.path.expanduser", return_value=tmpdir):
                result = _persist_force_for_shell()
            force_file = os.path.join(tmpdir, ".finish-issue-force")
            self.assertTrue(os.path.exists(force_file))
            with open(force_file) as f:
                self.assertEqual(f.read(), "")
            self.assertTrue(result)

    def test_oserror_emits_warning_and_returns_false(self):
        with patch("builtins.open", side_effect=OSError("disk full")), \
             patch("sys.stderr") as mock_stderr:
            result = _persist_force_for_shell()
        mock_stderr.write.assert_called()
        self.assertFalse(result)


class TestClearForceMarkerForShell(unittest.TestCase):
    def test_removes_existing_marker_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            force_file = os.path.join(tmpdir, ".finish-issue-force")
            open(force_file, "w").close()
            with patch("worktree_finder.os.path.expanduser", return_value=tmpdir):
                result = _clear_force_marker_for_shell()
            self.assertFalse(os.path.exists(force_file))
            self.assertTrue(result)

    def test_noop_when_marker_file_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("worktree_finder.os.path.expanduser", return_value=tmpdir):
                result = _clear_force_marker_for_shell()
            self.assertTrue(result)

    def test_oserror_emits_warning_and_returns_false(self):
        with patch("worktree_finder.os.path.exists", return_value=True), \
             patch("worktree_finder.os.remove", side_effect=OSError("permission denied")), \
             patch("sys.stderr") as mock_stderr:
            result = _clear_force_marker_for_shell()
        mock_stderr.write.assert_called()
        self.assertFalse(result)


class TestIsDirty(unittest.TestCase):
    def test_returns_true_when_status_has_output(self):
        with patch(
            "worktree_finder.subprocess.run",
            return_value=MagicMock(returncode=0, stdout=" M some/file.py\n"),
        ) as mock_run:
            self.assertTrue(is_dirty("/repos/feat-52"))
        mock_run.assert_called_once_with(
            ["git", "-C", "/repos/feat-52", "status", "--porcelain"],
            capture_output=True, text=True,
        )

    def test_returns_false_when_status_is_empty(self):
        with patch(
            "worktree_finder.subprocess.run",
            return_value=MagicMock(returncode=0, stdout=""),
        ):
            self.assertFalse(is_dirty("/repos/feat-52"))

    def test_returns_false_when_status_is_only_whitespace(self):
        with patch(
            "worktree_finder.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="\n"),
        ):
            self.assertFalse(is_dirty("/repos/feat-52"))

    def test_returns_false_on_git_failure(self):
        with patch(
            "worktree_finder.subprocess.run",
            return_value=MagicMock(returncode=128, stdout=""),
        ):
            self.assertFalse(is_dirty("/repos/missing"))


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

from worktree import check_worktrunk, create_worktree, _persist_branch_for_shell

_WORKTREE_LIST_JSON = json.dumps([
    {"branch": "main", "path": "/repos/main"},
    {"branch": "feat/my-branch", "path": "/repos/feat/my-branch"},
])
_WORKTREE_LIST = json.loads(_WORKTREE_LIST_JSON)


def _make_run(create_rc=0, create_stderr="", switch_rc=0, switch_stderr="", branch_exists=False):
    def side_effect(cmd, **kwargs):
        if cmd[0] == "git" and "--list" in cmd:
            stdout = "  feat/my-branch" if branch_exists else ""
            return MagicMock(returncode=0, stdout=stdout)
        if cmd[0] == "wt" and "--create" in cmd:
            assert "--no-cd" in cmd, f"wt switch --create must include --no-cd, got: {cmd}"
            return MagicMock(returncode=create_rc, stderr=create_stderr)
        if cmd[0] == "wt" and "list" in cmd:
            return MagicMock(returncode=0, stdout=_WORKTREE_LIST_JSON)
        if cmd[0] == "wt":
            if "switch" in cmd:
                assert "--no-cd" in cmd, f"wt switch must include --no-cd, got: {cmd}"
            return MagicMock(returncode=switch_rc, stderr=switch_stderr)
        return MagicMock(returncode=0)
    return side_effect


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


class TestCreateWorktree(unittest.TestCase):
    def test_success_returns_worktree_path(self):
        with patch("worktree.subprocess.run", side_effect=_make_run()), \
             patch("worktree.query_worktrees", return_value=_WORKTREE_LIST):
            path = create_worktree("feat/my-branch")
        self.assertEqual(path, "/repos/feat/my-branch")

    def test_already_exists_user_confirms_returns_path(self):
        with patch("worktree.subprocess.run", side_effect=_make_run(branch_exists=True)), \
             patch("worktree.query_worktrees", return_value=_WORKTREE_LIST), \
             patch("worktree.confirm", return_value=True):
            path = create_worktree("feat/my-branch")
        self.assertEqual(path, "/repos/feat/my-branch")

    def test_already_exists_user_aborts_exits(self):
        with patch("worktree.subprocess.run", side_effect=_make_run(branch_exists=True)), \
             patch("worktree.confirm", return_value=False):
            with self.assertRaises(SystemExit):
                create_worktree("feat/my-branch")

    def test_already_exists_switch_fails_exits(self):
        with patch("worktree.subprocess.run", side_effect=_make_run(
            branch_exists=True, switch_rc=1,
        )), patch("worktree.confirm", return_value=True):
            with self.assertRaises(SystemExit):
                create_worktree("feat/my-branch")

    def test_general_error_exits(self):
        with patch("worktree.subprocess.run", side_effect=_make_run(create_rc=1)):
            with self.assertRaises(SystemExit):
                create_worktree("feat/my-branch")


class TestPersistBranchForShell(unittest.TestCase):
    def test_writes_branch_name_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("worktree.os.path.expanduser", return_value=tmpdir):
                _persist_branch_for_shell("feat/my-branch")
            branch_file = os.path.join(tmpdir, ".start-issue-branch")
            self.assertTrue(os.path.exists(branch_file))
            with open(branch_file) as f:
                self.assertEqual(f.read(), "feat/my-branch")

    def test_overwrites_stale_branch_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            branch_file = os.path.join(tmpdir, ".start-issue-branch")
            with open(branch_file, "w") as f:
                f.write("old-branch")
            with patch("worktree.os.path.expanduser", return_value=tmpdir):
                _persist_branch_for_shell("feat/new-branch")
            with open(branch_file) as f:
                self.assertEqual(f.read(), "feat/new-branch")

    def test_oserror_emits_warning_and_does_not_raise(self):
        with patch("builtins.open", side_effect=OSError("disk full")), \
             patch("sys.stderr") as mock_stderr:
            _persist_branch_for_shell("feat/my-branch")
        mock_stderr.write.assert_called()


if __name__ == "__main__":
    unittest.main()

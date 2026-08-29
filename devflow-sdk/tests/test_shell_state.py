import os
import sys
import tempfile
import unittest
from unittest.mock import patch


from devflow_sdk.core.git.shell_state import (
    _persist_branch_for_shell,
    _persist_worktree_for_shell,
    _persist_force_for_shell,
    _persist_worktree_path_for_shell,
    _clear_force_marker_for_shell,
)


class TestPersistBranchForShell(unittest.TestCase):
    def test_writes_branch_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("devflow_sdk.core.git.shell_state.os.path.expanduser", return_value=tmpdir):
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
            with patch("devflow_sdk.core.git.shell_state.os.path.expanduser", return_value=tmpdir):
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
            with patch("devflow_sdk.core.git.shell_state.os.path.expanduser", return_value=tmpdir):
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
            with patch("devflow_sdk.core.git.shell_state.os.path.expanduser", return_value=tmpdir):
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
            with patch("devflow_sdk.core.git.shell_state.os.path.expanduser", return_value=tmpdir):
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


class TestPersistWorktreePathForShell(unittest.TestCase):
    def test_writes_path_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("devflow_sdk.core.git.shell_state.os.path.expanduser", return_value=tmpdir):
                result = _persist_worktree_path_for_shell("/repos/my-feature")
            path_file = os.path.join(tmpdir, ".finish-issue-worktree-path")
            self.assertTrue(os.path.exists(path_file))
            with open(path_file) as f:
                self.assertEqual(f.read(), "/repos/my-feature")
            self.assertTrue(result)

    def test_oserror_emits_warning_and_returns_false(self):
        with patch("builtins.open", side_effect=OSError("disk full")), \
             patch("sys.stderr") as mock_stderr:
            result = _persist_worktree_path_for_shell("/repos/my-feature")
        mock_stderr.write.assert_called()
        self.assertFalse(result)


class TestClearForceMarkerForShell(unittest.TestCase):
    def test_removes_existing_marker_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            force_file = os.path.join(tmpdir, ".finish-issue-force")
            open(force_file, "w").close()
            with patch("devflow_sdk.core.git.shell_state.os.path.expanduser", return_value=tmpdir):
                result = _clear_force_marker_for_shell()
            self.assertFalse(os.path.exists(force_file))
            self.assertTrue(result)

    def test_noop_when_marker_file_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("devflow_sdk.core.git.shell_state.os.path.expanduser", return_value=tmpdir):
                result = _clear_force_marker_for_shell()
            self.assertTrue(result)

    def test_oserror_emits_warning_and_returns_false(self):
        with patch("devflow_sdk.core.git.shell_state.os.path.exists", return_value=True), \
             patch("devflow_sdk.core.git.shell_state.os.remove", side_effect=OSError("permission denied")), \
             patch("sys.stderr") as mock_stderr:
            result = _clear_force_marker_for_shell()
        mock_stderr.write.assert_called()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

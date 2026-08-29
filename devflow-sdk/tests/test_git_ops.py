#!/usr/bin/env python3
import sys
import os
import unittest
import contextlib
import io
from unittest.mock import patch, MagicMock

from devflow_sdk.core.git.git_ops import (
    current_branch,
    get_base_branch,
    is_dirty,
    commits_ahead,
    stash_push,
    stash_pop,
    log_for_prompt,
    diff_stat,
    soft_reset_and_commit,
    force_push_with_lease,
)


def _proc(returncode=0, stdout="", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestCurrentBranch(unittest.TestCase):
    def test_returns_branch_name(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(stdout="feat/foo\n")):
            self.assertEqual(current_branch(), "feat/foo")

    def test_returns_none_on_failure(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=128)):
            self.assertIsNone(current_branch())


class TestGetBaseBranch(unittest.TestCase):
    def test_uses_origin_head_when_available(self):
        with patch(
            "devflow_sdk.core.git.git_ops.subprocess.run",
            return_value=_proc(stdout="origin/develop\n"),
        ):
            self.assertEqual(get_base_branch(), "develop")

    def test_falls_back_to_gh_when_origin_head_missing(self):
        git_fail = _proc(returncode=128, stdout="")
        gh_ok = _proc(returncode=0, stdout="trunk\n")
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", side_effect=[git_fail, gh_ok]):
            self.assertEqual(get_base_branch(), "trunk")

    def test_falls_back_to_main_when_gh_unavailable(self):
        git_fail = _proc(returncode=128, stdout="")
        with patch(
            "devflow_sdk.core.git.git_ops.subprocess.run", side_effect=[git_fail, FileNotFoundError()]
        ):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(get_base_branch(), "main")


class TestIsDirty(unittest.TestCase):
    def test_clean_tree_is_false(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(stdout="")):
            self.assertFalse(is_dirty())

    def test_dirty_tree_is_true(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(stdout=" M file.py\n")):
            self.assertTrue(is_dirty())


class TestCommitsAhead(unittest.TestCase):
    def test_parses_count(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(stdout="5\n")):
            self.assertEqual(commits_ahead("main"), 5)

    def test_zero_when_command_fails(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=1, stdout="")):
            self.assertEqual(commits_ahead("main"), 0)

    def test_zero_when_output_not_numeric(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(stdout="not-a-number\n")):
            self.assertEqual(commits_ahead("main"), 0)


class TestStash(unittest.TestCase):
    def test_stash_push_success(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=0)):
            self.assertTrue(stash_push())

    def test_stash_push_failure(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=1)):
            self.assertFalse(stash_push())

    def test_stash_pop_success(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=0)):
            self.assertTrue(stash_pop())

    def test_stash_pop_failure(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=1)):
            self.assertFalse(stash_pop())


class TestLogAndDiff(unittest.TestCase):
    def test_log_for_prompt_returns_stripped_stdout(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(stdout="  subject\nbody  \n")):
            self.assertEqual(log_for_prompt("main"), "subject\nbody")

    def test_log_for_prompt_empty_on_failure(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=1, stdout="x")):
            self.assertEqual(log_for_prompt("main"), "")

    def test_diff_stat_returns_stripped_stdout(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(stdout=" 1 file changed \n")):
            self.assertEqual(diff_stat("main"), "1 file changed")

    def test_diff_stat_empty_on_failure(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=1, stdout="x")):
            self.assertEqual(diff_stat("main"), "")


class TestSoftResetAndCommit(unittest.TestCase):
    def test_success(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=0)):
            self.assertTrue(soft_reset_and_commit("main", "feat: x"))

    def test_reset_failure_short_circuits(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=1)) as mock_run:
            self.assertFalse(soft_reset_and_commit("main", "feat: x"))
            self.assertEqual(mock_run.call_count, 1)

    def test_commit_failure(self):
        reset_ok = _proc(returncode=0)
        commit_fail = _proc(returncode=1)
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", side_effect=[reset_ok, commit_fail]):
            self.assertFalse(soft_reset_and_commit("main", "feat: x"))


class TestForcePushWithLease(unittest.TestCase):
    def test_success(self):
        with patch("devflow_sdk.core.git.git_ops.subprocess.run", return_value=_proc(returncode=0, stdout="ok")):
            ok, output = force_push_with_lease("feat/foo")
            self.assertTrue(ok)
            self.assertEqual(output, "ok")

    def test_failure_returns_combined_output(self):
        with patch(
            "devflow_sdk.core.git.git_ops.subprocess.run",
            return_value=_proc(returncode=1, stdout="", stderr="stale info"),
        ):
            ok, output = force_push_with_lease("feat/foo")
            self.assertFalse(ok)
            self.assertEqual(output, "stale info")


if __name__ == "__main__":
    unittest.main()

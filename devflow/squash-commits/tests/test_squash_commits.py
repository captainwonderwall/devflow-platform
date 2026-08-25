#!/usr/bin/env python3
import sys
import os
import unittest
import unittest.mock
import subprocess
import importlib.util
import contextlib
import io

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))        # squash-commits/ dir

_spec = importlib.util.spec_from_file_location(
    "squash_commits", os.path.join(_HERE, "..", "squash-commits.py")
)
squash_commits = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(squash_commits)

build_prompt = squash_commits.build_prompt
extract_commit_message = squash_commits.extract_commit_message
resolve_dirty_choice = squash_commits.resolve_dirty_choice
resolve_push_choice = squash_commits.resolve_push_choice
DIRTY_ABORT = squash_commits.DIRTY_ABORT
DIRTY_STASH = squash_commits.DIRTY_STASH
PUSH_YES = squash_commits.PUSH_YES
PUSH_NO = squash_commits.PUSH_NO


class TestPromptsMigration(unittest.TestCase):
    def test_uses_devflow_sdk_prompts_select(self):
        from devflow_sdk.prompts import select
        self.assertIs(squash_commits.select, select)

    @unittest.mock.patch("devflow_sdk.prompts.questionary.checkbox")
    def test_prompt_dirty_tree_choice_delegates_to_shared_select(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = [squash_commits.DIRTY_STASH]
        result = squash_commits.prompt_dirty_tree_choice()
        self.assertEqual(result, squash_commits.DIRTY_STASH)

    @unittest.mock.patch("devflow_sdk.prompts.questionary.checkbox")
    def test_prompt_push_choice_delegates_to_shared_select(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = [squash_commits.PUSH_YES]
        result = squash_commits.prompt_push_choice("main")
        self.assertEqual(result, squash_commits.PUSH_YES)


class TestBuildPrompt(unittest.TestCase):
    def test_includes_log_and_diff_stat(self):
        prompt = build_prompt("feat: a\nfix: b", "2 files changed")
        self.assertIn("feat: a\nfix: b", prompt)
        self.assertIn("2 files changed", prompt)
        self.assertIn("one line only", prompt)


class TestExtractCommitMessage(unittest.TestCase):
    def test_returns_first_nonempty_line(self):
        self.assertEqual(
            extract_commit_message("\nfeat: add squash-commits script\n"),
            "feat: add squash-commits script",
        )

    def test_strips_whitespace(self):
        self.assertEqual(extract_commit_message("  feat: x  "), "feat: x")

    def test_takes_first_of_multiple_lines(self):
        self.assertEqual(
            extract_commit_message("feat: x\nsome body text"), "feat: x"
        )

    def test_empty_string_returns_empty(self):
        self.assertEqual(extract_commit_message(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(extract_commit_message(None), "")

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(extract_commit_message("   \n  \n"), "")


class TestResolveDirtyChoice(unittest.TestCase):
    def test_stash_choice(self):
        self.assertEqual(resolve_dirty_choice(DIRTY_STASH), "stash")

    def test_abort_choice(self):
        self.assertEqual(resolve_dirty_choice(DIRTY_ABORT), "abort")

    def test_none_is_abort(self):
        self.assertEqual(resolve_dirty_choice(None), "abort")


class TestResolvePushChoice(unittest.TestCase):
    def test_yes_choice(self):
        self.assertTrue(resolve_push_choice(PUSH_YES))

    def test_no_choice(self):
        self.assertFalse(resolve_push_choice(PUSH_NO))

    def test_none_is_no(self):
        self.assertFalse(resolve_push_choice(None))


class TestMainOrchestration(unittest.TestCase):
    """Tests for main() orchestration — all git/AI calls are mocked."""

    def _make_git_ops(self):
        m = unittest.mock.MagicMock()
        m.current_branch.return_value = "feature-branch"
        m.get_base_branch.return_value = "main"
        m.commits_ahead.return_value = 3
        m.is_dirty.return_value = False
        m.stash_push.return_value = True
        m.stash_pop.return_value = True
        m.log_for_prompt.return_value = "feat: a\nfix: b"
        m.diff_stat.return_value = "2 files changed"
        m.soft_reset_and_commit.return_value = True
        m.force_push_with_lease.return_value = (True, "")
        return m

    def test_no_op_when_commits_ahead_le_1(self):
        git = self._make_git_ops()
        git.commits_ahead.return_value = 1
        with unittest.mock.patch("sys.argv", ["squash-commits"]), \
             unittest.mock.patch.object(squash_commits, "git_ops", git), \
             unittest.mock.patch.object(squash_commits.summary, "start_rate_fetch"), \
             unittest.mock.patch.object(squash_commits.summary, "add"), \
             unittest.mock.patch.object(squash_commits.summary, "print_summary"):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    squash_commits.main()
        self.assertEqual(cm.exception.code, 0)
        git.is_dirty.assert_not_called()
        git.soft_reset_and_commit.assert_not_called()

    def test_no_op_when_commits_ahead_is_0(self):
        git = self._make_git_ops()
        git.commits_ahead.return_value = 0
        with unittest.mock.patch("sys.argv", ["squash-commits"]), \
             unittest.mock.patch.object(squash_commits, "git_ops", git), \
             unittest.mock.patch.object(squash_commits.summary, "start_rate_fetch"), \
             unittest.mock.patch.object(squash_commits.summary, "add"), \
             unittest.mock.patch.object(squash_commits.summary, "print_summary"):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    squash_commits.main()
        self.assertEqual(cm.exception.code, 0)
        git.is_dirty.assert_not_called()

    def test_dirty_abort_path(self):
        git = self._make_git_ops()
        git.is_dirty.return_value = True
        with unittest.mock.patch("sys.argv", ["squash-commits"]), \
             unittest.mock.patch.object(squash_commits, "git_ops", git), \
             unittest.mock.patch.object(squash_commits, "prompt_dirty_tree_choice",
                                        return_value=DIRTY_ABORT), \
             unittest.mock.patch.object(squash_commits.summary, "start_rate_fetch"), \
             unittest.mock.patch.object(squash_commits.summary, "add"), \
             unittest.mock.patch.object(squash_commits.summary, "print_summary"):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    squash_commits.main()
        self.assertEqual(cm.exception.code, 1)
        git.stash_push.assert_not_called()
        git.soft_reset_and_commit.assert_not_called()

    def test_dirty_stash_then_restore_path(self):
        git = self._make_git_ops()
        git.is_dirty.return_value = True
        ai_result = unittest.mock.MagicMock(ok=True, result="feat: test commit", error=None)
        captured_callbacks = []

        def capture_register(fn, *args, **kwargs):
            captured_callbacks.append((fn, args, kwargs))

        with unittest.mock.patch("sys.argv", ["squash-commits"]), \
             unittest.mock.patch.object(squash_commits, "git_ops", git), \
             unittest.mock.patch.object(squash_commits, "prompt_dirty_tree_choice",
                                        return_value=DIRTY_STASH), \
             unittest.mock.patch.object(squash_commits, "prompt_push_choice",
                                        return_value=PUSH_NO), \
             unittest.mock.patch.object(squash_commits, "run_ai_prompt",
                                        return_value=ai_result), \
             unittest.mock.patch.object(squash_commits, "atexit") as mock_atexit, \
             unittest.mock.patch.object(squash_commits.summary, "start_rate_fetch"), \
             unittest.mock.patch.object(squash_commits.summary, "add"), \
             unittest.mock.patch.object(squash_commits.summary, "print_summary"):
            mock_atexit.register.side_effect = capture_register
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                squash_commits.main()
            git.stash_push.assert_called_once()
            # Invoke captured atexit callbacks while patches are still active
            for fn, args, kwargs in captured_callbacks:
                fn(*args, **kwargs)
            git.stash_pop.assert_called_once()

    def test_ai_failure_path(self):
        git = self._make_git_ops()
        ai_result = unittest.mock.MagicMock(ok=False, result=None, error="API error")
        with unittest.mock.patch("sys.argv", ["squash-commits"]), \
             unittest.mock.patch.object(squash_commits, "git_ops", git), \
             unittest.mock.patch.object(squash_commits, "run_ai_prompt",
                                        return_value=ai_result), \
             unittest.mock.patch.object(squash_commits, "atexit"), \
             unittest.mock.patch.object(squash_commits.summary, "start_rate_fetch"), \
             unittest.mock.patch.object(squash_commits.summary, "add"), \
             unittest.mock.patch.object(squash_commits.summary, "print_summary"):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    squash_commits.main()
        self.assertEqual(cm.exception.code, 1)
        git.soft_reset_and_commit.assert_not_called()

    def test_push_yes_path(self):
        git = self._make_git_ops()
        ai_result = unittest.mock.MagicMock(ok=True, result="feat: test commit", error=None)
        with unittest.mock.patch("sys.argv", ["squash-commits"]), \
             unittest.mock.patch.object(squash_commits, "git_ops", git), \
             unittest.mock.patch.object(squash_commits, "prompt_push_choice",
                                        return_value=PUSH_YES), \
             unittest.mock.patch.object(squash_commits, "run_ai_prompt",
                                        return_value=ai_result), \
             unittest.mock.patch.object(squash_commits, "atexit"), \
             unittest.mock.patch.object(squash_commits.summary, "start_rate_fetch"), \
             unittest.mock.patch.object(squash_commits.summary, "add"), \
             unittest.mock.patch.object(squash_commits.summary, "print_summary"):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                squash_commits.main()
        git.force_push_with_lease.assert_called_once_with("feature-branch")

    def test_push_no_path(self):
        git = self._make_git_ops()
        ai_result = unittest.mock.MagicMock(ok=True, result="feat: test commit", error=None)
        with unittest.mock.patch("sys.argv", ["squash-commits"]), \
             unittest.mock.patch.object(squash_commits, "git_ops", git), \
             unittest.mock.patch.object(squash_commits, "prompt_push_choice",
                                        return_value=PUSH_NO), \
             unittest.mock.patch.object(squash_commits, "run_ai_prompt",
                                        return_value=ai_result), \
             unittest.mock.patch.object(squash_commits, "atexit"), \
             unittest.mock.patch.object(squash_commits.summary, "start_rate_fetch"), \
             unittest.mock.patch.object(squash_commits.summary, "add"), \
             unittest.mock.patch.object(squash_commits.summary, "print_summary"):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                squash_commits.main()
        git.force_push_with_lease.assert_not_called()


class TestHelpFlag(unittest.TestCase):
    def test_help_exits_zero(self):
        script = os.path.join(_HERE, "..", "squash-commits.py")
        result = subprocess.run(
            [sys.executable, script, "--help"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()

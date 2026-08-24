import sys
import os
import unittest
import unittest.mock
import importlib.util

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))        # finish-issue/ dir

_spec = importlib.util.spec_from_file_location(
    "finish_issue", os.path.join(_HERE, "..", "finish-issue.py")
)
finish_issue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(finish_issue)
_cwd_inside_worktree = finish_issue._cwd_inside_worktree
DIRTY_ABORT = finish_issue.DIRTY_ABORT
DIRTY_DROP = finish_issue.DIRTY_DROP
resolve_dirty_choice = finish_issue.resolve_dirty_choice


class TestCwdInsideWorktree(unittest.TestCase):
    def test_cwd_equals_worktree_path(self):
        self.assertTrue(_cwd_inside_worktree("/repos/feat-52", cwd="/repos/feat-52"))

    def test_cwd_nested_inside_worktree_path(self):
        self.assertTrue(_cwd_inside_worktree("/repos/feat-52", cwd="/repos/feat-52/src/pkg"))

    def test_cwd_outside_worktree_path(self):
        self.assertFalse(_cwd_inside_worktree("/repos/feat-52", cwd="/repos/main"))

    def test_cwd_in_sibling_with_shared_prefix_is_not_inside(self):
        # "/repos/feat-52-other" is NOT inside "/repos/feat-52" even though it
        # shares a string prefix; only real path-segment containment counts.
        self.assertFalse(_cwd_inside_worktree("/repos/feat-52", cwd="/repos/feat-52-other"))


class TestResolveDirtyChoice(unittest.TestCase):
    def test_drop_choice_returns_drop(self):
        self.assertEqual(resolve_dirty_choice(DIRTY_DROP), "drop")

    def test_abort_choice_returns_abort(self):
        self.assertEqual(resolve_dirty_choice(DIRTY_ABORT), "abort")

    def test_ctrl_c_none_returns_abort(self):
        self.assertEqual(resolve_dirty_choice(None), "abort")


class TestPromptDirtyTreeChoice(unittest.TestCase):
    def test_delegates_to_shared_select(self):
        import unittest.mock
        with unittest.mock.patch("devflow_sdk.prompts.questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = DIRTY_DROP
            result = finish_issue.prompt_dirty_tree_choice("feat/gh65-something")
        self.assertEqual(result, DIRTY_DROP)
        mock_select.assert_called_once()
        message = mock_select.call_args[0][0]
        self.assertIn("feat/gh65-something", message)


class TestMainDirtyWorktreeHandling(unittest.TestCase):
    """Exercises the direct (non --prepare) removal path when the worktree
    is dirty. Mocks every external boundary: sys.argv, worktree_finder's
    listing/merge functions, is_dirty, the prompt, and subprocess.run."""

    def _run_main_with(self, is_dirty_return, dirty_choice, prepare=False):
        argv = ["finish-issue", "65"] + (["--prepare"] if prepare else [])
        worktrees = [{"branch": "main", "path": "/repos/main", "is_main": True}]
        match = {"branch": "feat/wt/gh65-something", "path": "/repos/gh65"}

        with unittest.mock.patch("sys.argv", argv), \
             unittest.mock.patch.object(finish_issue, "check_worktrunk"), \
             unittest.mock.patch.object(finish_issue, "check_shell_function"), \
             unittest.mock.patch.object(finish_issue, "fetch",
                 return_value={"source": "github", "id": "65", "title": "t"}), \
             unittest.mock.patch.object(finish_issue, "list_worktrees", return_value=worktrees), \
             unittest.mock.patch.object(finish_issue, "find_matching_worktrees", return_value=[match]), \
             unittest.mock.patch.object(finish_issue, "get_main_branch", return_value="main"), \
             unittest.mock.patch.object(finish_issue, "is_merged", return_value=True), \
             unittest.mock.patch.object(finish_issue, "is_dirty", return_value=is_dirty_return), \
             unittest.mock.patch.object(finish_issue, "prompt_dirty_tree_choice", return_value=dirty_choice), \
             unittest.mock.patch.object(finish_issue, "_persist_branch_for_shell", return_value=True), \
             unittest.mock.patch.object(finish_issue, "_persist_worktree_for_shell", return_value=True), \
             unittest.mock.patch.object(finish_issue, "_persist_force_for_shell", return_value=True) as mock_force, \
             unittest.mock.patch.object(finish_issue, "_persist_worktree_path_for_shell", return_value=True), \
             unittest.mock.patch.object(finish_issue, "_clear_force_marker_for_shell", return_value=True) as mock_clear, \
             unittest.mock.patch.object(finish_issue, "_cwd_inside_worktree", return_value=False), \
             unittest.mock.patch.object(finish_issue.subprocess, "run",
                 return_value=unittest.mock.MagicMock(returncode=0, stderr="")) as mock_run:
            try:
                finish_issue.main()
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code
        return exit_code, mock_run, mock_force, mock_clear

    def test_clean_worktree_calls_wt_remove_without_force(self):
        exit_code, mock_run, mock_force, mock_clear = self._run_main_with(is_dirty_return=False, dirty_choice=None)
        mock_run.assert_called_once_with(
            ["wt", "remove", "feat/wt/gh65-something"], stdout=None,
            stderr=unittest.mock.ANY, text=True,
        )
        mock_force.assert_not_called()

    def test_dirty_worktree_drop_choice_pre_cleans_then_removes(self):
        exit_code, mock_run, mock_force, mock_clear = self._run_main_with(
            is_dirty_return=True, dirty_choice=finish_issue.DIRTY_DROP,
        )
        self.assertEqual(mock_run.call_count, 3)
        calls = mock_run.call_args_list
        self.assertEqual(calls[0][0][0], ["git", "-C", "/repos/gh65", "reset", "--hard", "HEAD"])
        self.assertEqual(calls[1][0][0], ["git", "-C", "/repos/gh65", "clean", "-fd"])
        mock_run.assert_called_with(
            ["wt", "remove", "feat/wt/gh65-something"], stdout=None,
            stderr=unittest.mock.ANY, text=True,
        )
        mock_force.assert_not_called()  # only used in --prepare mode

    def test_dirty_worktree_abort_choice_exits_1_without_removing(self):
        exit_code, mock_run, mock_force, mock_clear = self._run_main_with(
            is_dirty_return=True, dirty_choice=finish_issue.DIRTY_ABORT,
        )
        self.assertEqual(exit_code, 1)
        mock_run.assert_not_called()

    def test_dirty_worktree_ctrl_c_treated_as_abort(self):
        exit_code, mock_run, mock_force, mock_clear = self._run_main_with(
            is_dirty_return=True, dirty_choice=None,
        )
        self.assertEqual(exit_code, 1)
        mock_run.assert_not_called()

    def test_prepare_mode_dirty_drop_persists_force_marker(self):
        exit_code, mock_run, mock_force, mock_clear = self._run_main_with(
            is_dirty_return=True, dirty_choice=finish_issue.DIRTY_DROP, prepare=True,
        )
        self.assertEqual(exit_code, 0)
        mock_force.assert_called_once()
        mock_run.assert_not_called()  # --prepare never calls wt remove itself

    def test_prepare_mode_clean_worktree_does_not_persist_force_marker(self):
        exit_code, mock_run, mock_force, mock_clear = self._run_main_with(
            is_dirty_return=False, dirty_choice=None, prepare=True,
        )
        self.assertEqual(exit_code, 0)
        mock_force.assert_not_called()

    def test_prepare_mode_always_clears_stale_force_marker(self):
        exit_code, mock_run, mock_force, mock_clear = self._run_main_with(
            is_dirty_return=False, dirty_choice=None, prepare=True,
        )
        self.assertEqual(exit_code, 0)
        mock_clear.assert_called_once()


class TestMainIssueContextCleanup(unittest.TestCase):
    """Verify remove_issue_context is called before the dirty check."""

    def _run_main(self, is_dirty_return=False):
        argv = ["finish-issue", "65"]
        worktrees = [{"branch": "main", "path": "/repos/main", "is_main": True}]
        match = {"branch": "feat/wt/gh65-something", "path": "/repos/gh65"}
        call_order = []

        with unittest.mock.patch("sys.argv", argv), \
             unittest.mock.patch.object(finish_issue, "check_worktrunk"), \
             unittest.mock.patch.object(finish_issue, "check_shell_function"), \
             unittest.mock.patch.object(finish_issue, "fetch",
                 return_value={"source": "github", "id": "65", "title": "t"}), \
             unittest.mock.patch.object(finish_issue, "list_worktrees", return_value=worktrees), \
             unittest.mock.patch.object(finish_issue, "find_matching_worktrees", return_value=[match]), \
             unittest.mock.patch.object(finish_issue, "get_main_branch", return_value="main"), \
             unittest.mock.patch.object(finish_issue, "is_merged", return_value=True), \
             unittest.mock.patch.object(finish_issue, "is_dirty",
                 side_effect=lambda p: call_order.append("is_dirty") or is_dirty_return), \
             unittest.mock.patch.object(finish_issue, "prompt_dirty_tree_choice",
                 return_value=finish_issue.DIRTY_ABORT), \
             unittest.mock.patch.object(finish_issue, "_persist_branch_for_shell"), \
             unittest.mock.patch.object(finish_issue, "_cwd_inside_worktree", return_value=False), \
             unittest.mock.patch.object(finish_issue, "remove_issue_context",
                 side_effect=lambda p: call_order.append("remove_issue_context")) as mock_remove, \
             unittest.mock.patch.object(finish_issue.subprocess, "run",
                 return_value=unittest.mock.MagicMock(returncode=0, stderr="")):
            try:
                finish_issue.main()
            except SystemExit:
                pass
        return mock_remove, call_order

    def test_remove_issue_context_called_with_worktree_path(self):
        mock_remove, _ = self._run_main()
        mock_remove.assert_called_once_with("/repos/gh65")

    def test_dirty_check_called_before_remove_issue_context(self):
        _, call_order = self._run_main()
        self.assertIn("remove_issue_context", call_order)
        self.assertIn("is_dirty", call_order)
        self.assertLess(
            call_order.index("is_dirty"),
            call_order.index("remove_issue_context"),
        )


class TestMainIssueAutoDetection(unittest.TestCase):
    """Exercises the issue resolution order: CLI arg → .issue.json → user prompt."""

    def _run_main(self, argv, issue_context=None, prompt_input=None):
        worktrees = [{"branch": "main", "path": "/repos/main", "is_main": True}]
        match = {"branch": "feat/wt/gh65-something", "path": "/repos/gh65"}
        fetched_issue = {"source": "github", "id": "65", "title": "t"}

        with unittest.mock.patch("sys.argv", argv), \
             unittest.mock.patch.object(finish_issue, "check_worktrunk"), \
             unittest.mock.patch.object(finish_issue, "check_shell_function"), \
             unittest.mock.patch.object(finish_issue, "fetch", return_value=fetched_issue) as mock_fetch, \
             unittest.mock.patch.object(finish_issue, "read_issue_context", return_value=issue_context) as mock_read, \
             unittest.mock.patch.object(finish_issue, "text", return_value=prompt_input) as mock_text, \
             unittest.mock.patch.object(finish_issue, "list_worktrees", return_value=worktrees), \
             unittest.mock.patch.object(finish_issue, "find_matching_worktrees", return_value=[match]), \
             unittest.mock.patch.object(finish_issue, "get_main_branch", return_value="main"), \
             unittest.mock.patch.object(finish_issue, "is_merged", return_value=True), \
             unittest.mock.patch.object(finish_issue, "is_dirty", return_value=False), \
             unittest.mock.patch.object(finish_issue, "_persist_branch_for_shell", return_value=True), \
             unittest.mock.patch.object(finish_issue, "_cwd_inside_worktree", return_value=False), \
             unittest.mock.patch.object(finish_issue, "remove_issue_context"), \
             unittest.mock.patch.object(finish_issue.subprocess, "run",
                 return_value=unittest.mock.MagicMock(returncode=0, stderr="")):
            try:
                finish_issue.main()
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code
        return exit_code, mock_fetch, mock_read, mock_text

    def test_cli_arg_calls_fetch_and_skips_read_and_prompt(self):
        exit_code, mock_fetch, mock_read, mock_text = self._run_main(
            ["finish-issue", "65"],
        )
        self.assertEqual(exit_code, 0)
        mock_fetch.assert_called_once_with("65")
        mock_read.assert_not_called()
        mock_text.assert_not_called()

    def test_no_arg_uses_issue_context_without_calling_fetch(self):
        stored = {"source": "github", "id": "65", "title": "t"}
        exit_code, mock_fetch, mock_read, mock_text = self._run_main(
            ["finish-issue"], issue_context=stored,
        )
        self.assertEqual(exit_code, 0)
        mock_read.assert_called_once()
        mock_fetch.assert_not_called()
        mock_text.assert_not_called()

    def test_no_arg_no_context_prompts_user_then_fetches(self):
        exit_code, mock_fetch, mock_read, mock_text = self._run_main(
            ["finish-issue"], issue_context=None, prompt_input="65",
        )
        self.assertEqual(exit_code, 0)
        mock_text.assert_called_once()
        mock_fetch.assert_called_once_with("65")

    def test_no_arg_no_context_user_cancels_exits_1_without_fetching(self):
        exit_code, mock_fetch, mock_read, mock_text = self._run_main(
            ["finish-issue"], issue_context=None, prompt_input=None,
        )
        self.assertEqual(exit_code, 1)
        mock_fetch.assert_not_called()


class TestCheckShellFunctionCalledInFinishIssue(unittest.TestCase):
    def _make_worktree(self):
        return {"branch": "feat/gh-42", "path": "/repos/feat-gh-42", "is_main": False}

    def test_check_shell_function_called_with_finish_issue_sentinel_and_prepare(self):
        wt = self._make_worktree()
        with unittest.mock.patch("sys.argv", ["finish-issue", "42"]), \
             unittest.mock.patch.object(finish_issue, "check_worktrunk"), \
             unittest.mock.patch.object(finish_issue, "check_shell_function") as mock_csf, \
             unittest.mock.patch.object(finish_issue, "fetch",
                 return_value={"source": "github", "id": "42", "title": "t",
                               "body": "", "comments": [], "issuetype": "", "labels": []}), \
             unittest.mock.patch.object(finish_issue, "list_worktrees", return_value=[wt]), \
             unittest.mock.patch.object(finish_issue, "find_matching_worktrees", return_value=[wt]), \
             unittest.mock.patch.object(finish_issue, "get_main_branch", return_value="main"), \
             unittest.mock.patch.object(finish_issue, "is_merged", return_value=True), \
             unittest.mock.patch.object(finish_issue, "is_dirty", return_value=False), \
             unittest.mock.patch.object(finish_issue, "_persist_branch_for_shell"), \
             unittest.mock.patch.object(finish_issue, "_persist_worktree_for_shell"), \
             unittest.mock.patch.object(finish_issue, "_cwd_inside_worktree", return_value=False), \
             unittest.mock.patch.object(finish_issue, "remove_issue_context"), \
             unittest.mock.patch.object(finish_issue.subprocess, "run",
                 return_value=unittest.mock.MagicMock(returncode=0, stderr="")):
            try:
                finish_issue.main()
            except SystemExit:
                pass
        mock_csf.assert_called_once()
        sentinel_arg = mock_csf.call_args[0][0]
        required_content_kwarg = mock_csf.call_args[1].get("required_content")
        self.assertIn("finish-issue shell integration", sentinel_arg)
        self.assertIsNotNone(required_content_kwarg)
        fragments = [required_content_kwarg] if isinstance(required_content_kwarg, str) else required_content_kwarg
        self.assertTrue(any("--prepare" in f for f in fragments))
        self.assertTrue(any(".finish-issue-force" in f for f in fragments))


if __name__ == "__main__":
    unittest.main()

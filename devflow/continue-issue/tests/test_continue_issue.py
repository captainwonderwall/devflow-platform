import sys
import os
import unittest
import unittest.mock
import importlib.util
from devflow_sdk.domain.workspace import Workspace
from devflow_sdk.worktree_state import WorktreeEntry

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

_spec = importlib.util.spec_from_file_location(
    "continue_issue", os.path.join(_HERE, "..", "continue-issue.py")
)
continue_issue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(continue_issue)


def _make_entry(ticket_id="65", source="github", path="/repos/gh65"):
    return WorktreeEntry(path=path, ticket_id=ticket_id, source=source)


def _make_workspace(branch="feat/wt/gh65-something", path="/repos/gh65"):
    return Workspace(branch=branch, path=path, is_main=False)


def _run_main(argv, tracked=None, find_return=None, select_return=None,
              cwd_inside=False, persist_return=True):
    import contextlib
    if tracked is None:
        tracked = []
    if find_return is None:
        find_return = [_make_workspace()]

    with contextlib.ExitStack() as stack:
        stack.enter_context(unittest.mock.patch("sys.argv", argv))
        stack.enter_context(unittest.mock.patch.object(continue_issue, "check_manager"))
        stack.enter_context(unittest.mock.patch.object(continue_issue, "check_shell_function"))
        stack.enter_context(unittest.mock.patch.object(continue_issue, "list_tracked_worktrees",
            return_value=tracked))
        stack.enter_context(unittest.mock.patch.object(continue_issue, "_cwd_inside_worktree",
            return_value=cwd_inside))
        mock_select = stack.enter_context(unittest.mock.patch.object(continue_issue, "select",
            return_value=select_return))
        stack.enter_context(unittest.mock.patch.object(continue_issue, "query_worktrees",
            return_value=[]))
        stack.enter_context(unittest.mock.patch.object(continue_issue, "find_for_issue",
            return_value=find_return))
        mock_ide = stack.enter_context(unittest.mock.patch.object(continue_issue, "prompt_and_open_ide"))
        stack.enter_context(unittest.mock.patch.object(continue_issue, "prompt_and_open_ai_agent"))
        mock_persist = stack.enter_context(unittest.mock.patch.object(
            continue_issue, "_persist_continue_branch_for_shell", return_value=persist_return))
        try:
            continue_issue.main()
            exit_code = 0
        except SystemExit as e:
            exit_code = e.code
    return exit_code, mock_select, mock_ide, mock_persist


class TestNoArgPicker(unittest.TestCase):
    def test_empty_tracked_list_exits_0(self):
        exit_code, _, _, _ = _run_main(["continue-issue"], tracked=[])
        self.assertEqual(exit_code, 0)

    def test_cwd_is_only_worktree_exits_0(self):
        entry = _make_entry()
        exit_code, _, _, _ = _run_main(["continue-issue"], tracked=[entry], cwd_inside=True)
        self.assertEqual(exit_code, 0)

    def test_picker_shown_with_available_worktrees(self):
        entry = _make_entry()
        label = "65 (github) → /repos/gh65"
        exit_code, mock_select, _, mock_persist = _run_main(
            ["continue-issue"],
            tracked=[entry],
            select_return=label,
        )
        self.assertEqual(exit_code, 0)
        mock_select.assert_called_once()
        mock_persist.assert_called_once_with("feat/wt/gh65-something", "/repos/gh65")

    def test_shell_check_requires_worktree_path_and_explicit_working_directory(self):
        with unittest.mock.patch("sys.argv", ["continue-issue"]), \
             unittest.mock.patch.object(continue_issue, "check_manager"), \
             unittest.mock.patch.object(continue_issue, "check_shell_function") as mock_check, \
             unittest.mock.patch.object(continue_issue, "list_tracked_worktrees", return_value=[]):
            try:
                continue_issue.main()
            except SystemExit:
                pass

        required_content = mock_check.call_args.kwargs["required_content"]
        self.assertIn(".continue-issue-worktree-path", required_content)
        self.assertIn("wt -C", required_content)

    def test_picker_cancel_exits_1(self):
        entry = _make_entry()
        exit_code, mock_select, _, mock_persist = _run_main(
            ["continue-issue"],
            tracked=[entry],
            select_return=None,
        )
        self.assertEqual(exit_code, 1)
        mock_persist.assert_not_called()

    def test_single_remaining_shows_picker_for_confirmation(self):
        entry = _make_entry()
        label = "65 (github) → /repos/gh65"
        exit_code, mock_select, _, _ = _run_main(
            ["continue-issue"],
            tracked=[entry],
            select_return=label,
        )
        mock_select.assert_called_once()
        choices_arg = mock_select.call_args[0][1]
        self.assertEqual(len(choices_arg), 1)


class TestArgPath(unittest.TestCase):
    def test_matching_arg_skips_picker(self):
        entry = _make_entry(ticket_id="65")
        exit_code, mock_select, _, mock_persist = _run_main(
            ["continue-issue", "65"],
            tracked=[entry],
        )
        self.assertEqual(exit_code, 0)
        mock_select.assert_not_called()
        mock_persist.assert_called_once_with("feat/wt/gh65-something", "/repos/gh65")

    def test_arg_case_insensitive_match(self):
        entry = _make_entry(ticket_id="VDP-123", source="jira", path="/repos/vdp-123")
        workspace = _make_workspace(branch="feat/wt/jira-vdp-123", path="/repos/vdp-123")
        exit_code, _, _, mock_persist = _run_main(
            ["continue-issue", "vdp-123"],
            tracked=[entry],
            find_return=[workspace],
        )
        self.assertEqual(exit_code, 0)
        mock_persist.assert_called_once_with("feat/wt/jira-vdp-123", "/repos/vdp-123")

    def test_unmatched_arg_exits_1(self):
        exit_code, mock_select, _, mock_persist = _run_main(
            ["continue-issue", "VDP-999"],
            tracked=[],
        )
        self.assertEqual(exit_code, 1)
        mock_select.assert_not_called()
        mock_persist.assert_not_called()

    def test_unmatched_arg_suggests_start_issue(self, ):
        with unittest.mock.patch("sys.argv", ["continue-issue", "VDP-999"]), \
             unittest.mock.patch.object(continue_issue, "check_manager"), \
             unittest.mock.patch.object(continue_issue, "check_shell_function"), \
             unittest.mock.patch.object(continue_issue, "list_tracked_worktrees",
                 return_value=[]), \
             unittest.mock.patch("builtins.print") as mock_print:
            try:
                continue_issue.main()
            except SystemExit:
                pass
        printed = " ".join(str(c) for c in mock_print.call_args_list)
        self.assertIn("start-issue", printed)


class TestIdePrompt(unittest.TestCase):
    def test_ide_prompt_called_for_picker_path(self):
        entry = _make_entry()
        label = "65 (github) → /repos/gh65"
        _, _, mock_ide, _ = _run_main(
            ["continue-issue"],
            tracked=[entry],
            select_return=label,
        )
        mock_ide.assert_called_once_with("/repos/gh65")

    def test_ide_prompt_called_for_arg_path(self):
        entry = _make_entry()
        _, _, mock_ide, _ = _run_main(
            ["continue-issue", "65"],
            tracked=[entry],
        )
        mock_ide.assert_called_once_with("/repos/gh65")


class TestWorktreeNotInGit(unittest.TestCase):
    def test_state_entry_with_no_git_match_exits_1(self):
        entry = _make_entry()
        exit_code, _, _, mock_persist = _run_main(
            ["continue-issue", "65"],
            tracked=[entry],
            find_return=[],
        )
        self.assertEqual(exit_code, 1)
        mock_persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()

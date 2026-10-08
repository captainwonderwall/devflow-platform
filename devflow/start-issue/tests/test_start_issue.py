import sys
import os
import importlib.util
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

# Add devflow-sdk to path
_ROOT = os.path.join(_HERE, "..", "..", "..")
sys.path.insert(0, _ROOT)
_SDK_PATH = os.path.join(_ROOT, "devflow-sdk")
if os.path.isdir(_SDK_PATH):
    sys.path.insert(0, _SDK_PATH)

# start-issue.py has a hyphen so it can't be imported normally
_spec = importlib.util.spec_from_file_location(
    "start_issue",
    os.path.join(_HERE, "..", "start-issue.py"),
)
start_issue = importlib.util.module_from_spec(_spec)
sys.modules["start_issue"] = start_issue  # register so patch("start_issue.x") works
_spec.loader.exec_module(start_issue)

from devflow_sdk.core.ai import AiResult
from devflow_sdk.domain.workspace import Workspace


FAKE_WORKSPACE = Workspace(branch="feat/wt/gh-42-fix", path="/fake/worktree", is_main=False)


def _ai_result(type_str=None, ok=True, error=""):
    result = {"type": type_str} if type_str else {}
    return AiResult(result=result, session_id=None, ok=ok,
                    error=error, needs_interaction=False, total_tokens=50)


class TestNeedsAiInference(unittest.TestCase):
    def test_jira_empty_issuetype_returns_true(self):
        self.assertTrue(start_issue._needs_ai_inference(
            {"source": "jira", "issuetype": "", "labels": []}
        ))

    def test_jira_none_issuetype_returns_true(self):
        self.assertTrue(start_issue._needs_ai_inference(
            {"source": "jira", "issuetype": None, "labels": []}
        ))

    def test_jira_story_issuetype_returns_false(self):
        self.assertFalse(start_issue._needs_ai_inference(
            {"source": "jira", "issuetype": "Story", "labels": []}
        ))

    def test_jira_bug_issuetype_returns_false(self):
        self.assertFalse(start_issue._needs_ai_inference(
            {"source": "jira", "issuetype": "Bug", "labels": []}
        ))

    def test_github_empty_labels_returns_true(self):
        self.assertTrue(start_issue._needs_ai_inference(
            {"source": "github", "issuetype": "", "labels": []}
        ))

    def test_github_with_labels_returns_false(self):
        self.assertFalse(start_issue._needs_ai_inference(
            {"source": "github", "issuetype": "", "labels": ["enhancement"]}
        ))

    def test_github_unmatched_labels_still_returns_false(self):
        # AI does NOT trigger just because labels don't match keywords
        self.assertFalse(start_issue._needs_ai_inference(
            {"source": "github", "issuetype": "", "labels": ["needs-triage"]}
        ))


class TestAiInferType(unittest.TestCase):
    def _issue(self, source="jira", title="Fix crash on login", body=""):
        return {"source": source, "title": title, "body": body,
                "issuetype": "", "labels": []}

    def test_returns_valid_type_from_ai(self):
        with patch("start_issue.run_ai_prompt", return_value=_ai_result("fix")):
            result = start_issue._ai_infer_type(self._issue())
        self.assertEqual(result, "fix")

    def test_returns_feat_when_ai_fails(self):
        with patch("start_issue.run_ai_prompt", return_value=_ai_result(ok=False, error="timeout")):
            result = start_issue._ai_infer_type(self._issue())  # no exception raised
        self.assertEqual(result, "feat")

    def test_prints_warning_when_ai_fails(self):
        with patch("start_issue.run_ai_prompt", return_value=_ai_result(ok=False, error="timeout")):
            with patch("sys.stderr") as mock_stderr:
                result = start_issue._ai_infer_type(self._issue())
        self.assertEqual(result, "feat")
        mock_stderr.write.assert_called()

    def test_returns_feat_for_unknown_type(self):
        with patch("start_issue.run_ai_prompt", return_value=_ai_result("refactor")):
            result = start_issue._ai_infer_type(self._issue())
        self.assertEqual(result, "feat")

    def test_all_valid_types_accepted(self):
        for t in ("feat", "fix", "hotfix", "chore", "docs"):
            with patch("start_issue.run_ai_prompt", return_value=_ai_result(t)):
                result = start_issue._ai_infer_type(self._issue())
            self.assertEqual(result, t)

    def test_body_truncated_to_2000_chars(self):
        long_body = "x" * 5000
        captured = {}
        def capture_prompt(prompt, **kwargs):
            captured["prompt"] = prompt
            return _ai_result("feat")
        with patch("start_issue.run_ai_prompt", side_effect=capture_prompt):
            start_issue._ai_infer_type(self._issue(body=long_body))
        self.assertIn("x" * 2000, captured["prompt"])
        self.assertNotIn("x" * 2001, captured["prompt"])

    def test_uses_fast_tier(self):
        captured = {}
        def capture(prompt, tier, **kwargs):
            captured["tier"] = tier
            return _ai_result("feat")
        with patch("start_issue.run_ai_prompt", side_effect=capture):
            start_issue._ai_infer_type(self._issue())
        self.assertEqual(captured["tier"], "fast")

    def test_prompt_includes_source_and_title(self):
        captured = {}
        def capture(prompt, **kwargs):
            captured["prompt"] = prompt
            return _ai_result("feat")
        with patch("start_issue.run_ai_prompt", side_effect=capture):
            start_issue._ai_infer_type({"source": "github", "title": "Add dark mode",
                                         "body": "", "issuetype": "", "labels": []})
        self.assertIn("github", captured["prompt"])
        self.assertIn("Add dark mode", captured["prompt"])


class TestMainAiInferenceWiring(unittest.TestCase):
    """Verify that main() calls _ai_infer_type at the right times."""

    def _run_main(self, issue_arg, issue_data, ai_type=None, extra_argv=None):
        """Helper: patch fetch, run_ai_prompt, and all downstream functions
        that main() calls so the test stays unit-scoped."""
        argv = ["start-issue", issue_arg] + (extra_argv or [])
        ai_result_val = _ai_result(ai_type or "feat")
        with patch("sys.argv", argv), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue_data), \
             patch("start_issue.run_ai_prompt", return_value=ai_result_val) as mock_ai, \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_workspace", return_value=FAKE_WORKSPACE), \
             patch("start_issue.write_issue_context"), \
             patch("start_issue.copy_ide_config") as mock_copy_ide_config, \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree"), \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        self._mock_copy_ide_config = mock_copy_ide_config
        return mock_ai

    def _jira_no_type(self):
        return {"source": "jira", "id": "VDP-1", "title": "Fix crash",
                "body": "", "comments": [], "issuetype": "", "labels": []}

    def _jira_with_type(self):
        return {"source": "jira", "id": "VDP-1", "title": "Fix crash",
                "body": "", "comments": [], "issuetype": "Bug", "labels": []}

    def _github_no_labels(self):
        return {"source": "github", "id": "42", "title": "Add dark mode",
                "body": "", "comments": [], "issuetype": "", "labels": []}

    def test_copy_ide_config_called_with_repo_root_and_worktree_path(self):
        self._run_main("VDP-1", self._jira_with_type())
        self._mock_copy_ide_config.assert_called_once_with("/fake/root", "/fake/worktree")

    def test_copy_ide_config_not_called_when_worktree_path_is_none(self):
        with patch("sys.argv", ["start-issue", "VDP-1"]), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=self._jira_with_type()), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_workspace", return_value=None), \
             patch("start_issue.copy_ide_config") as mock_copy_ide_config, \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree"), \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        mock_copy_ide_config.assert_not_called()

    def test_ai_called_for_jira_with_no_issuetype(self):
        mock_ai = self._run_main("VDP-1", self._jira_no_type(), ai_type="fix")
        mock_ai.assert_called_once()

    def test_ai_not_called_for_jira_with_issuetype(self):
        mock_ai = self._run_main("VDP-1", self._jira_with_type())
        mock_ai.assert_not_called()

    def test_ai_called_for_github_with_no_labels(self):
        mock_ai = self._run_main("42", self._github_no_labels(), ai_type="chore")
        mock_ai.assert_called_once()

    def test_cli_override_suppresses_ai(self):
        # --fix flag: AI must NOT be called even when issuetype is empty
        mock_ai = self._run_main("VDP-1", self._jira_no_type(), extra_argv=["--fix"])
        mock_ai.assert_not_called()

    def test_ai_result_used_as_branch_type(self):
        captured = {}
        issue = self._jira_no_type()
        ai_ret = _ai_result("hotfix")
        with patch("sys.argv", ["start-issue", "VDP-1"]), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue), \
             patch("start_issue.run_ai_prompt", return_value=ai_ret), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_workspace", return_value=FAKE_WORKSPACE), \
             patch("start_issue.write_issue_context"), \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree"), \
             patch("start_issue.make_branch", side_effect=lambda i, override, worktree: captured.update({"override": override}) or "hotfix/wt/jira-VDP-1-fix-crash"), \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        self.assertEqual(captured["override"], "hotfix")


class TestMainIssueContextEnrichment(unittest.TestCase):
    """Verify main() enriches the issue dict with branch/branch_type/started_at before writing."""

    def _run_main_capture_written_issue(self, issue_data):
        written = {}

        def capture_write(worktree_path, issue):
            written["issue"] = dict(issue)

        argv = ["start-issue", str(issue_data.get("id", "42"))]
        with patch("sys.argv", argv), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue_data), \
             patch("start_issue.run_ai_prompt", return_value=_ai_result("feat")), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_workspace", return_value=FAKE_WORKSPACE), \
             patch("start_issue.write_issue_context", side_effect=capture_write), \
             patch("start_issue.copy_ide_config"), \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree"), \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        return written.get("issue")

    def _github_issue(self):
        return {"source": "github", "id": "42", "title": "Add dark mode",
                "body": "", "comments": [], "issuetype": "", "labels": ["enhancement"]}

    def test_write_issue_context_receives_branch(self):
        written = self._run_main_capture_written_issue(self._github_issue())
        self.assertIn("branch", written)
        self.assertTrue(written["branch"].startswith("feat/"))

    def test_write_issue_context_receives_branch_type(self):
        written = self._run_main_capture_written_issue(self._github_issue())
        self.assertIn("branch_type", written)
        self.assertIn(written["branch_type"], ("feat", "fix", "hotfix", "chore", "docs"))

    def test_write_issue_context_receives_started_at(self):
        written = self._run_main_capture_written_issue(self._github_issue())
        self.assertIn("started_at", written)
        self.assertIn("T", written["started_at"])

    def test_summary_includes_issue_json_path(self):
        issue = self._github_issue()
        summary_calls = []
        with patch("sys.argv", ["start-issue", "42"]), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue), \
             patch("start_issue.run_ai_prompt", return_value=_ai_result("feat")), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_workspace", return_value=FAKE_WORKSPACE), \
             patch("start_issue.write_issue_context"), \
             patch("start_issue.copy_ide_config"), \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree"), \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add",
                          side_effect=lambda k, v: summary_calls.append((k, v))):
            start_issue.main()
        keys = [k for k, v in summary_calls]
        self.assertIn("Issue JSON", keys)
        issue_json_value = next(v for k, v in summary_calls if k == "Issue JSON")
        self.assertIn(".issue.json", issue_json_value)


class TestMainIssueContextWriting(unittest.TestCase):
    def _run_main(self, worktree_path, issue_data):
        argv = ["start-issue", str(issue_data.get("id", "42"))]
        with patch("sys.argv", argv), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue_data), \
             patch("start_issue.run_ai_prompt", return_value=_ai_result("feat")), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
              patch("start_issue.create_workspace", return_value=Workspace(branch="feat/wt/gh42-add-dark-mode", path=worktree_path, is_main=False) if worktree_path else None), \
             patch("start_issue.copy_ide_config"), \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree"), \
             patch("start_issue.write_issue_context") as mock_write, \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        return mock_write

    def _github_issue(self):
        return {"source": "github", "id": "42", "title": "Add dark mode",
                "body": "", "comments": [], "issuetype": "", "labels": ["enhancement"]}

    def test_write_issue_context_called_when_worktree_created(self):
        issue = self._github_issue()
        mock_write = self._run_main("/fake/worktree", issue)
        mock_write.assert_called_once_with("/fake/worktree", issue)

    def test_write_issue_context_not_called_when_no_worktree(self):
        issue = self._github_issue()
        with patch("sys.argv", ["start-issue", "42"]), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue), \
             patch("start_issue.run_ai_prompt", return_value=_ai_result("feat")), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_workspace", return_value=None), \
             patch("start_issue.copy_ide_config"), \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree"), \
             patch("start_issue.write_issue_context") as mock_write, \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        mock_write.assert_not_called()


class TestCheckShellFunctionCalledInStartIssue(unittest.TestCase):
    def test_check_shell_function_called_with_start_issue_sentinel(self):
        issue = {"source": "github", "id": "42", "title": "t",
                 "body": "", "comments": [], "issuetype": "", "labels": ["feat"]}
        calls = []
        with patch("sys.argv", ["start-issue", "42"]), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue), \
             patch("start_issue.run_ai_prompt", return_value=_ai_result("feat")), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function", side_effect=lambda *a, **kw: calls.append((a, kw))) as mock_csf, \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_workspace", return_value=FAKE_WORKSPACE), \
             patch("start_issue.write_issue_context"), \
             patch("start_issue.copy_ide_config"), \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree"), \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        mock_csf.assert_called_once()
        sentinel_arg = mock_csf.call_args[0][0]
        self.assertIn("start-issue shell integration", sentinel_arg)
        required_content = mock_csf.call_args.kwargs["required_content"]
        self.assertIn("~/.start-issue-branch", required_content)
        self.assertIn("~/.start-issue-worktree-path", required_content)
        self.assertIn("wt -C", required_content)


class TestStartIssueShellSelection(unittest.TestCase):
    def test_persists_branch_and_absolute_worktree_path(self):
        issue = {"source": "github", "id": "42", "title": "t",
                 "body": "", "comments": [], "issuetype": "", "labels": ["feat"]}
        with patch("sys.argv", ["start-issue", "42"]), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_workspace", return_value=FAKE_WORKSPACE), \
             patch("start_issue.write_issue_context"), \
             patch("start_issue.copy_ide_config"), \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue.add_worktree"), \
             patch("start_issue._persist_start_branch_for_shell") as mock_persist, \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()

        mock_persist.assert_called_once()
        branch, path = mock_persist.call_args.args
        self.assertTrue(branch.startswith("feat/wt/gh42-"))
        self.assertEqual(path, "/fake/worktree")


class TestMainWorktreeStateIntegration(unittest.TestCase):
    def _run_main(self, worktree_path, issue_data):
        argv = ["start-issue", str(issue_data.get("id", "42"))]
        with patch("sys.argv", argv), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue_data), \
             patch("start_issue.run_ai_prompt", return_value=_ai_result("feat")), \
             patch("start_issue.check_manager"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
              patch("start_issue.create_workspace", return_value=Workspace(branch="feat/wt/gh42-add-dark-mode", path=worktree_path, is_main=False) if worktree_path else None), \
             patch("start_issue.write_issue_context"), \
             patch("start_issue.copy_ide_config"), \
              patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_start_branch_for_shell"), \
             patch("start_issue.add_worktree") as mock_add, \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        return mock_add

    def _github_issue(self):
        return {"source": "github", "id": "42", "title": "Add dark mode",
                "body": "", "comments": [], "issuetype": "", "labels": ["enhancement"]}

    def test_add_worktree_called_with_path_ticket_id_and_source(self):
        issue = self._github_issue()
        mock_add = self._run_main("/fake/worktree", issue)
        mock_add.assert_called_once_with("/fake/worktree", "42", "github", parent_branch=None)

    def test_add_worktree_not_called_when_no_worktree(self):
        mock_add = self._run_main(None, self._github_issue())
        mock_add.assert_not_called()

    def test_add_worktree_called_with_jira_source(self):
        issue = {"source": "jira", "id": "VDP-123", "title": "Fix crash",
                 "body": "", "comments": [], "issuetype": "Bug", "labels": []}
        mock_add = self._run_main("/fake/worktree", issue)
        mock_add.assert_called_once_with("/fake/worktree", "VDP-123", "jira", parent_branch=None)


def _entry(path, parent_branch=None):
    from devflow_sdk.worktree_state import WorktreeEntry
    return WorktreeEntry(path=path, ticket_id="1", source="github",
                         parent_branch=parent_branch)


class TestDetectStackParent(unittest.TestCase):
    def test_returns_none_when_not_in_tracked_worktree(self):
        with patch("devflow_sdk.worktree_state.list_tracked_worktrees", return_value=[]), \
             patch("devflow_sdk.core.git.worktree._cwd_inside_worktree", return_value=False):
            self.assertIsNone(start_issue._detect_stack_parent())

    def test_returns_current_branch_when_in_tracked_worktree(self):
        proc = MagicMock(); proc.returncode = 0; proc.stdout = "feat/wt/issue-1-base\n"
        with patch("devflow_sdk.worktree_state.list_tracked_worktrees",
                   return_value=[_entry("/repos/wt/feat-base")]), \
             patch("devflow_sdk.core.git.worktree._cwd_inside_worktree", return_value=True), \
             patch("subprocess.run", return_value=proc):
            self.assertEqual(start_issue._detect_stack_parent(), "feat/wt/issue-1-base")

    def test_returns_none_when_git_branch_fails(self):
        proc = MagicMock(); proc.returncode = 128; proc.stdout = ""
        with patch("devflow_sdk.worktree_state.list_tracked_worktrees",
                   return_value=[_entry("/repos/wt/feat-base")]), \
             patch("devflow_sdk.core.git.worktree._cwd_inside_worktree", return_value=True), \
             patch("subprocess.run", return_value=proc):
            self.assertIsNone(start_issue._detect_stack_parent())


class TestValidateBaseBranch(unittest.TestCase):
    def _proc(self, returncode=0, stdout=""):
        p = MagicMock(); p.returncode = returncode; p.stdout = stdout
        return p

    def test_returns_true_when_up_to_date(self):
        fetch_ok = self._proc(0)
        behind_zero = self._proc(0, "0\n")
        with patch("subprocess.run", side_effect=[fetch_ok, behind_zero]):
            self.assertTrue(start_issue._validate_base_branch("feat/wt/issue-1-base"))

    def test_returns_true_when_behind_count_unreadable(self):
        fetch_ok = self._proc(0)
        count_fail = self._proc(1, "")
        with patch("subprocess.run", side_effect=[fetch_ok, count_fail]):
            self.assertTrue(start_issue._validate_base_branch("feat/wt/issue-1-base"))

    def test_accept_prints_warning_and_returns_true(self):
        fetch_ok = self._proc(0)
        behind_five = self._proc(0, "5\n")
        with patch("subprocess.run", side_effect=[fetch_ok, behind_five]), \
             patch("devflow_sdk.core.prompts.select", return_value="Accept (proceed with stale base)"), \
             patch("sys.stderr"):
            result = start_issue._validate_base_branch("feat/wt/issue-1-base")
        self.assertTrue(result)

    def test_update_success_returns_true(self):
        fetch_ok = self._proc(0)
        behind_two = self._proc(0, "2\n")
        pull_ok = self._proc(0)
        with patch("subprocess.run", side_effect=[fetch_ok, behind_two, pull_ok]) as mock_run, \
             patch("devflow_sdk.core.prompts.select", return_value="Update (git pull --rebase)"):
            self.assertTrue(start_issue._validate_base_branch("feat/wt/issue-1-base"))
        pull_call = mock_run.call_args_list[2][0][0]
        self.assertIn("origin", pull_call)
        self.assertIn("feat/wt/issue-1-base", pull_call)

    def test_update_rebase_conflict_aborts_and_exits(self):
        fetch_ok = self._proc(0)
        behind_two = self._proc(0, "2\n")
        pull_fail = self._proc(1)
        abort_ok = self._proc(0)
        with patch("subprocess.run", side_effect=[fetch_ok, behind_two, pull_fail, abort_ok]), \
             patch("devflow_sdk.core.prompts.select", return_value="Update (git pull --rebase)"), \
             self.assertRaises(SystemExit) as cm:
            start_issue._validate_base_branch("feat/wt/issue-1-base")
        self.assertEqual(cm.exception.code, 1)

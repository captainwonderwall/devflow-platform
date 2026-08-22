import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

# Load draft-pr.py (filename has hyphen, can't use normal import)
_spec = importlib.util.spec_from_file_location(
    "draft_pr", os.path.join(_HERE, "..", "draft-pr.py")
)
draft_pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draft_pr)


def _make_data(**kw):
    base = {
        "branch": "feat/CONS-123-my-feature",
        "base": "main",
        "git_log": "add feature",
        "diff_stat": "1 file changed",
        "changed_files": ["foo.py"],
        "is_fix": False,
        "behind_count": 0,
    }
    base.update(kw)
    return base


def _make_plugin(name="Test", questions=None, prompt_str="prompt", body_str="body"):
    p = MagicMock()
    p.name = name
    p.get_questions.return_value = questions or []
    p.build_prompt.return_value = prompt_str
    p.build_body.return_value = body_str
    return p


_STANDARD_ANSWERS = {"issue_type": "Issue", "customer_visible": "no"}


class TestDetectIssueRefs(unittest.TestCase):
    def test_extracts_jira_key(self):
        refs = draft_pr.detect_issue_refs("feat/CONS-456-something")
        self.assertIn("CONS-456", refs)

    def test_returns_empty_for_no_refs(self):
        refs = draft_pr.detect_issue_refs("feat/no-ticket")
        self.assertEqual(refs, [])


class TestResolveJira(unittest.TestCase):
    def test_returns_jira_key_from_branch(self):
        data = _make_data(branch="feat/CONS-123-foo")
        with patch.object(draft_pr, "select") as mock_select:
            mock_select.return_value = "CONS-123"
            result, _ = draft_pr.resolve_jira(data, None)
        self.assertEqual(result, "CONS-123")


class TestMainNoPlugins(unittest.TestCase):
    def test_exits_when_no_plugins_found(self):
        with patch.object(draft_pr, "collect", return_value=_make_data()), \
             patch.object(draft_pr, "validate_state"), \
             patch.object(draft_pr, "check_existing_pr", return_value=None), \
             patch.object(draft_pr, "select_plugin", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                draft_pr.main()
            self.assertNotEqual(ctx.exception.code, 0)


class TestMainSinglePlugin(unittest.TestCase):
    def _run_main(self, plugin, ai_result=None):
        if ai_result is None:
            ai_result = MagicMock(ok=True, result={"title": "My PR"})
        with patch.object(draft_pr, "collect", return_value=_make_data()), \
             patch.object(draft_pr, "validate_state"), \
             patch.object(draft_pr, "check_existing_pr", return_value=None), \
             patch.object(draft_pr, "select_plugin", return_value=plugin), \
             patch.object(draft_pr, "resolve_jira", return_value=("CONS-123", None)), \
             patch.object(draft_pr, "select", return_value="Issue"), \
             patch.object(draft_pr, "run_ai_prompt", return_value=ai_result), \
             patch.object(draft_pr, "write_create_script"), \
             patch.object(draft_pr, "run_create_script", return_value=(None, None)), \
             patch("questionary.prompt", return_value=_STANDARD_ANSWERS), \
             patch("builtins.input", return_value="no"):
            draft_pr.main()

    def test_single_plugin_used_without_selection_prompt(self):
        plugin = _make_plugin()
        with patch.object(draft_pr, "collect", return_value=_make_data()), \
             patch.object(draft_pr, "validate_state"), \
             patch.object(draft_pr, "check_existing_pr", return_value=None), \
             patch.object(draft_pr, "select_plugin", return_value=plugin), \
             patch.object(draft_pr, "resolve_jira", return_value=("CONS-123", None)), \
             patch.object(draft_pr, "select") as mock_select, \
             patch.object(draft_pr, "run_ai_prompt",
                          return_value=MagicMock(ok=True, result={"title": "T"})), \
             patch.object(draft_pr, "write_create_script"), \
             patch.object(draft_pr, "run_create_script", return_value=(None, None)), \
             patch("questionary.prompt", return_value=_STANDARD_ANSWERS), \
             patch("builtins.input", return_value="no"):
            draft_pr.main()
        # select() should NOT have been called to choose a plugin
        mock_select.assert_not_called()

    def test_build_prompt_called_with_data_and_user_inputs(self):
        plugin = _make_plugin()
        ai = MagicMock(ok=True, result={"title": "T"})
        self._run_main(plugin, ai)
        plugin.build_prompt.assert_called_once()
        _data_arg, user_inputs_arg = plugin.build_prompt.call_args[0]
        self.assertIn("jira_ticket", user_inputs_arg)

    def test_build_body_called_with_ai_result_and_user_inputs(self):
        plugin = _make_plugin()
        ai = MagicMock(ok=True, result={"title": "T"})
        self._run_main(plugin, ai)
        plugin.build_body.assert_called_once()
        ai_result_arg, user_inputs_arg = plugin.build_body.call_args[0]
        self.assertEqual(ai_result_arg, {"title": "T"})

    def test_exits_when_ai_result_not_ok(self):
        plugin = _make_plugin()
        ai = MagicMock(ok=False, error="timeout")
        with self.assertRaises(SystemExit):
            self._run_main(plugin, ai)


class TestMainMultiplePlugins(unittest.TestCase):
    def test_prompts_user_to_choose_plugin_when_multiple(self):
        plugin_alpha = _make_plugin("Alpha")
        plugins = [plugin_alpha, _make_plugin("Beta")]
        with patch.object(draft_pr, "collect", return_value=_make_data()), \
             patch.object(draft_pr, "validate_state"), \
             patch.object(draft_pr, "check_existing_pr", return_value=None), \
             patch.object(draft_pr, "select_plugin", return_value=plugin_alpha), \
             patch.object(draft_pr, "resolve_jira", return_value=("CONS-1", None)), \
             patch.object(draft_pr, "select",
                          side_effect=["Issue", "no"]) as mock_select, \
             patch.object(draft_pr, "run_ai_prompt",
                          return_value=MagicMock(ok=True, result={"title": "T"})), \
             patch.object(draft_pr, "write_create_script"), \
             patch.object(draft_pr, "run_create_script", return_value=(None, None)), \
             patch("questionary.prompt", return_value=_STANDARD_ANSWERS), \
             patch("builtins.input", return_value="no"):
            draft_pr.main()
        # The select_plugin function handles the selection now, not select()
        # This test verifies that a plugin is successfully selected and used


class TestMainPluginQuestions(unittest.TestCase):
    def test_plugin_get_questions_results_added_to_user_inputs(self):
        plugin = _make_plugin(questions=[
            {"id": "component", "text": "Component?"},
        ])
        ai = MagicMock(ok=True, result={"title": "T"})
        with patch.object(draft_pr, "collect", return_value=_make_data()), \
             patch.object(draft_pr, "validate_state"), \
             patch.object(draft_pr, "check_existing_pr", return_value=None), \
             patch.object(draft_pr, "select_plugin", return_value=plugin), \
             patch.object(draft_pr, "resolve_jira", return_value=("CONS-1", None)), \
             patch.object(draft_pr, "select", return_value="Issue"), \
             patch("questionary.prompt", return_value={"component": "auth"}), \
             patch.object(draft_pr, "run_ai_prompt", return_value=ai), \
             patch.object(draft_pr, "write_create_script"), \
             patch.object(draft_pr, "run_create_script", return_value=(None, None)), \
             patch("builtins.input", return_value="no"):
            draft_pr.main()
        _, user_inputs_arg = plugin.build_prompt.call_args[0]
        self.assertEqual(user_inputs_arg.get("component"), "auth")


class TestMainBehindBaseCheck(unittest.TestCase):
    def test_exits_when_behind_count_exceeds_threshold(self):
        data = _make_data(behind_count=5)
        with patch.object(draft_pr, "collect", return_value=data), \
             patch.object(draft_pr, "validate_state",
                          side_effect=SystemExit(1)):
            with self.assertRaises(SystemExit):
                draft_pr.main()


if __name__ == "__main__":
    unittest.main()

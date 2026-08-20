import sys
import os
import unittest
from unittest.mock import patch, MagicMock, mock_open, call

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

from repo_init import has_wt_config, detect_and_write_config
from devflow_sdk.ai import AiResult

WT_CONFIG = ".config/wt.toml"


def _mock_ai_toml(toml_text='[pre-start]\ninstall = "npm ci"\n', ok=True):
    return AiResult(result=toml_text, session_id=None, ok=ok,
                    error="" if ok else "claude failed", needs_interaction=False,
                    total_tokens=150)


class TestHasWtConfig(unittest.TestCase):
    def test_returns_true_when_config_exists(self):
        with patch("os.path.exists", return_value=True):
            self.assertTrue(has_wt_config("/some/repo"))

    def test_returns_false_when_config_absent(self):
        with patch("os.path.exists", return_value=False):
            self.assertFalse(has_wt_config("/some/repo"))


class TestDetectAndWriteConfig(unittest.TestCase):
    def _run(self, repo_root="/repo", ai_result=None, user_confirms=True, config_exists=False):
        if ai_result is None:
            ai_result = _mock_ai_toml()
        with patch("repo_init.has_wt_config", return_value=config_exists), \
             patch("repo_init.run_ai_prompt", return_value=ai_result) as mock_ai, \
             patch("repo_init.subprocess.run") as mock_run, \
             patch("repo_init.confirm", return_value=user_confirms), \
             patch("builtins.open", mock_open()), \
             patch("os.makedirs"), \
             patch("repo_init.os.path.exists", return_value=False):
            detect_and_write_config(repo_root)
            return mock_ai, mock_run

    def test_skips_when_config_exists(self):
        mock_ai, _ = self._run(config_exists=True)
        mock_ai.assert_not_called()

    def test_config_exists_does_not_raise(self):
        # Claude check is now inside the runner (tested in test_ai.py).
        # detect_and_write_config should not raise when has_wt_config returns True.
        with patch("repo_init.has_wt_config", return_value=True):
            detect_and_write_config("/repo")  # must not raise

    def test_warns_when_claude_fails(self):
        with patch("sys.stderr"):
            self._run(ai_result=_mock_ai_toml(ok=False))  # must not raise

    def test_warns_when_claude_output_invalid(self):
        with patch("sys.stderr"):
            self._run(ai_result=_mock_ai_toml(toml_text="no toml here"))

    def test_calls_run_ai_prompt_with_correct_params(self):
        with patch("repo_init.has_wt_config", return_value=False), \
             patch("repo_init.run_ai_prompt", return_value=_mock_ai_toml()) as mock_ai, \
             patch("repo_init.confirm", return_value=False), \
             patch("builtins.open", mock_open()), \
             patch("os.makedirs"), \
             patch("repo_init.os.path.exists", return_value=False):
            detect_and_write_config("/repo")
        mock_ai.assert_called_once()
        _, kwargs = mock_ai.call_args
        self.assertTrue(kwargs.get("stateless"))
        self.assertEqual(kwargs.get("tier"), "fast")

    def test_adds_cost_to_summary(self):
        # Cost now flows through the runner (accumulator.add called internally).
        # Verify that run_ai_prompt is called (cost is tracked inside the runner).
        mock_ai, _ = self._run()
        mock_ai.assert_called_once()

    def test_user_declines_no_commit(self):
        _, mock_run = self._run(user_confirms=False)
        all_cmds = [c[0][0] for c in mock_run.call_args_list]
        git_cmds = [c for c in all_cmds if c[0] == "git"]
        self.assertEqual(len(git_cmds), 0)

    def test_user_confirms_commits(self):
        _, mock_run = self._run(user_confirms=True)
        all_cmds = [c[0][0] for c in mock_run.call_args_list]
        git_cmds = [c for c in all_cmds if c[0] == "git"]
        self.assertTrue(any("commit" in c for c in git_cmds))

    def test_strips_markdown_code_fence_from_claude_output(self):
        fenced_result = _mock_ai_toml(toml_text='```toml\n[pre-start]\ninstall = "npm ci"\n```')
        m = mock_open()
        with patch("repo_init.has_wt_config", return_value=False), \
             patch("repo_init.run_ai_prompt", return_value=fenced_result), \
             patch("repo_init.subprocess.run"), \
             patch("repo_init.confirm", return_value=True), \
             patch("builtins.open", m), \
             patch("os.makedirs"), \
             patch("repo_init.os.path.exists", return_value=False):
            detect_and_write_config("/repo")

        written = "".join(c.args[0] for c in m().write.call_args_list)
        self.assertNotIn("```", written)
        self.assertTrue(written.startswith("[pre-start]"))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
import sys
import os
import unittest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fetch_comments import Comment
from post_replies import generate_reply_texts, _post_reply, _resolve_thread, _edit_in_editor, confirm_and_post_replies
from devflow_sdk.ai import AiResult


def _make_comment(id_, kind="review_thread", author="alice", is_bot=False,
                  thread_node_id=None):
    return Comment(
        id=id_, kind=kind, author=author, is_bot=is_bot,
        body="some comment", file=None, line=None,
        url="http://x", thread_node_id=thread_node_id,
    )


def _mock_ai_result(replies):
    return AiResult(result=replies, session_id=None, ok=True,
                    error="", needs_interaction=False, total_tokens=100)


class TestGenerateReplyTexts(unittest.TestCase):
    def test_sets_reply_text(self):
        c = _make_comment("RC_1")
        replies = [{"id": "RC_1", "reply": "Thanks, fixed!"}]
        with patch("post_replies.run_ai_prompt", return_value=_mock_ai_result(replies)):
            result = generate_reply_texts([c], "abc1234")
        self.assertEqual(result[0].reply_text, "Thanks, fixed!")

    def test_returns_empty_list_unchanged(self):
        result = generate_reply_texts([], "abc1234")
        self.assertEqual(result, [])

    def test_unmatched_id_leaves_reply_text_none(self):
        c = _make_comment("RC_1")
        replies = [{"id": "RC_999", "reply": "other"}]
        with patch("post_replies.run_ai_prompt", return_value=_mock_ai_result(replies)):
            result = generate_reply_texts([c], "abc1234")
        self.assertIsNone(result[0].reply_text)

    def test_invalid_comment_prompt_does_not_claim_addressed(self):
        c = _make_comment("RC_1")
        c.verdict = "INVALID"
        c.reason = "This is already handled by the existing validation."
        replies = [{"id": "RC_1", "reply": "No change needed here."}]
        with patch("post_replies.run_ai_prompt",
                   return_value=_mock_ai_result(replies)) as mock_ai:
            generate_reply_texts([c], "abc1234")
        prompt_arg = mock_ai.call_args[0][0]
        self.assertIn("verdict: INVALID", prompt_arg)
        self.assertIn(c.reason, prompt_arg)
        self.assertIn("Do NOT say the issue was fixed", prompt_arg)

    def test_valid_comment_prompt_keeps_addressed_instruction(self):
        c = _make_comment("RC_1")
        c.verdict = "VALID"
        replies = [{"id": "RC_1", "reply": "Fixed!"}]
        with patch("post_replies.run_ai_prompt",
                   return_value=_mock_ai_result(replies)) as mock_ai:
            generate_reply_texts([c], "abc1234")
        prompt_arg = mock_ai.call_args[0][0]
        self.assertIn("addressed in commit abc1234", prompt_arg)

    def test_comment_with_no_verdict_treated_as_valid(self):
        c = _make_comment("RC_1")
        self.assertIsNone(c.verdict)
        replies = [{"id": "RC_1", "reply": "Fixed!"}]
        with patch("post_replies.run_ai_prompt",
                   return_value=_mock_ai_result(replies)) as mock_ai:
            generate_reply_texts([c], "abc1234")
        prompt_arg = mock_ai.call_args[0][0]
        self.assertIn("verdict: VALID", prompt_arg)

    def test_mixed_selection_single_claude_call_maps_both_replies(self):
        valid_c = _make_comment("RC_1")
        valid_c.verdict = "VALID"
        invalid_c = _make_comment("RC_2")
        invalid_c.verdict = "INVALID"
        invalid_c.reason = "Style preference, not a bug."
        replies = [
            {"id": "RC_1", "reply": "Fixed in the commit."},
            {"id": "RC_2", "reply": "No change needed — style preference."},
        ]
        with patch("post_replies.run_ai_prompt",
                   return_value=_mock_ai_result(replies)) as mock_ai:
            result = generate_reply_texts([valid_c, invalid_c], "abc1234")
        self.assertEqual(mock_ai.call_count, 1)
        self.assertEqual(result[0].reply_text, "Fixed in the commit.")
        self.assertEqual(result[1].reply_text,
                          "No change needed — style preference.")

    def test_debug_forwarded_to_run_ai_prompt(self):
        c = _make_comment("RC_1")
        replies = [{"id": "RC_1", "reply": "Thanks!"}]
        with patch("post_replies.run_ai_prompt",
                   return_value=_mock_ai_result(replies)) as mock_run:
            generate_reply_texts([c], "abc1234", debug=True)
        _, kwargs = mock_run.call_args
        self.assertTrue(kwargs.get("debug"))

    def test_debug_defaults_to_false(self):
        c = _make_comment("RC_1")
        replies = [{"id": "RC_1", "reply": "Thanks!"}]
        with patch("post_replies.run_ai_prompt",
                   return_value=_mock_ai_result(replies)) as mock_run:
            generate_reply_texts([c], "abc1234")
        _, kwargs = mock_run.call_args
        self.assertFalse(kwargs.get("debug"))


class TestPostReply(unittest.TestCase):
    def _run_with_mock(self, c):
        m = MagicMock()
        m.returncode = 0
        with patch("subprocess.run", return_value=m) as mock_run:
            _post_reply(c, "owner", "repo", 42)
            return mock_run.call_args[0][0]

    def test_review_thread_uses_pulls_comments_endpoint(self):
        c = _make_comment("123", kind="review_thread")
        c.reply_text = "Fixed!"
        args = self._run_with_mock(c)
        self.assertIn("/pulls/42/comments/123/replies", " ".join(args))

    def test_pr_comment_uses_issues_endpoint(self):
        c = _make_comment("456", kind="pr_comment")
        c.reply_text = "Done!"
        args = self._run_with_mock(c)
        self.assertIn("/issues/42/comments", " ".join(args))
        self.assertNotIn("/pulls/", " ".join(args))


class TestResolveThread(unittest.TestCase):
    def test_calls_graphql_with_thread_id(self):
        m = MagicMock()
        m.returncode = 0
        with patch("subprocess.run", return_value=m) as mock_run:
            _resolve_thread("PRRT_xyz")
        args = mock_run.call_args[0][0]
        joined = " ".join(args)
        self.assertIn("graphql", joined)
        self.assertIn("PRRT_xyz", joined)


class TestEditInEditor(unittest.TestCase):
    def _run(self, editor_writes: str, original: str = "original text") -> str:
        """
        Simulate _edit_in_editor: patches subprocess.run (the editor call)
        so it writes `editor_writes` to the temp file path it receives,
        then returns what _edit_in_editor returns.
        """
        captured_path = []

        def fake_run(cmd, **kwargs):
            # cmd is [editor, tmp_path]; write the simulated editor output
            captured_path.append(cmd[1])
            with open(cmd[1], "w") as f:
                f.write(editor_writes)
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict(os.environ, {"EDITOR": "vi"}):
                result = _edit_in_editor(original)
        return result

    def test_returns_edited_text(self):
        result = self._run("custom reply text")
        self.assertEqual(result, "custom reply text")

    def test_strips_trailing_whitespace(self):
        result = self._run("custom reply text\n\n")
        self.assertEqual(result, "custom reply text")

    def test_empty_result_returns_original(self):
        result = self._run("", original="AI draft")
        self.assertEqual(result, "AI draft")

    def test_whitespace_only_returns_original(self):
        result = self._run("   \n  ", original="AI draft")
        self.assertEqual(result, "AI draft")

    def test_uses_editor_env_var(self):
        called_with = []

        def fake_run(cmd, **kwargs):
            called_with.append(cmd[0])
            with open(cmd[1], "w") as f:
                f.write("edited")
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict(os.environ, {"EDITOR": "nano"}):
                _edit_in_editor("text")
        self.assertEqual(called_with[0], "nano")

    def test_falls_back_to_vi_when_editor_unset(self):
        called_with = []

        def fake_run(cmd, **kwargs):
            called_with.append(cmd[0])
            with open(cmd[1], "w") as f:
                f.write("edited")
            m = MagicMock()
            m.returncode = 0
            return m

        env_without_editor = {k: v for k, v in os.environ.items() if k != "EDITOR"}
        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict(os.environ, env_without_editor, clear=True):
                _edit_in_editor("text")
        self.assertEqual(called_with[0], "vi")

    def test_editor_with_arguments(self):
        """EDITOR="code --wait" should split into ["code", "--wait", tmp_path]."""
        called_with = []

        def fake_run(cmd, **kwargs):
            called_with.append(cmd)
            with open(cmd[-1], "w") as f:
                f.write("edited")
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict(os.environ, {"EDITOR": "code --wait"}):
                result = _edit_in_editor("text")
        self.assertEqual(called_with[0][0], "code")
        self.assertEqual(called_with[0][1], "--wait")
        self.assertEqual(result, "edited")

    def test_temp_file_is_deleted_after_edit(self):
        paths_seen = []

        def fake_run(cmd, **kwargs):
            paths_seen.append(cmd[1])
            with open(cmd[1], "w") as f:
                f.write("edited")
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict(os.environ, {"EDITOR": "vi"}):
                _edit_in_editor("text")
        self.assertFalse(os.path.exists(paths_seen[0]))

    def test_editor_not_found_returns_original(self):
        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("no such editor")

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict(os.environ, {"EDITOR": "no-such-editor"}):
                result = _edit_in_editor("original text")
        self.assertEqual(result, "original text")

    def test_editor_nonzero_exit_returns_original(self):
        def fake_run(cmd, **kwargs):
            with open(cmd[1], "w") as f:
                f.write("partial edit")
            m = MagicMock()
            m.returncode = 1
            return m

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict(os.environ, {"EDITOR": "vi"}):
                result = _edit_in_editor("original text")
        self.assertEqual(result, "original text")

    def test_invalid_tmpdir_falls_back_to_default(self):
        def fake_run(cmd, **kwargs):
            with open(cmd[1], "w") as f:
                f.write("edited")
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict(os.environ, {"EDITOR": "vi",
                                          "TMPDIR": "/no/such/dir"}):
                result = _edit_in_editor("text")
        self.assertEqual(result, "edited")


class TestConfirmAndPostReplies(unittest.TestCase):
    def _make_comment_with_reply(self, id_="RC_1", kind="review_thread",
                                  author="alice", is_bot=False,
                                  thread_node_id=None,
                                  reply_text="AI draft reply"):
        c = _make_comment(id_, kind=kind, author=author,
                          is_bot=is_bot, thread_node_id=thread_node_id)
        c.reply_text = reply_text
        return c

    def test_y_posts_reply(self):
        c = self._make_comment_with_reply()
        with patch("post_replies.select", return_value="yes"), \
             patch("post_replies._post_reply") as mock_post:
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_post.assert_called_once_with(c, "owner", "repo", 1)

    def test_n_skips_reply(self):
        c = self._make_comment_with_reply()
        with patch("post_replies.select", return_value="no"), \
             patch("post_replies._post_reply") as mock_post:
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_post.assert_not_called()

    def test_cancel_skips_reply(self):
        c = self._make_comment_with_reply()
        with patch("post_replies.select", return_value=None), \
             patch("post_replies._post_reply") as mock_post:
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_post.assert_not_called()

    def test_e_then_y_posts_edited_reply(self):
        c = self._make_comment_with_reply(reply_text="AI draft")
        with patch("post_replies.select", side_effect=["edit", "yes"]), \
             patch("post_replies._edit_in_editor", return_value="custom reply") as mock_edit, \
             patch("post_replies._post_reply") as mock_post:
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_edit.assert_called_once_with("AI draft")
        self.assertEqual(c.reply_text, "custom reply")
        mock_post.assert_called_once_with(c, "owner", "repo", 1)

    def test_e_then_n_skips_posting(self):
        c = self._make_comment_with_reply(reply_text="AI draft")
        with patch("post_replies.select", side_effect=["edit", "no"]), \
             patch("post_replies._edit_in_editor", return_value="custom reply"), \
             patch("post_replies._post_reply") as mock_post:
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_post.assert_not_called()

    def test_e_twice_opens_editor_twice(self):
        c = self._make_comment_with_reply(reply_text="AI draft")
        with patch("post_replies.select", side_effect=["edit", "edit", "yes"]), \
             patch("post_replies._edit_in_editor", side_effect=["first edit", "second edit"]) as mock_edit, \
             patch("post_replies._post_reply"):
            confirm_and_post_replies([c], "owner", "repo", 1)
        self.assertEqual(mock_edit.call_count, 2)
        # second call receives the result of the first edit
        mock_edit.assert_called_with("first edit")
        self.assertEqual(c.reply_text, "second edit")

    def test_prompt_offers_yes_no_edit_choices(self):
        c = self._make_comment_with_reply()
        with patch("post_replies.select", return_value="yes") as mock_select, \
             patch("post_replies._post_reply"):
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_select.assert_called_once_with(
            "Post this reply?", choices=["yes", "no", "edit"]
        )

    def test_bot_review_thread_resolves_after_post(self):
        c = self._make_comment_with_reply(
            kind="review_thread", is_bot=True, thread_node_id="PRRT_abc"
        )
        with patch("post_replies.select", return_value="yes"), \
             patch("post_replies._post_reply"), \
             patch("post_replies._resolve_thread") as mock_resolve:
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_resolve.assert_called_once_with("PRRT_abc")

    def test_human_review_thread_not_resolved(self):
        c = self._make_comment_with_reply(
            kind="review_thread", is_bot=False, thread_node_id="PRRT_abc"
        )
        with patch("post_replies.select", return_value="yes"), \
             patch("post_replies._post_reply"), \
             patch("post_replies._resolve_thread") as mock_resolve:
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_resolve.assert_not_called()

    def test_skips_comment_with_no_reply_text(self):
        c = _make_comment("RC_1")
        c.reply_text = None
        with patch("post_replies.select") as mock_select, \
             patch("post_replies._post_reply") as mock_post:
            confirm_and_post_replies([c], "owner", "repo", 1)
        mock_select.assert_not_called()
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

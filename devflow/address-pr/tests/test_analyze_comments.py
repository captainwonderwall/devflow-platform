#!/usr/bin/env python3
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fetch_comments import Comment
from analyze_comments import build_analysis_prompt, analyze_comments
from devflow_sdk.ai import AiResult


def _make_comment(id_, author="alice", body="fix this", file=None, line=None,
                  is_bot=False):
    return Comment(
        id=id_, kind="review_thread", author=author, is_bot=is_bot,
        body=body, file=file, line=line, url="http://x", thread_node_id=None,
    )


def _mock_ai_result(verdicts, session_id="sess-123", total_tokens=1_000):
    return AiResult(
        result=verdicts,
        session_id=session_id,
        ok=True,
        error="",
        needs_interaction=False,
        total_tokens=total_tokens,
    )


class TestBuildAnalysisPrompt(unittest.TestCase):
    def test_includes_pr_title(self):
        c = _make_comment("RC_1")
        prompt = build_analysis_prompt("My PR Title", "feature/x", [c])
        self.assertIn("My PR Title", prompt)

    def test_includes_comment_id(self):
        c = _make_comment("RC_abc")
        prompt = build_analysis_prompt("PR", "branch", [c])
        self.assertIn("RC_abc", prompt)

    def test_truncates_long_body(self):
        c = _make_comment("RC_1", body="x" * 400)
        prompt = build_analysis_prompt("PR", "branch", [c])
        self.assertNotIn("x" * 400, prompt)
        self.assertIn("x" * 300, prompt)

    def test_includes_file_and_line_for_inline(self):
        c = _make_comment("RC_1", file="src/auth.py", line=42)
        prompt = build_analysis_prompt("PR", "branch", [c])
        self.assertIn("src/auth.py", prompt)
        self.assertIn("42", prompt)

    def test_bot_label_in_prompt(self):
        c = _make_comment("RC_1", author="dependabot[bot]", is_bot=True)
        prompt = build_analysis_prompt("PR", "branch", [c])
        self.assertIn("[bot]", prompt)

    def test_includes_file_reading_instruction(self):
        c = _make_comment("RC_1", file="src/auth.py", line=42)
        prompt = build_analysis_prompt("PR", "branch", [c])
        self.assertIn("read that file", prompt)


class TestAnalyzeComments(unittest.TestCase):
    def test_sets_verdict_and_reason(self):
        c = _make_comment("RC_1")
        verdicts = [{"id": "RC_1", "verdict": "VALID", "reason": "good reason"}]
        with patch("analyze_comments.run_ai_prompt",
                   return_value=_mock_ai_result(verdicts)):
            result, _ = analyze_comments("PR", "branch", [c])
        self.assertEqual(result[0].verdict, "VALID")
        self.assertEqual(result[0].reason, "good reason")

    def test_returns_empty_list_unchanged(self):
        result, session_id = analyze_comments("PR", "branch", [])
        self.assertEqual(result, [])
        self.assertIsNone(session_id)

    def test_unmatched_id_leaves_verdict_none(self):
        c = _make_comment("RC_1")
        verdicts = [{"id": "RC_999", "verdict": "VALID", "reason": "other"}]
        with patch("analyze_comments.run_ai_prompt",
                   return_value=_mock_ai_result(verdicts)):
            result, _ = analyze_comments("PR", "branch", [c])
        self.assertIsNone(result[0].verdict)

    def test_returns_session_id_when_under_threshold(self):
        c = _make_comment("RC_1")
        verdicts = [{"id": "RC_1", "verdict": "VALID", "reason": "ok"}]
        with patch("analyze_comments.run_ai_prompt",
                   return_value=_mock_ai_result(verdicts, session_id="sess-abc",
                                                total_tokens=1_000)):
            _, session_id = analyze_comments("PR", "branch", [c])
        self.assertEqual(session_id, "sess-abc")

    def test_returns_none_when_over_threshold(self):
        c = _make_comment("RC_1")
        verdicts = [{"id": "RC_1", "verdict": "VALID", "reason": "ok"}]
        with patch("analyze_comments.run_ai_prompt",
                   return_value=_mock_ai_result(verdicts, session_id="sess-abc",
                                                total_tokens=160_000)):
            _, session_id = analyze_comments("PR", "branch", [c])
        self.assertIsNone(session_id)

    def test_debug_forwarded_to_run_ai_prompt(self):
        c = _make_comment("RC_1")
        verdicts = [{"id": "RC_1", "verdict": "VALID", "reason": "ok"}]
        with patch("analyze_comments.run_ai_prompt",
                   return_value=_mock_ai_result(verdicts)) as mock_run:
            analyze_comments("My PR", "feature/x", [c], debug=True)
        _, kwargs = mock_run.call_args
        self.assertTrue(kwargs.get("debug"))

    def test_debug_defaults_to_false(self):
        c = _make_comment("RC_1")
        verdicts = [{"id": "RC_1", "verdict": "VALID", "reason": "ok"}]
        with patch("analyze_comments.run_ai_prompt",
                   return_value=_mock_ai_result(verdicts)) as mock_run:
            analyze_comments("My PR", "feature/x", [c])
        _, kwargs = mock_run.call_args
        self.assertFalse(kwargs.get("debug"))


if __name__ == "__main__":
    unittest.main()

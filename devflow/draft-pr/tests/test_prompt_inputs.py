#!/usr/bin/env python3
import sys
import os
import io
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from prompt_inputs import build_questions, load_stdin_json


class TestBuildQuestions(unittest.TestCase):
    def _base(self):
        return {"jira_ticket": "CONS-123", "issue_type": "Feature"}

    def test_always_includes_customer_visible(self):
        questions = build_questions(self._base())
        ids = [q["id"] for q in questions]
        self.assertIn("customer_visible", ids)

    def test_no_jira_question_when_ticket_present(self):
        questions = build_questions(self._base())
        ids = [q["id"] for q in questions]
        self.assertNotIn("jira_ticket", ids)

    def test_asks_jira_when_ticket_missing(self):
        data = {**self._base(), "jira_ticket": None}
        questions = build_questions(data)
        ids = [q["id"] for q in questions]
        self.assertIn("jira_ticket", ids)

    def test_asks_jira_when_ticket_empty_string(self):
        data = {**self._base(), "jira_ticket": ""}
        questions = build_questions(data)
        ids = [q["id"] for q in questions]
        self.assertIn("jira_ticket", ids)

    def test_no_type_question_when_type_present(self):
        questions = build_questions(self._base())
        ids = [q["id"] for q in questions]
        self.assertNotIn("issue_type", ids)

    def test_asks_type_when_type_missing(self):
        data = {**self._base(), "issue_type": None}
        questions = build_questions(data)
        ids = [q["id"] for q in questions]
        self.assertIn("issue_type", ids)

    def test_question_text_is_non_empty_string(self):
        questions = build_questions(self._base())
        for q in questions:
            self.assertIsInstance(q["text"], str)
            self.assertTrue(len(q["text"]) > 0)

    def test_customer_visible_question_mentions_yes_no(self):
        questions = build_questions(self._base())
        cv = next(q for q in questions if q["id"] == "customer_visible")
        self.assertIn("Yes", cv["text"])
        self.assertIn("No", cv["text"])

    def test_issue_type_question_lists_options(self):
        data = {**self._base(), "issue_type": None}
        questions = build_questions(data)
        type_q = next(q for q in questions if q["id"] == "issue_type")
        self.assertIn("Feature", type_q["text"])
        self.assertIn("Enhancement", type_q["text"])

    def test_order_jira_before_type_before_customer(self):
        data = {"jira_ticket": None, "issue_type": None}
        questions = build_questions(data)
        ids = [q["id"] for q in questions]
        self.assertLess(ids.index("jira_ticket"), ids.index("issue_type"))
        self.assertLess(ids.index("issue_type"), ids.index("customer_visible"))


class TestLoadStdinJson(unittest.TestCase):
    def test_valid_json_returns_data(self):
        stream = io.StringIO('{"branch": "feature/CONS-123"}')
        data = load_stdin_json(stream)
        self.assertEqual(data, {"branch": "feature/CONS-123"})

    def test_invalid_json_exits_nonzero(self):
        stream = io.StringIO("not json")
        with self.assertRaises(SystemExit):
            load_stdin_json(stream)

    def test_empty_stdin_exits_nonzero(self):
        stream = io.StringIO("")
        with self.assertRaises(SystemExit):
            load_stdin_json(stream)


if __name__ == "__main__":
    unittest.main()

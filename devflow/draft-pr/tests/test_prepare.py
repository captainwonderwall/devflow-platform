#!/usr/bin/env python3
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from prepare import validate_state, format_output


class TestValidateState(unittest.TestCase):
    def _valid(self):
        return {"branch": "feature/CONS-123", "base": "main", "git_log": "abc123 Add thing"}

    def test_passes_with_valid_state(self):
        validate_state(self._valid())  # must not raise

    def test_exits_when_branch_is_none(self):
        with self.assertRaises(SystemExit):
            validate_state({"branch": None, "base": "main", "git_log": "abc"})

    def test_exits_when_branch_is_empty(self):
        with self.assertRaises(SystemExit):
            validate_state({"branch": "", "base": "main", "git_log": "abc"})

    def test_exits_when_on_main_base_branch(self):
        with self.assertRaises(SystemExit):
            validate_state({"branch": "main", "base": "main", "git_log": "abc"})

    def test_exits_when_on_master_base_branch(self):
        with self.assertRaises(SystemExit):
            validate_state({"branch": "master", "base": "master", "git_log": "abc"})

    def test_exits_when_on_develop_base_branch(self):
        with self.assertRaises(SystemExit):
            validate_state({"branch": "develop", "base": "develop", "git_log": "abc"})

    def test_does_not_exit_when_branch_differs_from_base(self):
        # e.g. repo default is develop, user is on a feature branch named master
        validate_state({"branch": "master", "base": "develop", "git_log": "abc"})  # must not raise

    def test_exits_when_no_commits(self):
        with self.assertRaises(SystemExit):
            validate_state({"branch": "feature/CONS-123", "base": "main", "git_log": ""})

    def test_exits_when_git_log_none(self):
        with self.assertRaises(SystemExit):
            validate_state({"branch": "feature/CONS-123", "base": "main", "git_log": None})

    def test_falls_back_to_main_when_base_missing(self):
        # data without "base" key — guard should still work using "main" fallback
        validate_state({"branch": "feature/CONS-123", "git_log": "abc"})  # must not raise

    def test_exits_when_base_missing_and_branch_is_master(self):
        # Backward compatibility: previously master was always blocked via
        # MAIN_BRANCHES, regardless of detected base. If base detection is
        # missing entirely, master must still be blocked.
        with self.assertRaises(SystemExit):
            validate_state({"branch": "master", "git_log": "abc"})

    def test_exits_when_base_missing_and_branch_is_main(self):
        with self.assertRaises(SystemExit):
            validate_state({"branch": "main", "git_log": "abc"})


class TestFormatOutput(unittest.TestCase):
    def _data(self):
        return {"branch": "feature/CONS-123", "git_log": "abc123 Add thing", "diff_stat": "1 file changed"}

    def _questions(self):
        return {"questions": [{"id": "customer_visible", "text": "Is this customer visible? (Yes/No)"}]}

    def test_contains_data_section(self):
        output = format_output(self._data(), self._questions())
        self.assertIn("DATA:", output)

    def test_contains_questions_section(self):
        output = format_output(self._data(), self._questions())
        self.assertIn("QUESTIONS:", output)

    def test_data_section_contains_json(self):
        output = format_output(self._data(), self._questions())
        self.assertIn('"branch"', output)

    def test_questions_numbered(self):
        output = format_output(self._data(), self._questions())
        self.assertIn("1.", output)

    def test_question_text_verbatim(self):
        output = format_output(self._data(), self._questions())
        self.assertIn("Is this customer visible? (Yes/No)", output)

    def test_data_before_questions(self):
        output = format_output(self._data(), self._questions())
        self.assertLess(output.index("DATA:"), output.index("QUESTIONS:"))


if __name__ == "__main__":
    unittest.main()

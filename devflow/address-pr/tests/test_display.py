#!/usr/bin/env python3
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from display import resolve_selection
from unittest.mock import patch
from fetch_comments import Comment


class TestResolveSelection(unittest.TestCase):
    def test_all_and_none_both_checked_is_error(self):
        indices, error = resolve_selection(["all", "none"], 5)
        self.assertIsNone(indices)
        self.assertEqual(error, 'Cannot select both "all" and "none" — pick one.')

    def test_all_and_none_with_individual_items_is_still_error(self):
        indices, error = resolve_selection(["1", "all", "none"], 5)
        self.assertIsNone(indices)
        self.assertEqual(error, 'Cannot select both "all" and "none" — pick one.')

    def test_nothing_checked_is_error(self):
        indices, error = resolve_selection([], 5)
        self.assertIsNone(indices)
        self.assertEqual(error, "Select at least one option.")

    def test_none_alone_signals_quit(self):
        indices, error = resolve_selection(["none"], 5)
        self.assertIsNone(indices)
        self.assertIsNone(error)

    def test_all_alone_selects_full_range(self):
        indices, error = resolve_selection(["all"], 3)
        self.assertEqual(indices, [0, 1, 2])
        self.assertIsNone(error)

    def test_individual_items_resolved_to_zero_based_indices(self):
        indices, error = resolve_selection(["1", "3"], 5)
        self.assertEqual(indices, [0, 2])
        self.assertIsNone(error)

    def test_individual_items_sorted_regardless_of_check_order(self):
        indices, error = resolve_selection(["3", "1", "2"], 5)
        self.assertEqual(indices, [0, 1, 2])
        self.assertIsNone(error)

    def test_single_individual_item(self):
        indices, error = resolve_selection(["2"], 5)
        self.assertEqual(indices, [1])
        self.assertIsNone(error)


def _make_comment(author="alice", is_bot=False, kind="review_thread",
                   file="foo.py", line=10, body="a comment"):
    return Comment(
        id="1",
        kind=kind,
        author=author,
        is_bot=is_bot,
        body=body,
        file=file,
        line=line,
        url="https://example.com",
        thread_node_id=None,
    )


class TestPromptSelection(unittest.TestCase):
    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_returns_indices_on_valid_submission(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = ["1"]
        from display import prompt_selection
        comments = [_make_comment(), _make_comment()]
        result = prompt_selection(comments)
        self.assertEqual(result, [0])

    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_all_resolves_to_every_index(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = ["all"]
        from display import prompt_selection
        comments = [_make_comment(), _make_comment(), _make_comment()]
        result = prompt_selection(comments)
        self.assertEqual(result, [0, 1, 2])

    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_none_returns_none(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = ["none"]
        from display import prompt_selection
        comments = [_make_comment()]
        result = prompt_selection(comments)
        self.assertIsNone(result)

    @patch("builtins.print")
    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_ctrl_c_returns_none_immediately(self, mock_checkbox, mock_print):
        mock_checkbox.return_value.ask.return_value = None
        from display import prompt_selection
        comments = [_make_comment()]
        result = prompt_selection(comments)
        self.assertIsNone(result)
        mock_checkbox.return_value.ask.assert_called_once()

    @patch("builtins.print")
    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_invalid_combo_reprompts_then_succeeds(self, mock_checkbox, mock_print):
        mock_checkbox.return_value.ask.side_effect = [["all", "none"], ["1"]]
        from display import prompt_selection
        comments = [_make_comment(), _make_comment()]
        result = prompt_selection(comments)
        self.assertEqual(result, [0])
        self.assertEqual(mock_checkbox.return_value.ask.call_count, 2)
        mock_print.assert_any_call('Cannot select both "all" and "none" — pick one.')

    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_choice_labels_include_author_and_location(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = ["1"]
        from display import prompt_selection
        comments = [_make_comment(author="bob", is_bot=True, kind="review_thread",
                                   file="bar.py", line=42)]
        prompt_selection(comments)
        _, kwargs = mock_checkbox.call_args
        choice_titles = [c.title for c in kwargs["choices"]]
        self.assertIn("[1] @bob (bot) — inline: bar.py:42", choice_titles)
        self.assertIn("all", choice_titles)
        self.assertIn("none", choice_titles)

    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_pr_comment_location_label(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = ["1"]
        from display import prompt_selection
        comments = [_make_comment(kind="pr_comment", file=None, line=None)]
        prompt_selection(comments)
        _, kwargs = mock_checkbox.call_args
        choice_titles = [c.title for c in kwargs["choices"]]
        self.assertIn("[1] @alice — PR comment", choice_titles)


if __name__ == "__main__":
    unittest.main()

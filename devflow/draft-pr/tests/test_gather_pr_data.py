#!/usr/bin/env python3
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gather_pr_data import extract_prefix, extract_jira_ticket, is_fix, PREFIX_TO_TYPE, validate_data, get_base_branch, get_behind_count


class TestExtractPrefix(unittest.TestCase):
    def test_feature_prefix(self):
        self.assertEqual(extract_prefix("feature/CONS-123-something"), "feature")

    def test_fix_prefix(self):
        self.assertEqual(extract_prefix("fix/CONS-123-something"), "fix")

    def test_hotfix_prefix(self):
        self.assertEqual(extract_prefix("hotfix/CONS-123-something"), "hotfix")

    def test_no_slash_returns_none(self):
        self.assertIsNone(extract_prefix("no-prefix-branch"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(extract_prefix(""))

    def test_uppercase_prefix_returns_none(self):
        self.assertIsNone(extract_prefix("Feature/CONS-123"))


class TestExtractJiraTicket(unittest.TestCase):
    def test_extracts_ticket(self):
        self.assertEqual(extract_jira_ticket("feature/CONS-123-something"), "CONS-123")

    def test_no_ticket_returns_none(self):
        self.assertIsNone(extract_jira_ticket("feature/no-ticket"))

    def test_multiple_tickets_returns_first(self):
        self.assertEqual(extract_jira_ticket("feature/CONS-123-and-CONS-456"), "CONS-123")

    def test_empty_returns_none(self):
        self.assertIsNone(extract_jira_ticket(""))

    def test_lowercase_ticket_returns_none(self):
        self.assertIsNone(extract_jira_ticket("feature/cons-123"))


class TestIsFix(unittest.TestCase):
    def test_fix_prefix(self):
        self.assertTrue(is_fix("fix"))

    def test_bugfix_prefix(self):
        self.assertTrue(is_fix("bugfix"))

    def test_hotfix_prefix(self):
        self.assertTrue(is_fix("hotfix"))

    def test_feature_not_fix(self):
        self.assertFalse(is_fix("feature"))

    def test_none_not_fix(self):
        self.assertFalse(is_fix(None))

    def test_empty_not_fix(self):
        self.assertFalse(is_fix(""))


class TestPrefixToType(unittest.TestCase):
    def test_feature_maps_to_feature(self):
        self.assertEqual(PREFIX_TO_TYPE.get("feature"), "Feature")

    def test_fix_maps_to_issue(self):
        self.assertEqual(PREFIX_TO_TYPE.get("fix"), "Issue")

    def test_enhancement_maps_to_enhancement(self):
        self.assertEqual(PREFIX_TO_TYPE.get("enhancement"), "Enhancement")


class TestValidateData(unittest.TestCase):
    def test_passes_when_branch_present(self):
        validate_data({"branch": "feature/CONS-123"})  # must not raise

    def test_exits_when_branch_missing(self):
        with self.assertRaises(SystemExit):
            validate_data({"branch": None})

    def test_exits_when_branch_empty(self):
        with self.assertRaises(SystemExit):
            validate_data({"branch": ""})


class TestGetBaseBranch(unittest.TestCase):
    def test_returns_branch_from_origin_head(self):
        with patch("gather_pr_data.run_git", return_value="origin/main"):
            self.assertEqual(get_base_branch(), "main")

    def test_returns_develop_from_origin_head(self):
        with patch("gather_pr_data.run_git", return_value="origin/develop"):
            self.assertEqual(get_base_branch(), "develop")

    def test_falls_back_to_gh_when_origin_head_is_literal(self):
        # origin/HEAD can resolve to the literal string "origin/HEAD" in a
        # non-symref/odd remote state; this must not be treated as base "HEAD".
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "develop\n"
        with patch("gather_pr_data.run_git", return_value="origin/HEAD"), \
             patch("gather_pr_data.subprocess.run", return_value=mock_proc):
            self.assertEqual(get_base_branch(), "develop")

    def test_falls_back_to_gh_when_git_returns_none(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "develop\n"
        with patch("gather_pr_data.run_git", return_value=None), \
             patch("gather_pr_data.subprocess.run", return_value=mock_proc):
            self.assertEqual(get_base_branch(), "develop")

    def test_falls_back_to_gh_when_git_returns_no_slash(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "develop\n"
        with patch("gather_pr_data.run_git", return_value="HEAD"), \
             patch("gather_pr_data.subprocess.run", return_value=mock_proc):
            self.assertEqual(get_base_branch(), "develop")

    def test_falls_back_to_main_when_both_fail(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        with patch("gather_pr_data.run_git", return_value=None), \
             patch("gather_pr_data.subprocess.run", return_value=mock_proc):
            self.assertEqual(get_base_branch(), "main")

    def test_falls_back_to_main_when_gh_returns_empty(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "   \n"
        with patch("gather_pr_data.run_git", return_value=None), \
             patch("gather_pr_data.subprocess.run", return_value=mock_proc):
            self.assertEqual(get_base_branch(), "main")

    def test_falls_back_to_main_when_gh_not_found(self):
        with patch("gather_pr_data.run_git", return_value=None), \
             patch("gather_pr_data.subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(get_base_branch(), "main")


class TestGetBehindCount(unittest.TestCase):
    def test_returns_0_when_up_to_date(self):
        with patch("gather_pr_data.run_git", return_value="0"):
            self.assertEqual(get_behind_count("main"), 0)

    def test_returns_count_when_behind(self):
        with patch("gather_pr_data.run_git", return_value="3"):
            self.assertEqual(get_behind_count("main"), 3)

    def test_uses_correct_git_args_for_base(self):
        with patch("gather_pr_data.run_git") as mock_git:
            mock_git.return_value = "0"
            get_behind_count("develop")
        mock_git.assert_called_once_with(["rev-list", "--count", "HEAD..origin/develop"])

    def test_returns_0_when_git_fails(self):
        with patch("gather_pr_data.run_git", return_value=None):
            self.assertEqual(get_behind_count("main"), 0)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))        # draft-pr/ dir

from devflow_sdk.ticket_info import (
    is_jira_key, check_acli, check_gh,
    fetch_jira_ticket, fetch_github_issue, get_ticket_context, format_ticket_context,
)



class TestIsJiraKey(unittest.TestCase):
    def test_valid_key(self):
        self.assertTrue(is_jira_key("CONS-123"))

    def test_lowercase_rejected(self):
        self.assertFalse(is_jira_key("cons-123"))

    def test_free_text_rejected(self):
        self.assertFalse(is_jira_key("N/A"))

    def test_none_rejected(self):
        self.assertFalse(is_jira_key(None))

    def test_empty_string_rejected(self):
        self.assertFalse(is_jira_key(""))

    def test_trailing_text_rejected(self):
        self.assertFalse(is_jira_key("CONS-123-extra"))


class TestCheckAcli(unittest.TestCase):
    @patch("devflow_sdk.ticket_info.shutil.which", return_value=None)
    def test_exits_when_not_installed(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            check_acli()
        self.assertEqual(ctx.exception.code, 1)

    @patch("devflow_sdk.ticket_info.subprocess.run")
    @patch("devflow_sdk.ticket_info.shutil.which", return_value="/usr/local/bin/acli")
    def test_exits_when_not_authenticated(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        with self.assertRaises(SystemExit) as ctx:
            check_acli()
        self.assertEqual(ctx.exception.code, 1)

    @patch("devflow_sdk.ticket_info.subprocess.run")
    @patch("devflow_sdk.ticket_info.shutil.which", return_value="/usr/local/bin/acli")
    def test_passes_when_installed_and_authenticated(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        check_acli()  # must not raise


class TestCheckGh(unittest.TestCase):
    @patch("devflow_sdk.ticket_info.shutil.which", return_value=None)
    def test_exits_when_not_installed(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            check_gh()
        self.assertEqual(ctx.exception.code, 1)

    @patch("devflow_sdk.ticket_info.subprocess.run")
    @patch("devflow_sdk.ticket_info.shutil.which", return_value="/usr/local/bin/gh")
    def test_exits_when_not_authenticated(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        with self.assertRaises(SystemExit) as ctx:
            check_gh()
        self.assertEqual(ctx.exception.code, 1)

    @patch("devflow_sdk.ticket_info.subprocess.run")
    @patch("devflow_sdk.ticket_info.shutil.which", return_value="/usr/local/bin/gh")
    def test_passes_when_installed_and_authenticated(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        check_gh()  # must not raise


class TestFetchJiraTicket(unittest.TestCase):
    @patch("devflow_sdk.ticket_info.check_acli")
    @patch("devflow_sdk.ticket_info.subprocess.run")
    def test_returns_normalized_dict(self, mock_run, mock_check):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "fields": {
                    "summary": "Login fails on retry",
                    "description": "Users see a 500 error.",
                    "comment": {"comments": [{"body": "Confirmed in prod."}]},
                }
            }),
        )
        result = fetch_jira_ticket("CONS-123")
        self.assertEqual(result, {
            "source": "jira",
            "id": "CONS-123",
            "title": "Login fails on retry",
            "body": "Users see a 500 error.",
            "comments": ["Confirmed in prod."],
            "issuetype": "",
            "labels": [],
        })

    @patch("devflow_sdk.ticket_info.check_acli")
    @patch("devflow_sdk.ticket_info.subprocess.run")
    def test_returns_issuetype_when_present(self, mock_run, mock_check):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "fields": {
                    "summary": "Crash on login",
                    "description": "",
                    "comment": {},
                    "issuetype": {"name": "Bug"},
                }
            }),
        )
        result = fetch_jira_ticket("CONS-456")
        self.assertEqual(result["issuetype"], "Bug")

    @patch("devflow_sdk.ticket_info.check_acli")
    @patch("devflow_sdk.ticket_info.subprocess.run")
    def test_exits_on_command_failure(self, mock_run, mock_check):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        with self.assertRaises(SystemExit):
            fetch_jira_ticket("CONS-999")

    @patch("devflow_sdk.ticket_info.check_acli")
    @patch("devflow_sdk.ticket_info.subprocess.run")
    def test_exits_on_invalid_json(self, mock_run, mock_check):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        with self.assertRaises(SystemExit):
            fetch_jira_ticket("CONS-123")


class TestFetchGithubIssue(unittest.TestCase):
    @patch("devflow_sdk.ticket_info.check_gh")
    @patch("devflow_sdk.ticket_info.subprocess.run")
    def test_returns_normalized_dict(self, mock_run, mock_check):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "title": "draft-pr needs to extract information from JIRA",
                "body": "The draft-pr script needs to extract information...",
                "comments": [{"body": "Agreed, let's use acli."}],
                "labels": [],
            }),
        )
        result = fetch_github_issue("11")
        self.assertEqual(result, {
            "source": "github",
            "id": "11",
            "title": "draft-pr needs to extract information from JIRA",
            "body": "The draft-pr script needs to extract information...",
            "comments": ["Agreed, let's use acli."],
            "issuetype": "",
            "labels": [],
            "url": "",
        })

    @patch("devflow_sdk.ticket_info.check_gh")
    @patch("devflow_sdk.ticket_info.subprocess.run")
    def test_returns_labels_when_present(self, mock_run, mock_check):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "title": "Crash on export",
                "body": "",
                "comments": [],
                "labels": [{"name": "bug"}, {"name": "urgent"}],
            }),
        )
        result = fetch_github_issue("99")
        self.assertEqual(result["labels"], ["bug", "urgent"])

    @patch("devflow_sdk.ticket_info.check_gh")
    @patch("devflow_sdk.ticket_info.subprocess.run")
    def test_exits_on_command_failure(self, mock_run, mock_check):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        with self.assertRaises(SystemExit):
            fetch_github_issue("999")

    @patch("devflow_sdk.ticket_info.check_gh")
    @patch("devflow_sdk.ticket_info.subprocess.run")
    def test_exits_on_invalid_json(self, mock_run, mock_check):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        with self.assertRaises(SystemExit):
            fetch_github_issue("11")


class TestGetTicketContext(unittest.TestCase):
    @patch("devflow_sdk.ticket_info.fetch_jira_ticket")
    def test_valid_jira_key_wins(self, mock_fetch_jira):
        mock_fetch_jira.return_value = {
            "source": "jira", "id": "CONS-123",
            "title": "t", "body": "b", "comments": [],
            "issuetype": "Story", "labels": [],
        }
        result = get_ticket_context("CONS-123", "11")
        mock_fetch_jira.assert_called_once_with("CONS-123")
        self.assertEqual(result["source"], "jira")

    @patch("devflow_sdk.ticket_info.fetch_github_issue")
    def test_falls_back_to_github_issue_when_no_jira_key(self, mock_fetch_gh):
        mock_fetch_gh.return_value = {
            "source": "github", "id": "11",
            "title": "t", "body": "b", "comments": [],
            "issuetype": "", "labels": [],
        }
        result = get_ticket_context("N/A", "11")
        mock_fetch_gh.assert_called_once_with("11")
        self.assertEqual(result["source"], "github")

    @patch("devflow_sdk.ticket_info.fetch_github_issue")
    def test_falls_back_to_github_issue_when_jira_none(self, mock_fetch_gh):
        mock_fetch_gh.return_value = {
            "source": "github", "id": "11",
            "title": "t", "body": "b", "comments": [],
            "issuetype": "", "labels": [],
        }
        result = get_ticket_context(None, "11")
        mock_fetch_gh.assert_called_once_with("11")

    def test_returns_none_when_neither_present(self):
        self.assertIsNone(get_ticket_context(None, None))

    def test_returns_none_when_jira_invalid_and_no_github_issue(self):
        self.assertIsNone(get_ticket_context("N/A", None))


class TestFormatTicketContext(unittest.TestCase):
    def test_returns_empty_string_when_none(self):
        self.assertEqual(format_ticket_context(None), "")

    def test_includes_source_id_title_body_comments(self):
        ctx = {
            "source": "jira", "id": "CONS-123",
            "title": "Login fails on retry",
            "body": "Users see a 500 error.",
            "comments": ["Confirmed in prod.", "Started after last deploy."],
            "issuetype": "Bug", "labels": [],
        }
        text = format_ticket_context(ctx)
        self.assertIn("CONS-123", text)
        self.assertIn("Login fails on retry", text)
        self.assertIn("Users see a 500 error.", text)
        self.assertIn("Confirmed in prod.", text)
        self.assertIn("Started after last deploy.", text)

    def test_handles_no_comments(self):
        ctx = {
            "source": "github", "id": "11", "title": "t", "body": "b",
            "comments": [], "issuetype": "", "labels": [],
        }
        text = format_ticket_context(ctx)
        self.assertIn("11", text)

    def test_truncates_oversized_comment(self):
        ctx = {
            "source": "jira", "id": "CONS-123", "title": "t", "body": "b",
            "comments": ["x" * 5000], "issuetype": "", "labels": [],
        }
        text = format_ticket_context(ctx)
        self.assertLess(len(text), 1000)


if __name__ == "__main__":
    unittest.main()

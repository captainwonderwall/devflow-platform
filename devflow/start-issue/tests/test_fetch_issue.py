import sys
import os
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))        # start-issue/

from devflow_sdk.domain.issue import fetch


_JIRA_ISSUE = {
    "source": "jira", "id": "VDP-46625",
    "title": "Start issue script", "body": "", "comments": [],
    "issuetype": "Story", "labels": [],
}

_GH_ISSUE = {
    "source": "github", "id": "42",
    "title": "Add export button", "body": "", "comments": [],
    "issuetype": "", "labels": ["enhancement"],
}


class TestFetch(unittest.TestCase):
    @patch("devflow_sdk.domain.issue.ticket_info.fetch_jira_ticket", return_value=_JIRA_ISSUE)
    def test_jira_key_delegates_to_fetch_jira(self, mock_jira):
        result = fetch("VDP-46625")
        mock_jira.assert_called_once_with("VDP-46625")
        self.assertEqual(result["source"], "jira")

    @patch("devflow_sdk.domain.issue.ticket_info.fetch_github_issue", return_value=_GH_ISSUE)
    def test_numeric_string_delegates_to_fetch_github(self, mock_gh):
        result = fetch("42")
        mock_gh.assert_called_once_with(42)
        self.assertEqual(result["source"], "github")

    def test_invalid_input_exits(self):
        with self.assertRaises(SystemExit):
            fetch("not-a-valid-key")

    def test_lowercase_jira_key_treated_as_invalid(self):
        with self.assertRaises(SystemExit):
            fetch("vdp-123")

    @patch("devflow_sdk.domain.issue.ticket_info.fetch_jira_ticket", return_value=_JIRA_ISSUE)
    def test_multi_project_jira_key(self, mock_jira):
        fetch("CONS-123")
        mock_jira.assert_called_once_with("CONS-123")


if __name__ == "__main__":
    unittest.main()

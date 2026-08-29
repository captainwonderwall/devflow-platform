import json
import pytest
from unittest.mock import patch, MagicMock

from devflow_sdk.domain.issue.ticket_info import fetch, fetch_github_issue

_JIRA_ISSUE = {
    "source": "jira", "id": "VDP-46625",
    "title": "Some issue", "body": "", "comments": [],
    "issuetype": "Story", "labels": [],
}
_GH_ISSUE = {
    "source": "github", "id": "42",
    "title": "Add button", "body": "", "comments": [],
    "issuetype": "", "labels": [],
}


def test_jira_key_dispatches_to_fetch_jira():
    with patch("devflow_sdk.domain.issue.ticket_info.fetch_jira_ticket", return_value=_JIRA_ISSUE) as mock:
        result = fetch("VDP-46625")
    mock.assert_called_once_with("VDP-46625")
    assert result["source"] == "jira"


def test_numeric_string_dispatches_to_fetch_github():
    with patch("devflow_sdk.domain.issue.ticket_info.fetch_github_issue", return_value=_GH_ISSUE) as mock:
        result = fetch("42")
    mock.assert_called_once_with(42)
    assert result["source"] == "github"


def test_invalid_input_exits():
    with pytest.raises(SystemExit):
        fetch("not-valid")


def test_lowercase_jira_key_treated_as_invalid():
    with pytest.raises(SystemExit):
        fetch("vdp-123")


def test_multi_project_jira_key_dispatches_correctly():
    with patch("devflow_sdk.domain.issue.ticket_info.fetch_jira_ticket", return_value=_JIRA_ISSUE) as mock:
        fetch("CONS-123")
    mock.assert_called_once_with("CONS-123")


def _gh_subprocess_result(data: dict):
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = json.dumps(data)
    return proc


def test_github_issue_includes_url():
    proc = _gh_subprocess_result({
        "title": "Add button",
        "body": "Some body",
        "comments": [],
        "labels": [],
        "url": "https://github.com/owner/repo/issues/42",
    })
    with patch("devflow_sdk.domain.issue.ticket_info.check_gh"), \
         patch("subprocess.run", return_value=proc):
        result = fetch_github_issue(42)
    assert result["url"] == "https://github.com/owner/repo/issues/42"

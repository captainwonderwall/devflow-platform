#!/usr/bin/env python3
import json
import re
import shutil
import subprocess
import sys

JIRA_KEY_RE = re.compile(r'^[A-Z]+-[0-9]+$')

_ADF_BLOCK_TYPES = {
    "doc", "paragraph", "heading", "bulletList", "orderedList",
    "listItem", "blockquote", "codeBlock", "panel", "table",
    "tableRow", "tableCell",
}


def _adf_to_text(node):
    """Recursively extract plain text from an Atlassian Document Format node."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = [_adf_to_text(child) for child in node.get("content", [])]
    sep = "\n" if node.get("type") in _ADF_BLOCK_TYPES else ""
    return sep.join(p for p in parts if p)


def _str_field(value):
    """Return value as a string, converting ADF dicts to plain text."""
    if isinstance(value, dict):
        return _adf_to_text(value)
    return value or ""


ACLI_INSTALL_ERROR = (
    "ERROR: acli (Atlassian CLI) not found. Install it with:\n"
    "  brew tap atlassian/homebrew-acli && brew install acli\n"
    "Then authenticate with:\n"
    "  acli jira auth login --web"
)

ACLI_AUTH_ERROR = (
    "ERROR: acli is not authenticated. Run:\n"
    "  acli jira auth login --web\n"
    "(or acli jira auth login --site <site> --email <email> --token <token>)"
)

GH_INSTALL_ERROR = "ERROR: gh CLI not found. Install from https://cli.github.com"
GH_AUTH_ERROR = "ERROR: gh is not authenticated. Run: gh auth login"


def is_jira_key(value):
    return bool(value and JIRA_KEY_RE.match(value))


def check_acli():
    if shutil.which("acli") is None:
        print(ACLI_INSTALL_ERROR, file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(
        ["acli", "jira", "auth", "status"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(ACLI_AUTH_ERROR, file=sys.stderr)
        sys.exit(1)


def check_gh():
    if shutil.which("gh") is None:
        print(GH_INSTALL_ERROR, file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if result.returncode != 0:
        print(GH_AUTH_ERROR, file=sys.stderr)
        sys.exit(1)


def fetch_jira_ticket(key):
    check_acli()
    result = subprocess.run(
        ["acli", "jira", "workitem", "view", key,
         "--fields", "summary,description,comment,issuetype", "--json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: Failed to fetch JIRA ticket {key}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"ERROR: acli returned invalid JSON for {key}:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)

    fields = data.get("fields", data)
    title = _str_field(fields.get("summary", ""))
    body = _str_field(fields.get("description", ""))
    issuetype = (fields.get("issuetype") or {}).get("name", "") or ""
    comment_field = fields.get("comment", {})
    if isinstance(comment_field, dict):
        raw_comments = comment_field.get("comments", [])
    elif isinstance(comment_field, list):
        raw_comments = comment_field
    else:
        raw_comments = []
    comments = [_str_field(c.get("body", "")) for c in raw_comments if isinstance(c, dict)]

    return {
        "source": "jira",
        "id": key,
        "title": title,
        "body": body,
        "comments": comments,
        "issuetype": issuetype,
        "labels": [],
    }


def fetch_github_issue(number):
    check_gh()
    result = subprocess.run(
        ["gh", "issue", "view", str(number), "--json", "title,body,comments,labels,url"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: Failed to fetch GitHub issue #{number}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"ERROR: gh returned invalid JSON for issue #{number}:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)

    title = data.get("title", "") or ""
    body = data.get("body", "") or ""
    comments = [c.get("body", "") for c in data.get("comments", []) if isinstance(c, dict)]
    labels = [l.get("name", "") for l in data.get("labels", []) if isinstance(l, dict)]
    url = data.get("url", "") or ""

    return {
        "source": "github",
        "id": str(number),
        "title": title,
        "body": body,
        "comments": comments,
        "issuetype": "",
        "labels": labels,
        "url": url,
    }


def get_ticket_context(jira, github_issue):
    if is_jira_key(jira):
        return fetch_jira_ticket(jira)
    if github_issue:
        return fetch_github_issue(github_issue)
    return None


MAX_COMMENT_LENGTH = 500
MAX_COMMENTS = 10


def format_ticket_context(ticket_context):
    if not ticket_context:
        return ""
    truncated_comments = [
        c[:MAX_COMMENT_LENGTH] for c in ticket_context["comments"][:MAX_COMMENTS]
    ]
    comments_text = "\n".join(f"- {c}" for c in truncated_comments) or "(none)"
    return (
        f"\nLinked {ticket_context['source']} ticket {ticket_context['id']}:\n"
        f"Title: {ticket_context['title']}\n"
        f"Description: {ticket_context['body'][:3000]}\n"
        f"Comments:\n{comments_text}\n"
    )


def fetch(issue_arg: str) -> dict:
    if JIRA_KEY_RE.match(issue_arg):
        return fetch_jira_ticket(issue_arg)
    try:
        return fetch_github_issue(int(issue_arg))
    except ValueError:
        print(
            f"ERROR: '{issue_arg}' is not a valid JIRA key (e.g. VDP-123) "
            "or GitHub issue number (e.g. 42).",
            file=sys.stderr,
        )
        sys.exit(1)

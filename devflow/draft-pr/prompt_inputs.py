#!/usr/bin/env python3
import json
import sys
import os as _os
import glob as _glob_pi

_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
_REPO_ROOT = _os.path.dirname(_SCRIPT_DIR)
_VENDOR_DIR = _os.path.join(_REPO_ROOT, "vendor")
for _whl in sorted(_glob_pi.glob(_os.path.join(_VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)
from devflow_sdk.core.ui import error


def build_questions(data):
    questions = []

    if not data.get("jira_ticket") and not data.get("github_issue"):
        questions.append({
            "id": "jira_ticket",
            "text": "What is the Jira ticket number? (e.g. CONS-123)",
        })

    if not data.get("issue_type"):
        questions.append({
            "id": "issue_type",
            "text": "What type of change is this? Pick one: Issue / Feature / Enhancement / Other",
        })

    return questions


def load_stdin_json(stream):
    try:
        return json.load(stream)
    except json.JSONDecodeError as exc:
        error(f"Invalid JSON on stdin: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    data = load_stdin_json(sys.stdin)
    questions = build_questions(data)
    print(json.dumps({"questions": questions}, indent=2))

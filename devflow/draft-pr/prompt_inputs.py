#!/usr/bin/env python3
import json
import sys


def build_questions(data):
    questions = []

    if not data.get("jira_ticket"):
        questions.append({
            "id": "jira_ticket",
            "text": "What is the Jira ticket number? (e.g. CONS-123)",
        })

    if not data.get("issue_type"):
        questions.append({
            "id": "issue_type",
            "text": "What type of change is this? Pick one: Issue / Feature / Enhancement / Other",
        })

    questions.append({
        "id": "customer_visible",
        "text": "Is this a customer visible change? (Yes/No)",
    })

    return questions


def load_stdin_json(stream):
    try:
        return json.load(stream)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON on stdin: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    data = load_stdin_json(sys.stdin)
    questions = build_questions(data)
    print(json.dumps({"questions": questions}, indent=2))

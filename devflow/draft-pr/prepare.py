#!/usr/bin/env python3
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def run_script(script_name, stdin_data=None):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    kwargs = {"capture_output": True, "text": True}
    if stdin_data is not None:
        kwargs["input"] = json.dumps(stdin_data)
    result = subprocess.run([sys.executable, script_path], **kwargs)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return json.loads(result.stdout)


def validate_state(data):
    branch = data.get("branch")
    if not branch:
        print("ERROR: Not a git repo. Run this from inside your project.", file=sys.stderr)
        sys.exit(1)
    raw_base = data.get("base")
    base = raw_base or "main"
    # Preserve legacy backward-compatibility: if base detection is missing
    # (e.g. older callers omitting "base"), still block master in addition
    # to the "main" fallback so this doesn't regress the previous behavior.
    is_blocked = branch == base or (not raw_base and branch in {"main", "master"})
    if is_blocked:
        print(f"ERROR: You're on {branch}. Switch to a feature branch first.", file=sys.stderr)
        sys.exit(1)
    if not data.get("git_log"):
        print(f"ERROR: No commits found ahead of {base}. Nothing to PR.", file=sys.stderr)
        sys.exit(1)


def format_output(data, questions):
    lines = ["DATA:", json.dumps(data), "", "QUESTIONS:"]
    for i, q in enumerate(questions["questions"], 1):
        lines.append(f"{i}. {q['text']}")
    return "\n".join(lines)


if __name__ == "__main__":
    data = run_script("gather_pr_data.py")
    validate_state(data)
    questions = run_script("prompt_inputs.py", stdin_data=data)
    print(format_output(data, questions))

#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import glob as _glob_prep

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_VENDOR_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "vendor")
for _whl in sorted(_glob_prep.glob(os.path.join(_VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)
from devflow_sdk.core.ui import error

SCRIPTS_DIR = _SCRIPT_DIR


def run_script(script_name, stdin_data=None):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    kwargs = {"capture_output": True, "text": True}
    if stdin_data is not None:
        kwargs["input"] = json.dumps(stdin_data)
    result = subprocess.run([sys.executable, script_path], **kwargs)
    if result.returncode != 0:
        error(result.stderr.rstrip())
        sys.exit(result.returncode)
    return json.loads(result.stdout)


def validate_state(data):
    branch = data.get("branch")
    if not branch:
        error("Not a git repo. Run this from inside your project.")
        sys.exit(1)
    raw_base = data.get("base")
    base = raw_base or "main"
    # Preserve legacy backward-compatibility: if base detection is missing
    # (e.g. older callers omitting "base"), still block master in addition
    # to the "main" fallback so this doesn't regress the previous behavior.
    is_blocked = branch == base or (not raw_base and branch in {"main", "master"})
    if is_blocked:
        error(f"You're on {branch}. Switch to a feature branch first.")
        sys.exit(1)
    if not data.get("git_log"):
        error(f"No commits found ahead of {base}. Nothing to PR.")
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

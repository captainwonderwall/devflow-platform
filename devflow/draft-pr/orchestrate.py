#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(SCRIPTS_DIR, ".tmp")
SCRIPT_PATH = os.path.join(TMP_DIR, "create-pr.sh")


def check_existing_pr(branch):
    """Check if a PR exists for the given branch. Returns URL or None."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--json", "url"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        prs = json.loads(result.stdout)
        return prs[0]["url"] if prs else None
    except (json.JSONDecodeError, KeyError, IndexError, FileNotFoundError, OSError):
        return None


def run_create_script(script_path=None):
    """Run the create-pr shell script. Returns (url, error) tuple."""
    path = script_path or SCRIPT_PATH
    result = subprocess.run(["bash", path], stdout=subprocess.PIPE, text=True)
    if result.returncode != 0:
        return None, None
    output = result.stdout.strip()
    match = re.search(r"https://\S+", output)
    if match:
        return match.group(0), None
    return None, output or None

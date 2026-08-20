#!/usr/bin/env python3
import json
import re
import subprocess
import sys

FIX_PREFIXES = {"fix", "bugfix", "hotfix"}

PREFIX_TO_TYPE = {
    "fix": "Issue",
    "bugfix": "Issue",
    "hotfix": "Issue",
    "feature": "Feature",
    "feat": "Feature",
    "enhancement": "Enhancement",
    "enhance": "Enhancement",
    "chore": "Other",
    "refactor": "Other",
    "docs": "Other",
    "test": "Other",
}


def run_git(args):
    result = subprocess.run(["git"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def extract_prefix(branch):
    match = re.match(r'^([a-z]+)/', branch or "")
    return match.group(1) if match else None


def extract_jira_ticket(branch):
    match = re.search(r'[A-Z]+-[0-9]+', branch or "")
    return match.group(0) if match else None


def is_fix(prefix):
    return prefix in FIX_PREFIXES if prefix else False


def get_behind_count(base):
    subprocess.run(
        ["git", "fetch", "origin", base],
        capture_output=True,
        text=True,
    )
    result = run_git(["rev-list", "--count", f"HEAD..origin/{base}"])
    if result is None:
        return 0
    try:
        return int(result)
    except ValueError:
        return 0


def get_base_branch():
    result = run_git(["rev-parse", "--abbrev-ref", "origin/HEAD"])
    if result and "/" in result and result != "origin/HEAD":
        return result.split("/", 1)[1]

    try:
        gh_result = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
            capture_output=True,
            text=True,
        )
        if gh_result.returncode == 0:
            branch = gh_result.stdout.strip()
            if branch:
                return branch
    except (FileNotFoundError, OSError):
        pass

    print("WARNING: Could not detect default branch from origin/HEAD or GitHub; assuming 'main'.", file=sys.stderr)
    return "main"


def collect():
    branch = run_git(["branch", "--show-current"])
    prefix = extract_prefix(branch)
    jira_ticket = extract_jira_ticket(branch)
    issue_type = PREFIX_TO_TYPE.get(prefix) if prefix else None
    base = get_base_branch()
    remote_base = f"origin/{base}"
    git_log = run_git(["log", f"{remote_base}..HEAD", "--oneline"]) or ""
    diff_stat = run_git(["diff", f"{remote_base}..HEAD", "--stat"]) or ""
    files_output = run_git(["diff", f"{remote_base}..HEAD", "--name-only"]) or ""
    changed_files = [f for f in files_output.splitlines() if f]

    return {
        "branch": branch,
        "base": base,
        "prefix": prefix,
        "jira_ticket": jira_ticket,
        "issue_type": issue_type,
        "is_fix": is_fix(prefix),
        "git_log": git_log,
        "diff_stat": diff_stat,
        "changed_files": changed_files,
        "behind_count": get_behind_count(base),
    }


def validate_data(data):
    if not data.get("branch"):
        print("ERROR: Not a git repo. Run this from inside your project.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    data = collect()
    validate_data(data)
    print(json.dumps(data, indent=2))

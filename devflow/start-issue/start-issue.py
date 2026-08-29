#!/usr/bin/env python3
import argparse
import atexit
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)   # Homebrew: shared/ is sibling of start-issue.py
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)    # Dev: shared/ is at repo root

from devflow_sdk.domain.issue import fetch, write_issue_context
from devflow_sdk.core.branch_name import make_branch, infer_type, VALID_TYPES
from devflow_sdk.core.shell_function_check import check_shell_function
from devflow_sdk.worktree_state import add_worktree
from devflow_sdk.domain.workspace import check_manager, create as create_workspace
from devflow_sdk.core.git.worktree import get_repo_root
from devflow_sdk.core.git.shell_state import _persist_start_branch_for_shell
from repo_init import detect_and_write_config
from ide_config import copy_ide_config, prompt_and_open_ide, prompt_and_open_ai_agent
from devflow_sdk.core.summary import summary
from devflow_sdk.core.ai import run_ai_prompt

_INFER_TYPE_PROMPT = """\
You are classifying a {source} issue into a git branch type.
Valid types: feat, fix, hotfix, chore, docs.

Precedence: hotfix > fix > docs > chore > feat.

Issue title: {title}
Issue body: {body}

Output ONLY valid JSON in this exact format with no other text:
{{"type": "feat|fix|hotfix|chore|docs"}}
"""


def _needs_ai_inference(issue):
    if issue["source"] == "jira":
        return not issue.get("issuetype")
    return not issue.get("labels")  # github


def _ai_infer_type(issue):
    prompt = _INFER_TYPE_PROMPT.format(
        source=issue["source"],
        title=issue["title"],
        body=(issue.get("body") or "")[:2000],
    )
    result = run_ai_prompt(prompt, tier="fast", result_type="json", stateless=True)
    if not result.ok:
        print(f"WARNING: AI type inference failed — defaulting to 'feat'.\n{result.error}", file=sys.stderr)
        return "feat"
    inferred = result.result.get("type", "feat")
    if inferred not in VALID_TYPES:
        print(f"WARNING: AI returned unknown type '{inferred}' — defaulting to 'feat'.", file=sys.stderr)
        return "feat"
    return inferred


def main():
    parser = argparse.ArgumentParser(
        description="Create a branch and worktree from a JIRA or GitHub issue."
    )
    parser.add_argument(
        "issue",
        help="JIRA issue key (e.g. VDP-46625) or GitHub issue number (e.g. 42)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--feat", action="store_true", help="Force 'feat/' branch type")
    group.add_argument("--fix", action="store_true", help="Force 'fix/' branch type")
    group.add_argument("--hotfix", action="store_true", help="Force 'hotfix/' branch type")
    group.add_argument("--chore", action="store_true", help="Force 'chore/' branch type")
    group.add_argument("--docs", action="store_true", help="Force 'docs/' branch type")
    args = parser.parse_args()

    summary.start_rate_fetch()
    atexit.register(summary.print_summary)

    check_manager()
    check_shell_function(
        "# >>> start-issue shell integration >>>",
        f"ERROR: start-issue shell function is not installed or is out of date.\n"
        f"Re-run the installer: {os.path.join(SCRIPT_DIR, 'install.sh')}\n"
        "Then restart your shell or run: source {rc_path}",
        required_content="~/.start-issue-branch",
    )

    override = None
    for flag_name in ("feat", "fix", "hotfix", "chore", "docs"):
        if getattr(args, flag_name):
            override = flag_name
            break

    issue = fetch(args.issue)
    if override is None and _needs_ai_inference(issue):
        override = _ai_infer_type(issue)
    branch = make_branch(issue, override=override, worktree=True)
    print(f"Branch: {branch}")

    repo_root = get_repo_root()
    detect_and_write_config(repo_root)
    worktree_path = create_workspace(branch)
    if worktree_path:
        issue["branch"] = branch
        issue["branch_type"] = override if override is not None else infer_type(issue)
        issue["started_at"] = datetime.now(timezone.utc).isoformat()
        write_issue_context(worktree_path, issue)
        add_worktree(worktree_path, issue['id'], issue['source'])
        copy_ide_config(repo_root, worktree_path)
        prompt_and_open_ide(worktree_path)
        prompt_and_open_ai_agent(worktree_path)

    _persist_start_branch_for_shell(branch)

    summary.add("Issue", f"{issue['source'].upper()} {issue['id']}: {issue['title']}")
    summary.add("Branch", branch)
    if worktree_path:
        summary.add("Worktree", worktree_path)
        summary.add("Issue JSON", os.path.join(worktree_path, ".issue.json"))


if __name__ == "__main__":
    main()

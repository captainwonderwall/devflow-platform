#!/usr/bin/env python3
import argparse
import atexit
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)

import git_ops
from devflow_sdk.ai import run_ai_prompt
from devflow_sdk.summary import summary
from devflow_sdk.prompts import select

DIRTY_ABORT = "Abort"
DIRTY_STASH = "Stash changes, squash, then restore them"
PUSH_YES = "Yes, force-push"
PUSH_NO = "No, keep local only"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Squash all commits on the current branch into one AI-drafted commit"
    )
    return parser.parse_args()


def build_prompt(log_text, diff_stat_text):
    return f"""You are a git commit message assistant. Based on the commits below, output ONLY a single-line Conventional Commits style commit message (e.g. "feat: add export button") — no preamble, no quotes, no markdown fences, no body, one line only. Keep the message high-level and simple; avoid overly specific or verbose subjects.

Commit log (subjects and bodies, newest first):
{log_text}

Diff stat:
{diff_stat_text}"""


def extract_commit_message(ai_text):
    """Reduce raw AI text to the first non-empty line, or '' if the AI
    produced nothing usable."""
    for line in (ai_text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def resolve_dirty_choice(choice):
    """Map the raw questionary.select() return value to 'abort' or 'stash'.
    Ctrl+C returns None from questionary, which we treat as 'abort'."""
    if choice == DIRTY_STASH:
        return "stash"
    return "abort"


def resolve_push_choice(choice):
    """Map the raw questionary.select() return value to a push decision.
    Ctrl+C returns None from questionary, which we treat as 'no'."""
    return choice == PUSH_YES


def prompt_dirty_tree_choice():
    return select(
        "Working tree has uncommitted changes. What do you want to do?",
        [DIRTY_ABORT, DIRTY_STASH],
    )


def prompt_push_choice(branch):
    return select(
        f"Force-push the squashed commit to origin/{branch}?",
        [PUSH_YES, PUSH_NO],
    )


def main():
    parse_args()

    branch = git_ops.current_branch()
    if not branch:
        print("ERROR: Not a git repo. Run this from inside your project.", file=sys.stderr)
        sys.exit(1)

    base = git_ops.get_base_branch()
    count = git_ops.commits_ahead(base)
    if count <= 1:
        print(f"Nothing to squash — {count} commit(s) ahead of {base}.")
        sys.exit(0)

    stashed = False
    if git_ops.is_dirty():
        choice = resolve_dirty_choice(prompt_dirty_tree_choice())
        if choice == "abort":
            print("Aborted: commit or stash your changes, then rerun.", file=sys.stderr)
            sys.exit(1)
        if not git_ops.stash_push():
            print("ERROR: git stash push failed.", file=sys.stderr)
            sys.exit(1)
        stashed = True

    def restore_stash():
        if stashed:
            if not git_ops.stash_pop():
                print(
                    "WARNING: git stash pop failed; your changes are still stashed. "
                    "Recover with: git stash pop",
                    file=sys.stderr,
                )

    atexit.register(restore_stash)

    summary.start_rate_fetch()
    atexit.register(summary.print_summary)

    log_text = git_ops.log_for_prompt(base)
    diff_stat_text = git_ops.diff_stat(base)

    print("Drafting commit message with AI...")
    ai_result = run_ai_prompt(
        build_prompt(log_text, diff_stat_text), tier="fast", result_type="text"
    )
    if not ai_result.ok:
        print(f"ERROR: AI CLI failed:\n{ai_result.error}", file=sys.stderr)
        sys.exit(1)

    message = extract_commit_message(ai_result.result)
    if not message:
        print("ERROR: AI returned an empty commit message.", file=sys.stderr)
        sys.exit(1)

    if not git_ops.soft_reset_and_commit(base, message):
        print("ERROR: git reset/commit failed while squashing.", file=sys.stderr)
        sys.exit(1)

    summary.add("Branch", branch)
    summary.add("Base", base)
    summary.add("Commits squashed", str(count))
    summary.add("Message", message)

    push = resolve_push_choice(prompt_push_choice(branch))
    if push:
        ok, output = git_ops.force_push_with_lease(branch)
        if ok:
            summary.add("Push", f"origin/{branch} (force-with-lease)")
        else:
            summary.add("Push", "failed")
            print(f"ERROR: force-push failed:\n{output}", file=sys.stderr)
            print(
                "The squash is local-only. Retry manually: git push --force-with-lease",
                file=sys.stderr,
            )
            summary.print_summary()
            sys.exit(1)
    else:
        summary.add("Push", "skipped (local squash kept)")

    summary.print_summary()


if __name__ == "__main__":
    main()

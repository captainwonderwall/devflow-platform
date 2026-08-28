#!/usr/bin/env python3
import argparse
import atexit
import os
import subprocess
import sys
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)

from fetch_comments import collect
from analyze_comments import analyze_comments
from display import display_comments, prompt_selection
from apply_changes import apply_changes
from post_replies import generate_reply_texts, confirm_and_post_replies
from devflow_sdk.summary import summary
from devflow_sdk.ticket_info import check_gh
from devflow_sdk.prompts import confirm
from devflow_sdk.ai import configured_provider_display_name


def parse_args():
    parser = argparse.ArgumentParser(
        description="Address unresolved PR review comments with AI assistance"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
         help="Save the configured AI provider's raw output (command, exit code, "
             "stdout, stderr) to a temp file for each AI call, for inspection if "
             "something goes wrong.",
    )
    return parser.parse_args()


def get_current_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    )
    if result.returncode != 0:
        # Fail fast rather than returning a sentinel like "unknown" that
        # could later be mistaken for a real commit SHA.
        raise RuntimeError(
            f"git rev-parse HEAD failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _content_hash(path: str) -> Optional[str]:
    """Git blob hash of a file's on-disk content, or None if it doesn't
    exist (e.g. deleted). Lets us detect further edits to a file that was
    already dirty before Claude ran, since its status code alone (e.g. " M")
    wouldn't change."""
    if not os.path.isfile(path):
        return None
    result = subprocess.run(
        ["git", "hash-object", "--", path], capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_working_tree_status() -> dict:
    """Return {path: (status_code, content_hash)} for the current working
    tree, including untracked files. Used to snapshot state before/after
    apply_changes() so Claude's edits can be told apart from pre-existing
    unrelated changes, including further edits to an already-dirty file."""
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    )
    status = {}
    for line in result.stdout.splitlines():
        if not line:
            continue
        code, path = line[:2], line[3:]
        # Renames are reported as "old -> new"; key on the new path.
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        status[path] = (code, _content_hash(path))
    return status


def files_touched_by_claude(before: dict, after: dict) -> list:
    """Files whose (status_code, content_hash) changed, or that newly
    appeared, between the two snapshots. Pre-existing unrelated dirty files
    that Claude never touched keep the same status and hash and are
    excluded. Because the content hash is compared (not just the status
    code), further edits Claude makes to an already-dirty file are still
    detected even though its status code stays the same.
    """
    return sorted(
        path for path, snapshot in after.items()
        if before.get(path) != snapshot
    )


def head_advanced_via_commit() -> bool:
    """Check that the most recent HEAD move (if any) was a real `git commit`,
    not e.g. a reset/checkout, per reflog."""
    result = subprocess.run(
        ["git", "reflog", "-1", "--format=%gs"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False
    return result.stdout.strip().startswith("commit")


def commit_changes(authors: list, paths: Optional[list] = None) -> Optional[str]:
    """Commit changes. If `paths` is given, only those files are staged
    (so unrelated pre-existing dirty files are never swept into the
    commit); if it's an empty list, no-op immediately."""
    if paths is not None and not paths:
        print("No file changes to commit.")
        return None

    author_list = ", ".join(f"@{a}" for a in authors)
    add_cmd = ["git", "add", "-A"] if paths is None else ["git", "add", "--"] + list(paths)
    subprocess.run(add_cmd, check=True)

    # Check if there are staged changes
    # returncode: 0 = no diff, 1 = diff present, >1 = error
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True
    )
    if result.returncode == 1:
        # There are staged changes, proceed with commit
        subprocess.run(
            ["git", "commit", "-m", f"address: review comments from {author_list}"],
            check=True,
        )
        return get_current_sha()
    elif result.returncode > 1:
        raise subprocess.CalledProcessError(result.returncode,
                                             ["git", "diff", "--cached", "--quiet"])
    else:
        # No staged changes
        print("No file changes to commit.")
        return None


def prompt_and_push() -> bool:
    result = subprocess.run(
        ["git", "log", "--oneline", "-1"], capture_output=True, text=True
    )
    print(f"\nCommit: {result.stdout.strip()}")
    stat = subprocess.run(
        ["git", "diff", "HEAD~1", "--stat"], capture_output=True, text=True
    )
    print(stat.stdout)
    if confirm("Push these changes?"):
        subprocess.run(["git", "push"], check=True)
        print("Pushed.")
        return True
    else:
        print("Push skipped. Run 'git push' when ready.")
        return False


def main():
    args = parse_args()
    check_gh()
    summary.start_rate_fetch()
    atexit.register(summary.print_summary)

    data = collect()
    if not data["comments"]:
        print("No unresolved comments found.")
        summary.print_summary()
        return

    comments, session_id = analyze_comments(
        data["pr_title"], data["pr_branch"], data["comments"],
        debug=args.debug
    )

    display_comments(
        comments, data["pr_title"], data["pr_branch"], data["pr_base"]
    )

    selected = prompt_selection(comments)
    if selected is None:
        print("Quitting.")
        summary.print_summary()
        return

    chosen = [comments[i] for i in selected]

    print(
        f"\nAddressing comments with {configured_provider_display_name()}...\n"
    )
    status_before = get_working_tree_status()
    sha_before = get_current_sha()
    success = apply_changes(data["pr_title"], data["pr_description"], chosen,
                            session_id=session_id, debug=args.debug)
    if not success:
        print(
            f"ERROR: {configured_provider_display_name()} session failed. "
            "No changes committed.",
              file=sys.stderr)
        sys.exit(1)

    sha_after = get_current_sha()
    status_after = get_working_tree_status()
    claude_files = files_touched_by_claude(status_before, status_after)
    authors = list(dict.fromkeys(c.author for c in chosen))

    if sha_before != sha_after:
        if not head_advanced_via_commit():
            print(
                "WARNING: HEAD moved but the last reflog entry doesn't look "
                "like a commit (possible reset/checkout). Treating any "
                "remaining changes as uncommitted.",
                file=sys.stderr,
            )
        sha = sha_after
    else:
        sha = None

    # Whether or not Claude committed, still commit anything Claude touched
    # but left uncommitted — scoped to Claude's files only, so unrelated
    # pre-existing dirty files in the repo are never swept in.
    leftover_sha = commit_changes(authors, paths=claude_files)
    if leftover_sha is not None:
        sha = leftover_sha

    if sha is None:
        print("\nNo commit was made. Proceeding with reply.")
        commit_sha = "no commit"
    else:
        commit_sha = sha

    summary.add("Comments", f"{len(chosen)} addressed")
    if sha is not None:
        summary.add("Commit", sha[:7])

    chosen = generate_reply_texts(chosen, commit_sha, debug=args.debug)
    confirm_and_post_replies(
        chosen, data["owner"], data["repo"], data["pr_number"]
    )

    if sha is not None:
        pushed = prompt_and_push()
        summary.add("Pushed", "yes" if pushed else "no")

    summary.print_summary()


if __name__ == "__main__":
    main()

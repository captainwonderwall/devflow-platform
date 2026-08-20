#!/usr/bin/env python3
import os
import shlex
import subprocess
import sys
import tempfile
from typing import List
from fetch_comments import Comment

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)
from devflow_sdk.ai import run_ai_prompt
from devflow_sdk.prompts import select


def _edit_in_editor(text: str) -> str:
    editor = os.environ.get("EDITOR", "vi")
    tmp_dir = os.environ.get("TMPDIR")
    if tmp_dir and not os.path.isdir(tmp_dir):
        tmp_dir = None
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, dir=tmp_dir
    )
    try:
        tmp.write(text)
        tmp.flush()
        tmp.close()
        try:
            proc = subprocess.run([*shlex.split(editor), tmp.name])
        except (FileNotFoundError, OSError) as e:
            print(f"WARNING: failed to launch editor '{editor}': {e}",
                  file=sys.stderr)
            return text
        if proc.returncode != 0:
            print(f"WARNING: editor '{editor}' exited with code "
                  f"{proc.returncode}; keeping original text",
                  file=sys.stderr)
            return text
        with open(tmp.name) as f:
            edited = f.read().strip()
        return edited if edited else text
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


def generate_reply_texts(comments: List[Comment],
                         commit_sha: str,
                         debug: bool = False) -> List[Comment]:
    if not comments:
        return comments

    lines = [
        "Generate brief, friendly reply texts for these PR review comments.",
        "Each comment below is tagged VALID or INVALID (an earlier AI "
        "assessment of whether it needed a code change):",
        f"- VALID comments were addressed in commit {commit_sha[:8]}. Write "
        "a brief reply saying so.",
        "- INVALID comments were NOT changed — no code change was needed. "
        "Write a brief, polite reply explaining why, based on the given "
        "reason. Do NOT say the issue was fixed, addressed, or resolved by "
        "a change; do not agree that a change was required.",
        "Return ONLY a valid JSON array. Each element: "
        "id (string), reply (string, 1-2 sentences max).",
        "",
        "Comments:",
    ]
    for c in comments:
        verdict = c.verdict if c.verdict else "VALID"
        lines.append(f"- id: {c.id}, author: @{c.author}, verdict: {verdict}")
        lines.append(f"  body: {c.body[:200]}")
        if verdict == "INVALID" and c.reason:
            lines.append(f"  reason: {c.reason}")

    ai_result = run_ai_prompt(
        "\n".join(lines), tier="capable", result_type="json",
        debug=debug
    )
    if not ai_result.ok:
        print(f"ERROR: claude failed generating replies: {ai_result.error.strip()}",
              file=sys.stderr)
        sys.exit(1)
    replies = ai_result.result

    reply_map = {r["id"]: r["reply"] for r in replies}
    for c in comments:
        if c.id in reply_map:
            c.reply_text = reply_map[c.id]
    return comments


def _post_reply(c: Comment, owner: str, repo: str, pr_number: int) -> None:
    if c.kind == "review_thread":
        endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}/comments/{c.id}/replies"
    else:
        endpoint = f"/repos/{owner}/{repo}/issues/{pr_number}/comments"
    result = subprocess.run(
        ["gh", "api", endpoint, "-X", "POST", "-f", f"body={c.reply_text}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"WARNING: failed to post reply for comment {c.id}: "
              f"{result.stderr.strip()}", file=sys.stderr)


def _resolve_thread(thread_node_id: str) -> None:
    mutation = (
        "mutation($threadId:ID!){"
        "resolveReviewThread(input:{threadId:$threadId})"
        "{thread{isResolved}}}"
    )
    result = subprocess.run(
        ["gh", "api", "graphql",
         "-f", f"query={mutation}",
         "-f", f"threadId={thread_node_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"WARNING: failed to resolve thread {thread_node_id}: "
              f"{result.stderr.strip()}", file=sys.stderr)


def confirm_and_post_replies(comments: List[Comment], owner: str, repo: str,
                              pr_number: int) -> None:
    if not comments:
        return
    print("\nProposed replies:")
    for c in comments:
        if not c.reply_text:
            print(f"\n  @{c.author}: skipping - no reply text was generated "
                  f"for comment {c.id}", file=sys.stderr)
            continue
        body_preview = c.body[:80] + "..." if len(c.body) > 80 else c.body
        print(f"\n  @{c.author}: \"{body_preview}\"")
        while True:
            print(f"  Reply: {c.reply_text}")
            answer = select("Post this reply?", choices=["yes", "no", "edit"])
            if answer == "yes":
                _post_reply(c, owner, repo, pr_number)
                if c.is_bot and c.kind == "review_thread" and c.thread_node_id:
                    _resolve_thread(c.thread_node_id)
                break
            elif answer == "no" or answer is None:
                break
            elif answer == "edit":
                c.reply_text = _edit_in_editor(c.reply_text)

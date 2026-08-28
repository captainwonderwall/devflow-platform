#!/usr/bin/env python3
import os
import sys
from typing import List, Optional, Tuple
from fetch_comments import Comment

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)
from devflow_sdk.ai import configured_provider_display_name, run_ai_prompt

REUSE_TOKEN_LIMIT = 160_000


def build_analysis_prompt(pr_title: str, pr_branch: str,
                           comments: List[Comment]) -> str:
    lines = [
        f"PR: {pr_title} (branch: {pr_branch})",
        "",
        "Analyze these PR review comments. For each comment that references "
        "a file, read that file to understand the actual code before deciding "
        "whether it is a valid, actionable issue.",
        "Return ONLY a valid JSON array. Each element must have exactly: "
        "id (string), verdict (\"VALID\" or \"INVALID\"), reason (one sentence).",
        "",
        "Comments:",
    ]
    for c in comments:
        loc = f" at {c.file}:{c.line}" if c.file else ""
        bot_label = " [bot]" if c.is_bot else ""
        lines.append(f"- id: {c.id}, author: @{c.author}{bot_label}{loc}")
        lines.append(f"  body: {c.body[:300]}")
        if c.thread and len(c.thread) > 1:
            lines.append("  thread:")
            for entry in c.thread[1:]:
                bot_suffix = " [bot]" if entry["is_bot"] else ""
                lines.append(f"    @{entry['author']}{bot_suffix}: {entry['body'][:300]}")
    return "\n".join(lines)


def analyze_comments(pr_title: str, pr_branch: str,
                     comments: List[Comment],
                     debug: bool = False) -> Tuple[List[Comment], Optional[str]]:
    if not comments:
        return comments, None

    prompt = build_analysis_prompt(pr_title, pr_branch, comments)
    ai_result = run_ai_prompt(prompt, tier="capable",
                              result_type="json", debug=debug)
    if not ai_result.ok:
        print(
            f"ERROR: {configured_provider_display_name()} failed during analysis: "
            f"{ai_result.error.strip()}",
              file=sys.stderr)
        sys.exit(1)

    verdicts = ai_result.result
    verdict_map = {v["id"]: v for v in verdicts}
    for c in comments:
        if c.id in verdict_map:
            c.verdict = verdict_map[c.id]["verdict"]
            c.reason = verdict_map[c.id]["reason"]

    reusable_id = (ai_result.session_id
                   if ai_result.total_tokens < REUSE_TOKEN_LIMIT
                   else None)
    return comments, reusable_id

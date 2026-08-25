#!/usr/bin/env python3
import os
import sys
from typing import List, Optional, Tuple
from fetch_comments import Comment

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from devflow_sdk.prompts import Choice, checkbox


def display_comments(
    comments: List[Comment],
    pr_title: str,
    pr_branch: str,
    pr_base: str,
) -> None:
    print(f'\nPR: "{pr_title}" ({pr_branch} → {pr_base})')
    print(f"\nUnresolved comments ({len(comments)}):\n")
    for i, c in enumerate(comments, 1):
        bot_label = " (bot)" if c.is_bot else ""
        if c.kind == "review_thread":
            location = f"inline: {c.file}:{c.line}"
        else:
            location = "PR comment"
        body_preview = c.body[:120] + "..." if len(c.body) > 120 else c.body
        verdict_str = f"{c.verdict} — {c.reason}" if c.verdict else "—"
        print(f"[{i}] @{c.author}{bot_label} — {location}")
        print(f'    "{body_preview}"')
        print(f"    AI: {verdict_str}")
        print()


def resolve_selection(
    checked: List[str], count: int
) -> Tuple[Optional[List[int]], Optional[str]]:
    """Interpret the raw values returned by the checkbox prompt.

    Returns (indices, error):
      - error is not None: caller should print it and re-prompt.
      - error is None and indices is a list: the resolved 0-based indices
        of comments to address.
    """
    if "all" in checked:
        return list(range(count)), None
    return sorted(int(v) - 1 for v in checked), None


def _location_label(c: Comment) -> str:
    if c.kind == "review_thread":
        return f"inline: {c.file}:{c.line}"
    return "PR comment"


def prompt_selection(comments: List[Comment]) -> Optional[List[int]]:
    """Show an interactive checkbox menu and return the chosen 0-based
    indices, or None if the user quit (Ctrl+C or explicit "none")."""
    choices = []
    for i, c in enumerate(comments, 1):
        bot_label = " (bot)" if c.is_bot else ""
        choices.append(
            Choice(
                title=f"[{i}] @{c.author}{bot_label} — {_location_label(c)}",
                value=str(i),
            )
        )
    choices.append(Choice(title="all", value="all"))

    return checkbox(
        "Select comments to address",
        choices,
        resolve=lambda checked: resolve_selection(checked, len(comments)),
    )

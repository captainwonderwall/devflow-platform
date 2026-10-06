import os
import subprocess
import sys

from devflow_sdk.core.prompts import Choice, select

_IDE_LAUNCHERS = [
    (".idea",   "IntelliJ IDEA", "idea"),
    (".vscode", "VS Code",       "code"),
]

_SKIP = "__skip__"


def detect_ides(worktree_path):
    """Return (name, cmd) pairs for IDEs whose config folder exists in worktree_path."""
    return [
        (name, cmd)
        for folder, name, cmd in _IDE_LAUNCHERS
        if os.path.isdir(os.path.join(worktree_path, folder))
    ]


def prompt_and_open_ide(worktree_path):
    """Prompt the user to open the worktree in a detected IDE, then launch it."""
    ides = detect_ides(worktree_path)
    if not ides:
        return

    choices = [Choice(title=f"Open in {name}", value=cmd) for name, cmd in ides]
    choices.append(Choice(title="Skip", value=_SKIP))

    cmd = select("Open the worktree in an IDE?", choices, single=True)
    if cmd is None or cmd == _SKIP:
        return

    try:
        subprocess.run([cmd, "."], cwd=worktree_path)
    except FileNotFoundError:
        print(f"WARNING: Could not launch IDE — '{cmd}' not found on PATH.", file=sys.stderr)

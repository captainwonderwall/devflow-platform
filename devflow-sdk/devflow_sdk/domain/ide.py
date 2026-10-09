import os
import subprocess

from devflow_sdk.core.ai import launch_interactive_session
from devflow_sdk.core.prompts import Choice, select
from devflow_sdk.core.ui import error

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
        error(f"Could not launch IDE — '{cmd}' not found on PATH.")


_AI_AGENT_PROMPT = "Brainstorm a solution for the issue described in .issue.json"


def prompt_and_open_ai_agent(worktree_path):
    """Prompt the user to open an interactive AI agent session in the worktree."""
    choices = [
        Choice(title="Open AI agent session", value="open"),
        Choice(title="Skip", value=None),
    ]
    chosen = select("Start working with an AI agent?", choices, single=True)
    if chosen == "open":
        launch_interactive_session(_AI_AGENT_PROMPT, cwd=worktree_path)

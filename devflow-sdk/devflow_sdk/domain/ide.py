import json
import os
import subprocess
import urllib.request

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


_INTELLIJ_PORTS = range(63342, 63353)


def close_intellij_project(path: str) -> str:
    """
    Attempt to close an IntelliJ IDEA project window for `path`.
    Returns 'closed', 'not_running', or 'failed'.
    Tries the built-in REST API first, then AppleScript via System Events.
    """
    norm = os.path.realpath(path)
    project_name = os.path.basename(norm)

    pgrep = subprocess.run(
        ["pgrep", "-f", "IntelliJ IDEA"],
        capture_output=True,
    )
    if pgrep.returncode != 0:
        return "not_running"

    for port in _INTELLIJ_PORTS:
        try:
            req = urllib.request.Request(
                f"http://localhost:{port}/api/about?json=true",
                headers={"Origin": "http://localhost"},
            )
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            continue

        base = data.get("projectBasePath") or data.get("baseDir") or ""
        name = data.get("projectName") or ""
        path_match = base and os.path.realpath(base) == norm
        name_match = not base and name == project_name
        if not path_match and not name_match:
            continue

        try:
            close_req = urllib.request.Request(
                f"http://localhost:{port}/platform/actions/CloseProject",
                data=b"",
                method="POST",
                headers={"Origin": "http://localhost"},
            )
            urllib.request.urlopen(close_req, timeout=3)
            return "closed"
        except Exception:
            break

    return _applescript_close_intellij(project_name)


def _applescript_close_intellij(project_name: str) -> str:
    """Close an IntelliJ IDEA project window via AppleScript System Events."""
    safe_name = project_name.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''\
set _found to false
tell application "System Events"
    set _procs to every process whose name contains "IntelliJ IDEA"
    if (count of _procs) is 0 then return "not_running"
    repeat with _proc in _procs
        repeat with _win in windows of _proc
            if name of _win starts with "{safe_name}" then
                set frontmost of _proc to true
                tell _proc
                    perform action "AXRaise" of _win
                    click menu item "Close Project" of menu "File" of menu bar 1
                end tell
                set _found to true
            end if
        end repeat
    end repeat
end tell
if _found then
    return "closed"
else
    return "not_running"
end if\
'''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        return "failed"
    out = result.stdout.strip()
    if out in ("closed", "not_running"):
        return out
    return "failed"


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

import os
import re
import shutil
import subprocess
import sys

from devflow_sdk.prompts import select, Choice
from devflow_sdk.ai import launch_interactive_session

IDE_CONFIG_FOLDERS = (".idea", ".vscode")

_IDE_LAUNCHERS = [
    (".idea",   "IntelliJ IDEA", "idea"),
    (".vscode", "VS Code",       "code"),
]


def detect_ides(worktree_path):
    """Return a list of (name, cmd) for each IDE whose config folder exists in worktree_path."""
    return [
        (name, cmd)
        for folder, name, cmd in _IDE_LAUNCHERS
        if os.path.isdir(os.path.join(worktree_path, folder))
    ]


_SKIP = "__skip__"


def prompt_and_open_ide(worktree_path):
    """Prompt the user to open the worktree in an IDE whose config folder is present, then launch it."""
    ides = detect_ides(worktree_path)
    if not ides:
        return

    choices = [Choice(title=f"Open in {name}", value=cmd) for name, cmd in ides]
    choices.append(Choice(title="Skip", value=_SKIP))

    cmd = select("Open the worktree in an IDE?", choices)
    if cmd is None or cmd == _SKIP:
        return

    try:
        subprocess.run([cmd, "."], cwd=worktree_path)
    except FileNotFoundError:
        print(f"WARNING: Could not launch IDE — '{cmd}' not found on PATH.", file=sys.stderr)


_AI_AGENT_PROMPT = "Brainstorm a solution for the issue described in .issue.json"


def prompt_and_open_ai_agent(worktree_path):
    """Prompt the user to open an interactive AI agent session in the worktree."""
    choices = [
        Choice(title="Open AI agent session", value="open"),
        Choice(title="Skip", value=None),
    ]
    chosen = select("Start working with an AI agent?", choices)
    if chosen == "open":
        launch_interactive_session(_AI_AGENT_PROMPT, cwd=worktree_path)


def _copy_folder(src, dest):
    if not os.path.isdir(src):
        return False
    if os.path.exists(dest):
        print(
            f"NOTICE: {os.path.basename(dest)} already exists in the new "
            f"worktree — skipping copy."
        )
        return False
    try:
        shutil.copytree(src, dest)
    except Exception:
        # Don't leave a partially-copied dest behind — otherwise it will
        # look like an "already exists" dest on every subsequent run and
        # be skipped forever.
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return True


def _path_boundary_pattern(old_path):
    """Compile a regex matching old_path only when followed by a path
    boundary (separator, quote, angle bracket, whitespace, or end of
    string) so sibling paths that merely have old_path as a prefix (e.g.
    "<old_path>-legacy") are left untouched."""
    return re.compile(re.escape(old_path) + r'''(?=[/\\'"<>\s]|$)''')


def _rewrite_paths(dest, old_path, new_path):
    """Replace old_path with new_path in UTF-8 files under dest."""
    pattern = _path_boundary_pattern(old_path)
    for root, _dirs, files in os.walk(dest):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            new_content = pattern.sub(new_path, content)
            if new_content == content:
                continue
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except OSError:
                continue


def copy_ide_config(main_root, worktree_path):
    """Copy IDE config folders from main_root into worktree_path."""
    for folder in IDE_CONFIG_FOLDERS:
        src = os.path.join(main_root, folder)
        dest = os.path.join(worktree_path, folder)
        try:
            copied = _copy_folder(src, dest)
            if copied:
                _rewrite_paths(dest, main_root, worktree_path)
                print(f"Copied {folder} config (paths updated).")
        except Exception as e:
            print(f"WARNING: could not copy {folder} config: {e}", file=sys.stderr)

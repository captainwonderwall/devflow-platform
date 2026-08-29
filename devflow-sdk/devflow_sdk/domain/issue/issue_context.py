import json
import os
import subprocess

_FILENAME = ".issue.json"


def read_issue_context(worktree_path):
    current = os.path.realpath(worktree_path)
    while True:
        candidate = os.path.join(current, _FILENAME)
        try:
            with open(candidate) as f:
                data = json.load(f)
            if isinstance(data, dict) and "id" in data and "source" in data:
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        if os.path.exists(os.path.join(current, ".git")):
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def write_issue_context(worktree_path, issue):
    with open(os.path.join(worktree_path, _FILENAME), "w") as f:
        json.dump(issue, f, indent=2)
    _add_to_git_exclude(worktree_path)


def remove_issue_context(worktree_path):
    path = os.path.join(worktree_path, _FILENAME)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _add_to_git_exclude(worktree_path):
    result = subprocess.run(
        ["git", "-C", worktree_path, "rev-parse", "--git-common-dir"],
        capture_output=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return
    commondir = result.stdout.strip()
    if not os.path.isabs(commondir):
        commondir = os.path.join(worktree_path, commondir)
    exclude_path = os.path.join(commondir, "info", "exclude")
    os.makedirs(os.path.dirname(exclude_path), exist_ok=True)
    existing = ""
    if os.path.exists(exclude_path):
        with open(exclude_path) as f:
            existing = f.read()
    if _FILENAME not in existing.splitlines():
        with open(exclude_path, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(_FILENAME + "\n")

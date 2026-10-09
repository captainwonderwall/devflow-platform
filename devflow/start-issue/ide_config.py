import os
import re
import shutil

from devflow_sdk.core.ui import error, success
from devflow_sdk.domain.ide import detect_ides, prompt_and_open_ide, prompt_and_open_ai_agent

IDE_CONFIG_FOLDERS = (".idea", ".vscode")


def _copy_folder(src, dest):
    if not os.path.isdir(src):
        return False
    if os.path.exists(dest):
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
                success(f"Copied {folder} config (paths updated).")
        except Exception as e:
            error(f"could not copy {folder} config: {e}")

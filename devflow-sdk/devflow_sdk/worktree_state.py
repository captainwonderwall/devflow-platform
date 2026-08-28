from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_PATH = Path.home() / ".devflow" / "worktree_state.json"


@dataclass
class WorktreeEntry:
    path: str
    ticket_id: str
    source: str


def _load_raw(state_path: Path) -> list[dict]:
    if not state_path.exists():
        return []
    try:
        data = json.loads(state_path.read_text())
        if isinstance(data, dict):
            entries = data.get("worktrees", [])
            if isinstance(entries, list):
                return entries
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_raw(entries: list[dict], state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=state_path.parent, prefix=".worktree_state-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"worktrees": entries}, f, indent=2)
            f.write("\n")
        os.rename(tmp, state_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parse_entry(raw: dict) -> WorktreeEntry | None:
    try:
        return WorktreeEntry(
            path=raw["path"],
            ticket_id=raw["ticket_id"],
            source=raw["source"],
        )
    except (KeyError, TypeError):
        return None


def add_worktree(
    path: str,
    ticket_id: str,
    source: str,
    *,
    state_path: Path | None = None,
) -> None:
    target = state_path or STATE_PATH
    try:
        raw_entries = _load_raw(target)
        raw_entries = [e for e in raw_entries if e.get("path") != path]
        raw_entries.append({"path": path, "ticket_id": ticket_id, "source": source})
        _save_raw(raw_entries, target)
    except Exception as e:
        print(f"[devflow] Warning: could not update worktree state: {e}", file=sys.stderr)


def remove_worktree(path: str, *, state_path: Path | None = None) -> None:
    target = state_path or STATE_PATH
    try:
        raw_entries = _load_raw(target)
        filtered = [e for e in raw_entries if e.get("path") != path]
        if len(filtered) == len(raw_entries):
            return
        _save_raw(filtered, target)
    except Exception as e:
        print(f"[devflow] Warning: could not update worktree state: {e}", file=sys.stderr)


def list_worktrees(
    *,
    purge_stale: bool = True,
    state_path: Path | None = None,
) -> list[WorktreeEntry]:
    target = state_path or STATE_PATH
    try:
        raw_entries = _load_raw(target)
        entries = [e for e in (_parse_entry(r) for r in raw_entries) if e is not None]
        if purge_stale:
            live = [e for e in entries if Path(e.path).is_dir()]
            if len(live) != len(entries):
                _save_raw([asdict(e) for e in live], target)
            return live
        return entries
    except Exception as e:
        print(f"[devflow] Warning: could not read worktree state: {e}", file=sys.stderr)
        return []

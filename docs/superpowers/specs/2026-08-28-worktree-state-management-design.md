# Worktree State Management — Design

**Date:** 2026-08-28

## Overview

Add a state management module to `devflow_sdk` that tracks active worktrees created by `start-issue`. The state persists across processes, enabling `finish-issue` to clean up entries and a future `list` command to show all in-flight work.

## Data Model and Storage

**File:** `~/.devflow/worktree_state.json` (same directory as `config.json`, separate file)

```json
{
  "worktrees": [
    {"path": "/repos/feat-gh42-my-feature", "ticket_id": "42", "source": "github"},
    {"path": "/repos/fix-VDP-123-fix", "ticket_id": "VDP-123", "source": "jira"}
  ]
}
```

**Python dataclass:**

```python
@dataclass
class WorktreeEntry:
    path: str
    ticket_id: str
    source: str  # "github" or "jira"
```

Writes use atomic temp-file-then-rename (same pattern as `config/io.py`) to avoid corruption on crash.

## Module

**Location:** `devflow-sdk/devflow_sdk/worktree_state.py`

```
STATE_PATH = Path.home() / ".devflow" / "worktree_state.json"
```

## Public API

### `add_worktree(path: str, ticket_id: str, source: str) -> None`

Appends a new `WorktreeEntry`. If an entry with the same `path` already exists, it is replaced (idempotent for re-runs of `start-issue` on an existing branch).

### `remove_worktree(path: str) -> None`

Removes the entry whose `path` matches. No-ops silently if not found — `finish-issue` may call this on worktrees that predate the state module.

### `list_worktrees(*, purge_stale: bool = True) -> list[WorktreeEntry]`

Loads all entries. When `purge_stale=True` (default), any entry where `Path(entry.path).is_dir()` returns `False` is dropped and the file is rewritten before returning. Stale = directory no longer exists on disk.

## Error Handling

All three functions are best-effort: if the state file is unreadable, corrupt JSON, or unwritable, they print a warning to stderr and return without raising. A broken state file must never block `start-issue` or `finish-issue` from completing their primary work.

## Integration

### `start-issue.py`

Inside the existing `if worktree_path:` block (alongside `write_issue_context`), add:

```python
from devflow_sdk.worktree_state import add_worktree
add_worktree(worktree_path, issue['id'], issue['source'])
```

### `finish-issue.py`

Two call sites, both right after the existing `remove_issue_context(path)` call:

1. **`--prepare` path** (line ~166): `remove_worktree(path)` before `sys.exit(0)`.
2. **Direct path** (line ~187): `remove_worktree(path)` after `remove_issue_context(path)`.

```python
from devflow_sdk.worktree_state import remove_worktree
remove_worktree(path)
```

## Testing

New file: `devflow-sdk/tests/test_worktree_state.py`

Style: `unittest` + `unittest.mock.patch`, matching existing test files (`test_worktrunk.py`, `test_config_io.py`).

Coverage:
- `add_worktree`: creates file when absent, appends new entry, replaces on duplicate path
- `remove_worktree`: removes matching entry, no-ops when path not in state
- `list_worktrees`: returns all entries, purges stale entries and rewrites file, skips purge when `purge_stale=False`
- Corrupt JSON / missing file handled gracefully (warning to stderr, no exception) for all three functions

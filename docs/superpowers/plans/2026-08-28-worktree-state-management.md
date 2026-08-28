# Worktree State Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `worktree_state` module to `devflow_sdk` that tracks active worktrees, then wire `start-issue` and `finish-issue` to register and deregister entries.

**Architecture:** A single new module `devflow_sdk/worktree_state.py` stores state in `~/.devflow/worktree_state.json` using atomic writes (temp-file + rename). `start-issue` calls `add_worktree` after creating a worktree; `finish-issue` calls `remove_worktree` in both its `--prepare` and direct code paths. All three public functions are best-effort — they print a warning to stderr and return silently on any I/O error.

**Tech Stack:** Python stdlib only (`dataclasses`, `json`, `pathlib`, `tempfile`, `os`). Tests use `unittest` + `unittest.mock.patch`. SDK tests run via `uv run --extra dev pytest` from `devflow-sdk/`.

**Spec:** `docs/superpowers/specs/2026-08-28-worktree-state-management-design.md`

## Global Constraints

- No new third-party dependencies — stdlib only.
- Atomic writes: temp file in the same directory, then `os.rename`, matching the pattern in `devflow_sdk/config/io.py`.
- All three public functions (`add_worktree`, `remove_worktree`, `list_worktrees`) must never raise; they print a `[devflow] Warning:` to `sys.stderr` and return on any exception.
- State file path: `~/.devflow/worktree_state.json` (constant `STATE_PATH = Path.home() / ".devflow" / "worktree_state.json"`).
- `state_path: Path | None = None` keyword argument on all three functions for test injection (defaults to `STATE_PATH`).
- `list_worktrees` stale check: `Path(entry.path).is_dir()` — a directory that no longer exists is stale.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `devflow-sdk/devflow_sdk/worktree_state.py` | Core module: `WorktreeEntry`, `add_worktree`, `remove_worktree`, `list_worktrees` |
| Create | `devflow-sdk/tests/test_worktree_state.py` | SDK unit tests |
| Modify | `devflow/start-issue/start-issue.py` | Import `add_worktree`, call it inside `if worktree_path:` |
| Modify | `devflow/start-issue/tests/test_start_issue.py` | Patch `add_worktree` in all helpers; add `TestMainWorktreeStateIntegration` |
| Modify | `devflow/finish-issue/finish-issue.py` | Import `remove_worktree`, call it after each `remove_issue_context(path)` |
| Modify | `devflow/finish-issue/tests/test_finish_issue.py` | Patch `remove_worktree` in all helpers; add `TestMainWorktreeStateIntegration` |

---

## Task 1: Core `worktree_state` module

**Files:**
- Create: `devflow-sdk/devflow_sdk/worktree_state.py`
- Create: `devflow-sdk/tests/test_worktree_state.py`

**Interfaces:**
- Produces:
  - `WorktreeEntry(path: str, ticket_id: str, source: str)` — dataclass
  - `add_worktree(path: str, ticket_id: str, source: str, *, state_path: Path | None = None) -> None`
  - `remove_worktree(path: str, *, state_path: Path | None = None) -> None`
  - `list_worktrees(*, purge_stale: bool = True, state_path: Path | None = None) -> list[WorktreeEntry]`

- [ ] **Step 1: Write the failing tests**

Create `devflow-sdk/tests/test_worktree_state.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from devflow_sdk.worktree_state import (
    WorktreeEntry,
    add_worktree,
    list_worktrees,
    remove_worktree,
)


class TestAddWorktree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state_path = Path(self._tmp.name) / "worktree_state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _load(self):
        return json.loads(self._state_path.read_text())["worktrees"]

    def test_creates_file_when_absent(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        self.assertTrue(self._state_path.exists())
        entries = self._load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0], {"path": "/repos/feat-42", "ticket_id": "42", "source": "github"})

    def test_appends_new_entry(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        add_worktree("/repos/fix-VDP-1", "VDP-1", "jira", state_path=self._state_path)
        self.assertEqual(len(self._load()), 2)

    def test_replaces_entry_with_same_path(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        add_worktree("/repos/feat-42", "99", "jira", state_path=self._state_path)
        entries = self._load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["ticket_id"], "99")
        self.assertEqual(entries[0]["source"], "jira")

    def test_recovers_from_corrupt_file(self):
        self._state_path.write_text("not json")
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        entries = self._load()
        self.assertEqual(len(entries), 1)

    def test_prints_warning_on_unwritable_path(self):
        unwritable = Path("/no/such/dir/state.json")
        with patch("sys.stderr") as mock_err:
            add_worktree("/repos/feat-42", "42", "github", state_path=unwritable)
        mock_err.write.assert_called()


class TestRemoveWorktree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state_path = Path(self._tmp.name) / "worktree_state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _load(self):
        return json.loads(self._state_path.read_text())["worktrees"]

    def test_removes_matching_entry(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        add_worktree("/repos/fix-VDP-1", "VDP-1", "jira", state_path=self._state_path)
        remove_worktree("/repos/feat-42", state_path=self._state_path)
        entries = self._load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "/repos/fix-VDP-1")

    def test_no_op_when_path_not_in_state(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        remove_worktree("/repos/nonexistent", state_path=self._state_path)
        self.assertEqual(len(self._load()), 1)

    def test_no_op_when_file_absent(self):
        remove_worktree("/repos/feat-42", state_path=self._state_path)
        # Must not raise and must not create the file
        self.assertFalse(self._state_path.exists())


class TestListWorktrees(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state_path = Path(self._tmp.name) / "worktree_state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_empty_when_file_absent(self):
        result = list_worktrees(state_path=self._state_path)
        self.assertEqual(result, [])

    def test_returns_all_live_entries(self):
        dir1 = Path(self._tmp.name) / "wt1"
        dir1.mkdir()
        add_worktree(str(dir1), "42", "github", state_path=self._state_path)
        result = list_worktrees(state_path=self._state_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], WorktreeEntry(path=str(dir1), ticket_id="42", source="github"))

    def test_purges_stale_entry_and_rewrites_file(self):
        dir1 = Path(self._tmp.name) / "wt1"
        dir1.mkdir()
        add_worktree(str(dir1), "42", "github", state_path=self._state_path)
        add_worktree("/nonexistent/wt2", "99", "github", state_path=self._state_path)
        result = list_worktrees(state_path=self._state_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticket_id, "42")
        raw = json.loads(self._state_path.read_text())["worktrees"]
        self.assertEqual(len(raw), 1)

    def test_skips_purge_when_purge_stale_false(self):
        add_worktree("/nonexistent/wt2", "99", "github", state_path=self._state_path)
        result = list_worktrees(purge_stale=False, state_path=self._state_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticket_id, "99")

    def test_does_not_rewrite_file_when_no_stale_entries(self):
        dir1 = Path(self._tmp.name) / "wt1"
        dir1.mkdir()
        add_worktree(str(dir1), "42", "github", state_path=self._state_path)
        mtime_before = self._state_path.stat().st_mtime
        list_worktrees(state_path=self._state_path)
        self.assertEqual(self._state_path.stat().st_mtime, mtime_before)

    def test_returns_empty_on_corrupt_file(self):
        self._state_path.write_text("not json")
        result = list_worktrees(state_path=self._state_path)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_worktree_state.py -v
```

Expected: `ImportError: cannot import name 'WorktreeEntry' from 'devflow_sdk.worktree_state'` (module doesn't exist yet).

- [ ] **Step 3: Implement `devflow-sdk/devflow_sdk/worktree_state.py`**

```python
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
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_worktree_state.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run full SDK test suite to check for regressions**

```bash
cd devflow-sdk && uv run --extra dev pytest
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add devflow-sdk/devflow_sdk/worktree_state.py devflow-sdk/tests/test_worktree_state.py
git commit -m "feat(sdk): add worktree_state module for tracking active worktrees"
```

---

## Task 2: Wire `add_worktree` into `start-issue`

**Files:**
- Modify: `devflow/start-issue/start-issue.py`
- Modify: `devflow/start-issue/tests/test_start_issue.py`

**Interfaces:**
- Consumes: `add_worktree(path: str, ticket_id: str, source: str) -> None` from Task 1

- [ ] **Step 1: Write the failing integration test**

Open `devflow/start-issue/tests/test_start_issue.py` and append this new test class at the end (before `if __name__ == "__main__":`):

```python
class TestMainWorktreeStateIntegration(unittest.TestCase):
    def _run_main(self, worktree_path, issue_data):
        argv = ["start-issue", str(issue_data.get("id", "42"))]
        with patch("sys.argv", argv), \
             patch("atexit.register"), \
             patch("start_issue.fetch", return_value=issue_data), \
             patch("start_issue.run_ai_prompt", return_value=_ai_result("feat")), \
             patch("start_issue.check_worktrunk"), \
             patch("start_issue.check_shell_function"), \
             patch("start_issue.get_repo_root", return_value="/fake/root"), \
             patch("start_issue.detect_and_write_config"), \
             patch("start_issue.create_worktree", return_value=worktree_path), \
             patch("start_issue.write_issue_context"), \
             patch("start_issue.copy_ide_config"), \
             patch("start_issue.prompt_and_open_ai_agent"), \
             patch("start_issue._persist_branch_for_shell"), \
             patch("start_issue.add_worktree") as mock_add, \
             patch.object(start_issue.summary, "start_rate_fetch"), \
             patch.object(start_issue.summary, "add"):
            start_issue.main()
        return mock_add

    def _github_issue(self):
        return {"source": "github", "id": "42", "title": "Add dark mode",
                "body": "", "comments": [], "issuetype": "", "labels": ["enhancement"]}

    def test_add_worktree_called_with_path_ticket_id_and_source(self):
        issue = self._github_issue()
        mock_add = self._run_main("/fake/worktree", issue)
        mock_add.assert_called_once_with("/fake/worktree", "42", "github")

    def test_add_worktree_not_called_when_no_worktree(self):
        mock_add = self._run_main(None, self._github_issue())
        mock_add.assert_not_called()

    def test_add_worktree_called_with_jira_source(self):
        issue = {"source": "jira", "id": "VDP-123", "title": "Fix crash",
                 "body": "", "comments": [], "issuetype": "Bug", "labels": []}
        mock_add = self._run_main("/fake/worktree", issue)
        mock_add.assert_called_once_with("/fake/worktree", "VDP-123", "jira")
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd devflow/start-issue && python -m pytest tests/test_start_issue.py::TestMainWorktreeStateIntegration -v
```

Expected: `AttributeError: module 'start_issue' has no attribute 'add_worktree'` — the import doesn't exist yet.

- [ ] **Step 3: Add the import and call to `start-issue.py`**

In `devflow/start-issue/start-issue.py`, add to the import block (after the existing `devflow_sdk` imports, around line 25):

```python
from devflow_sdk.worktree_state import add_worktree
```

Then inside the `if worktree_path:` block (after `write_issue_context(worktree_path, issue)`, around line 112):

```python
        add_worktree(worktree_path, issue['id'], issue['source'])
```

The block should look like:

```python
    if worktree_path:
        issue["branch"] = branch
        issue["branch_type"] = override if override is not None else infer_type(issue)
        issue["started_at"] = datetime.now(timezone.utc).isoformat()
        write_issue_context(worktree_path, issue)
        add_worktree(worktree_path, issue['id'], issue['source'])
        copy_ide_config(repo_root, worktree_path)
        prompt_and_open_ide(worktree_path)
        prompt_and_open_ai_agent(worktree_path)
```

- [ ] **Step 4: Add `patch("start_issue.add_worktree")` to all existing helpers that run `main()`**

The existing test helpers call `start_issue.main()` without patching `add_worktree`. Now that `add_worktree` is imported, those calls will invoke the real function. Add `patch("start_issue.add_worktree")` to each helper.

**In `TestMainAiInferenceWiring._run_main`** — add to the `with` block:
```python
             patch("start_issue.add_worktree"), \
```

**In `TestMainIssueContextEnrichment._run_main_capture_written_issue`** — add to the `with` block:
```python
             patch("start_issue.add_worktree"), \
```

**In `TestMainIssueContextWriting._run_main`** — add to the `with` block:
```python
             patch("start_issue.add_worktree"), \
```

**In `TestMainAiInferenceWiring.test_ai_result_used_as_branch_type`** (inline `with` block) — add:
```python
             patch("start_issue.add_worktree"), \
```

**In `TestMainIssueContextEnrichment.test_summary_includes_issue_json_path`** (inline `with` block) — add:
```python
             patch("start_issue.add_worktree"), \
```

**In `TestMainIssueContextWriting.test_write_issue_context_not_called_when_no_worktree`** (inline `with` block) — add:
```python
             patch("start_issue.add_worktree"), \
```

**In `TestCheckShellFunctionCalledInStartIssue.test_check_shell_function_called_with_start_issue_sentinel`** (inline `with` block) — add:
```python
             patch("start_issue.add_worktree"), \
```

- [ ] **Step 5: Run the new integration tests to verify they pass**

```bash
cd devflow/start-issue && python -m pytest tests/test_start_issue.py::TestMainWorktreeStateIntegration -v
```

Expected: all 3 new tests pass.

- [ ] **Step 6: Run the full start-issue test suite to verify no regressions**

```bash
cd devflow/start-issue && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add devflow/start-issue/start-issue.py devflow/start-issue/tests/test_start_issue.py
git commit -m "feat(start-issue): register new worktrees in worktree state"
```

---

## Task 3: Wire `remove_worktree` into `finish-issue`

**Files:**
- Modify: `devflow/finish-issue/finish-issue.py`
- Modify: `devflow/finish-issue/tests/test_finish_issue.py`

**Interfaces:**
- Consumes: `remove_worktree(path: str) -> None` from Task 1

- [ ] **Step 1: Write the failing integration test**

Open `devflow/finish-issue/tests/test_finish_issue.py` and append this new test class at the end (before `if __name__ == "__main__":`):

```python
class TestMainWorktreeStateIntegration(unittest.TestCase):
    def _run_main(self, prepare=False):
        argv = ["finish-issue", "65"] + (["--prepare"] if prepare else [])
        worktrees = [{"branch": "main", "path": "/repos/main", "is_main": True}]
        match = {"branch": "feat/wt/gh65-something", "path": "/repos/gh65"}

        with unittest.mock.patch("sys.argv", argv), \
             unittest.mock.patch.object(finish_issue, "check_worktrunk"), \
             unittest.mock.patch.object(finish_issue, "check_shell_function"), \
             unittest.mock.patch.object(finish_issue, "fetch",
                 return_value={"source": "github", "id": "65", "title": "t"}), \
             unittest.mock.patch.object(finish_issue, "list_worktrees", return_value=worktrees), \
             unittest.mock.patch.object(finish_issue, "find_matching_worktrees", return_value=[match]), \
             unittest.mock.patch.object(finish_issue, "get_main_branch", return_value="main"), \
             unittest.mock.patch.object(finish_issue, "is_merged", return_value=True), \
             unittest.mock.patch.object(finish_issue, "is_dirty", return_value=False), \
             unittest.mock.patch.object(finish_issue, "_persist_branch_for_shell", return_value=True), \
             unittest.mock.patch.object(finish_issue, "_persist_worktree_for_shell", return_value=True), \
             unittest.mock.patch.object(finish_issue, "_persist_worktree_path_for_shell", return_value=True), \
             unittest.mock.patch.object(finish_issue, "_clear_force_marker_for_shell", return_value=True), \
             unittest.mock.patch.object(finish_issue, "_cwd_inside_worktree", return_value=False), \
             unittest.mock.patch.object(finish_issue, "remove_issue_context"), \
             unittest.mock.patch.object(finish_issue, "remove_worktree") as mock_remove, \
             unittest.mock.patch.object(finish_issue.subprocess, "run",
                 return_value=unittest.mock.MagicMock(returncode=0, stderr="")):
            try:
                finish_issue.main()
            except SystemExit:
                pass
        return mock_remove

    def test_remove_worktree_called_in_direct_path(self):
        mock_remove = self._run_main(prepare=False)
        mock_remove.assert_called_once_with("/repos/gh65")

    def test_remove_worktree_called_in_prepare_path(self):
        mock_remove = self._run_main(prepare=True)
        mock_remove.assert_called_once_with("/repos/gh65")
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd devflow/finish-issue && python -m pytest tests/test_finish_issue.py::TestMainWorktreeStateIntegration -v
```

Expected: `AttributeError: module 'finish_issue' has no attribute 'remove_worktree'` — the import doesn't exist yet.

- [ ] **Step 3: Add the import and calls to `finish-issue.py`**

In `devflow/finish-issue/finish-issue.py`, add to the import block (after the existing `devflow_sdk` imports, around line 19):

```python
from devflow_sdk.worktree_state import remove_worktree
```

**First call site — inside the `if args.prepare:` block**, immediately after `remove_issue_context(path)` (around line 166):

```python
    if args.prepare:
        ok = _persist_branch_for_shell(main_branch)
        ok = _persist_worktree_for_shell(branch) and ok
        ok = _clear_force_marker_for_shell() and ok
        if force_remove:
            ok = _persist_force_for_shell() and ok
        ok = _persist_worktree_path_for_shell(path) and ok
        remove_issue_context(path)
        remove_worktree(path)
        sys.exit(0 if ok else 1)
```

**Second call site — direct (non-`--prepare`) path**, immediately after `remove_issue_context(path)` (around line 187):

```python
    remove_issue_context(path)
    remove_worktree(path)
    print(f"Removing worktree...")
```

- [ ] **Step 4: Add `patch.object(finish_issue, "remove_worktree")` to all existing helpers**

The existing helpers call `finish_issue.main()` without patching `remove_worktree`. Now that it's imported, those calls will invoke the real function. Add the patch to each helper.

**In `TestMainDirtyWorktreeHandling._run_main_with`** — add to the `with` block:
```python
             unittest.mock.patch.object(finish_issue, "remove_worktree"), \
```

**In `TestMainIssueContextCleanup._run_main`** — add to the `with` block:
```python
             unittest.mock.patch.object(finish_issue, "remove_worktree"), \
```

**In `TestMainIssueAutoDetection._run_main`** — add to the `with` block:
```python
             unittest.mock.patch.object(finish_issue, "remove_worktree"), \
```

**In `TestCheckShellFunctionCalledInFinishIssue.test_check_shell_function_called_with_finish_issue_sentinel_and_prepare`** (inline `with` block) — add:
```python
             unittest.mock.patch.object(finish_issue, "remove_worktree"), \
```

- [ ] **Step 5: Run the new integration tests to verify they pass**

```bash
cd devflow/finish-issue && python -m pytest tests/test_finish_issue.py::TestMainWorktreeStateIntegration -v
```

Expected: both new tests pass.

- [ ] **Step 6: Run the full finish-issue test suite to verify no regressions**

```bash
cd devflow/finish-issue && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Run the SDK test suite one final time**

```bash
cd devflow-sdk && uv run --extra dev pytest
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add devflow/finish-issue/finish-issue.py devflow/finish-issue/tests/test_finish_issue.py
git commit -m "feat(finish-issue): deregister worktrees from state on removal"
```

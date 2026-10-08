# Stacked PR Support for `start-issue` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `start-issue` is run from inside a devflow-managed worktree, use the current branch as the PR base instead of `main`, enabling stacked PR workflows.

**Architecture:** Add a `parent_branch` field to `WorktreeEntry` and persist it in `worktree_state.json` when `start-issue` detects a stacked context. Enhance `get_base_branch()` to read this field before falling back to trunk detection. Fix `draft-pr` to pass `--base` explicitly to `gh pr create`.

**Tech Stack:** Python 3, `unittest` + `unittest.mock`, `questionary` (for prompts), GitHub CLI (`gh`), git CLI

**Spec:** Grilling session 2026-10-08 (no separate spec doc)

## Global Constraints

- `parent_branch` is stored only in `worktree_state.json` — never in `.issue.json`
- Stacked branch naming follows the same convention as normal branches (`feat/...`, `fix/...`)
- Re-targeting child PRs after the parent branch merges is out of scope
- If `git pull --rebase` fails during "update", abort the rebase and exit non-zero with a clear message
- Always `git fetch` before checking behind count — never use stale remote refs
- Only devflow-managed worktrees (tracked in `worktree_state.json`) trigger stacked mode

## Review Focus

- **Running from the main checkout**: `list_tracked_worktrees` returns entries, but none match CWD → `_detect_stack_parent()` returns `None` → `start-issue` behaves identically to before
- **Base branch is ahead of remote** (local unpushed commits): behind count is 0 → no prompt, proceed normally
- **Base branch has no upstream set**: `git fetch origin {branch}` succeeds silently or fails; `git rev-list HEAD..origin/{branch}` returns non-zero → behind count treated as 0 → no prompt
- **`draft-pr` from a non-stacked worktree** (`parent_branch` is `None`): `get_base_branch()` finds the entry but `entry.parent_branch` is falsy → falls through to origin/HEAD → `--base main` as before
- **Rebase conflict during "update"**: `git pull --rebase` exits non-zero → `git rebase --abort` runs → clear error printed → `sys.exit(1)`

---

### Task 1: Add `parent_branch` to `WorktreeEntry`

**Files:**
- Modify: `devflow-sdk/devflow_sdk/worktree_state.py` (lines 13–17, 50–58, 62–76)
- Test: `devflow-sdk/tests/test_worktree_state.py` (update existing)

**Interfaces:**
- Produces: `WorktreeEntry.parent_branch: str | None` — consumed by Task 2 and Task 4
- Produces: `add_worktree(path, ticket_id, source, *, parent_branch=None, state_path=None)` — called by Task 4's `start-issue.py`

- [ ] **Step 1: Read the files**

  Open `devflow-sdk/devflow_sdk/worktree_state.py` and `devflow-sdk/tests/test_worktree_state.py` to confirm current state before editing.

- [ ] **Step 2: Write failing tests**

  Add to `devflow-sdk/tests/test_worktree_state.py` inside `TestAddWorktree`:

  ```python
  def test_stores_parent_branch_when_provided(self):
      add_worktree("/repos/feat-42", "42", "github",
                   parent_branch="feat/wt/issue-1-some-base",
                   state_path=self._state_path)
      entries = self._load()
      self.assertEqual(entries[0]["parent_branch"], "feat/wt/issue-1-some-base")

  def test_omits_parent_branch_when_not_provided(self):
      add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
      entries = self._load()
      self.assertNotIn("parent_branch", entries[0])
  ```

  Add to `TestListWorktrees`:

  ```python
  def test_roundtrips_parent_branch(self):
      dir1 = Path(self._tmp.name) / "wt1"
      dir1.mkdir()
      add_worktree(str(dir1), "42", "github",
                   parent_branch="feat/wt/issue-1-base",
                   state_path=self._state_path)
      result = list_tracked_worktrees(state_path=self._state_path)
      self.assertEqual(result[0].parent_branch, "feat/wt/issue-1-base")

  def test_parent_branch_defaults_to_none_when_absent_in_json(self):
      dir1 = Path(self._tmp.name) / "wt1"
      dir1.mkdir()
      # Write entry without parent_branch (old format)
      self._state_path.write_text(json.dumps({"worktrees": [
          {"path": str(dir1), "ticket_id": "1", "source": "github"}
      ]}))
      result = list_tracked_worktrees(purge_stale=False, state_path=self._state_path)
      self.assertIsNone(result[0].parent_branch)
  ```

- [ ] **Step 3: Run tests to verify they fail**

  ```
  cd devflow-sdk && python -m pytest tests/test_worktree_state.py -v -k "parent_branch" 2>&1 | head -30
  ```

  Expected: 4 failures with `TypeError` or `unexpected keyword argument`.

- [ ] **Step 4: Add `parent_branch` to `WorktreeEntry`**

  In `worktree_state.py`, update the dataclass:

  ```python
  @dataclass
  class WorktreeEntry:
      path: str
      ticket_id: str
      source: str
      parent_branch: str | None = None
  ```

- [ ] **Step 5: Update `_parse_entry()` to read `parent_branch`**

  ```python
  def _parse_entry(raw: dict) -> WorktreeEntry | None:
      try:
          path = raw["path"]
          ticket_id = raw["ticket_id"]
          source = raw["source"]
          if not isinstance(path, str) or not isinstance(ticket_id, str) or not isinstance(source, str):
              return None
          parent_branch = raw.get("parent_branch")
          if parent_branch is not None and not isinstance(parent_branch, str):
              parent_branch = None
          return WorktreeEntry(path=path, ticket_id=ticket_id, source=source, parent_branch=parent_branch)
      except (KeyError, TypeError):
          return None
  ```

- [ ] **Step 6: Update `add_worktree()` to accept `parent_branch`**

  ```python
  def add_worktree(
      path: str,
      ticket_id: str,
      source: str,
      *,
      parent_branch: str | None = None,
      state_path: Path | None = None,
  ) -> None:
      target = state_path or STATE_PATH
      try:
          raw_entries = _load_raw(target)
          raw_entries = [e for e in raw_entries if e.get("path") != path]
          entry: dict = {"path": path, "ticket_id": ticket_id, "source": source}
          if parent_branch is not None:
              entry["parent_branch"] = parent_branch
          raw_entries.append(entry)
          _save_raw(raw_entries, target)
      except Exception as e:
          print(f"[devflow] Warning: could not update worktree state: {e}", file=sys.stderr)
  ```

- [ ] **Step 7: Run all worktree_state tests**

  ```
  python -m pytest tests/test_worktree_state.py -v
  ```

  Expected: all pass. The existing `test_returns_all_live_entries` uses `WorktreeEntry(path=..., ticket_id=..., source=...)` — it still passes because `parent_branch` defaults to `None` in both the constructed and parsed entries.

- [ ] **Step 8: Commit**

  ```bash
  git add devflow-sdk/devflow_sdk/worktree_state.py devflow-sdk/tests/test_worktree_state.py
  git commit -m "feat: add parent_branch field to WorktreeEntry for stacked PR support"
  ```

---

### Task 2: Enhance `get_base_branch()` to check worktree state

**Files:**
- Modify: `devflow-sdk/devflow_sdk/core/git/git_ops.py` (lines 18–46)
- Test: `devflow-sdk/tests/test_git_ops.py` (update existing `TestGetBaseBranch`)

**Interfaces:**
- Consumes: `WorktreeEntry.parent_branch` from Task 1
- Consumes: `list_tracked_worktrees(purge_stale=False)` from `devflow_sdk.worktree_state`
- Consumes: `_cwd_inside_worktree(entry.path)` from `devflow_sdk.core.git.worktree`
- Produces: `get_base_branch()` — now returns `parent_branch` when in a stacked worktree

- [ ] **Step 1: Write failing tests**

  Add to `TestGetBaseBranch` in `devflow-sdk/tests/test_git_ops.py`:

  ```python
  def test_returns_parent_branch_when_in_stacked_worktree(self):
      from devflow_sdk.worktree_state import WorktreeEntry
      mock_entry = WorktreeEntry(
          path="/repos/wt/feat-base",
          ticket_id="42",
          source="github",
          parent_branch="feat/wt/issue-1-some-base",
      )
      with patch("devflow_sdk.worktree_state.list_tracked_worktrees", return_value=[mock_entry]), \
           patch("devflow_sdk.core.git.worktree._cwd_inside_worktree", return_value=True):
          self.assertEqual(get_base_branch(), "feat/wt/issue-1-some-base")

  def test_falls_through_when_no_parent_branch_in_worktree(self):
      from devflow_sdk.worktree_state import WorktreeEntry
      mock_entry = WorktreeEntry(path="/repos/wt/feat", ticket_id="1", source="github")
      with patch("devflow_sdk.worktree_state.list_tracked_worktrees", return_value=[mock_entry]), \
           patch("devflow_sdk.core.git.worktree._cwd_inside_worktree", return_value=True), \
           patch("devflow_sdk.core.git.git_ops.subprocess.run",
                 return_value=_proc(stdout="origin/main\n")):
          self.assertEqual(get_base_branch(), "main")

  def test_falls_through_when_not_in_any_tracked_worktree(self):
      with patch("devflow_sdk.worktree_state.list_tracked_worktrees", return_value=[]), \
           patch("devflow_sdk.core.git.git_ops.subprocess.run",
                 return_value=_proc(stdout="origin/develop\n")):
          self.assertEqual(get_base_branch(), "develop")

  def test_falls_through_gracefully_when_worktree_state_raises(self):
      with patch("devflow_sdk.worktree_state.list_tracked_worktrees",
                 side_effect=Exception("disk error")), \
           patch("devflow_sdk.core.git.git_ops.subprocess.run",
                 return_value=_proc(stdout="origin/main\n")):
          self.assertEqual(get_base_branch(), "main")
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```
  cd devflow-sdk && python -m pytest tests/test_git_ops.py::TestGetBaseBranch -v 2>&1 | head -30
  ```

  Expected: 4 new failures.

- [ ] **Step 3: Update `get_base_branch()` in `git_ops.py`**

  Replace the function with:

  ```python
  def get_base_branch():
      """Detect the branch's target/base branch: parent branch for stacked worktrees,
      otherwise origin/HEAD, falling back to the GitHub default branch via `gh`,
      falling back to 'main'."""
      try:
          from devflow_sdk.worktree_state import list_tracked_worktrees
          from devflow_sdk.core.git.worktree import _cwd_inside_worktree
          for entry in list_tracked_worktrees(purge_stale=False):
              if entry.parent_branch and _cwd_inside_worktree(entry.path):
                  return entry.parent_branch
      except Exception:
          pass

      result = _run_git(["rev-parse", "--abbrev-ref", "origin/HEAD"])
      if result.returncode == 0:
          value = result.stdout.strip()
          if value and "/" in value and value != "origin/HEAD":
              return value.split("/", 1)[1]

      try:
          gh_result = subprocess.run(
              ["gh", "repo", "view", "--json", "defaultBranchRef",
               "--jq", ".defaultBranchRef.name"],
              capture_output=True,
              text=True,
          )
          if gh_result.returncode == 0:
              branch = gh_result.stdout.strip()
              if branch:
                  return branch
      except (FileNotFoundError, OSError):
          pass

      print(
          "WARNING: Could not detect default branch from origin/HEAD or "
          "GitHub; assuming 'main'.",
          file=sys.stderr,
      )
      return "main"
  ```

- [ ] **Step 4: Run all git_ops tests**

  ```
  python -m pytest tests/test_git_ops.py -v
  ```

  Expected: all pass (existing tests unaffected because `list_tracked_worktrees` is not patched in them, so the lazy import path is taken and returns an empty list, falling through to the mocked `subprocess.run`).

  Note: If existing tests fail because `list_tracked_worktrees` is called without mocking and reads the real `~/.devflow/worktree_state.json`, patch it in `setUp`:

  ```python
  def setUp(self):
      patcher = patch("devflow_sdk.worktree_state.list_tracked_worktrees", return_value=[])
      self.mock_wt = patcher.start()
      self.addCleanup(patcher.stop)
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add devflow-sdk/devflow_sdk/core/git/git_ops.py devflow-sdk/tests/test_git_ops.py
  git commit -m "feat: get_base_branch returns parent branch when in a stacked worktree"
  ```

---

### Task 3: Pass `--base` to `gh pr create` in `draft-pr`

**Files:**
- Modify: `devflow/draft-pr/build_pr_body.py` (line 6, lines 9–23)
- Modify: `devflow/draft-pr/draft-pr.py` (line 118)
- Test: `devflow/draft-pr/tests/test_build_pr_body.py` (update existing)

**Interfaces:**
- Consumes: `data["base"]` from `gather_pr_data.collect()` — already present, not changed
- Produces: `write_create_script(title, body_path, script_path, base=None)` — new optional `base` param

- [ ] **Step 1: Write failing tests**

  Add to `devflow/draft-pr/tests/test_build_pr_body.py`:

  ```python
  def test_script_contains_base_flag_when_provided(self):
      with tempfile.TemporaryDirectory() as tmp:
          body_path = os.path.join(tmp, "pr-body.md")
          script_path = os.path.join(tmp, "create-pr.sh")
          write_create_script("Title", body_path, script_path,
                               base="feat/wt/issue-1-some-base")
          with open(script_path) as f:
              content = f.read()
          self.assertIn("--base 'feat/wt/issue-1-some-base'", content)

  def test_script_omits_base_flag_when_not_provided(self):
      with tempfile.TemporaryDirectory() as tmp:
          body_path = os.path.join(tmp, "pr-body.md")
          script_path = os.path.join(tmp, "create-pr.sh")
          write_create_script("Title", body_path, script_path)
          with open(script_path) as f:
              content = f.read()
          self.assertNotIn("--base", content)
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```
  cd devflow/draft-pr && python -m pytest tests/test_build_pr_body.py -v -k "base" 2>&1 | head -20
  ```

  Expected: 2 failures.

- [ ] **Step 3: Update `write_create_script()` in `build_pr_body.py`**

  ```python
  import os
  import shlex
  import stat


  def write_create_script(title, body_path, script_path, base=None):
      safe_title = shlex.quote(title)
      safe_body = shlex.quote(body_path)
      base_line = f"  --base {shlex.quote(base)} \\\n" if base else ""
      script = f"""\
  #!/bin/bash
  set -euo pipefail

  command -v gh &>/dev/null || {{ echo "gh CLI not found. Install from https://cli.github.com/"; exit 1; }}
  gh auth status &>/dev/null 2>&1 || {{ echo "Not logged in. Run: gh auth login"; exit 1; }}

  git push -u origin HEAD

  gh pr create \\
    --draft \\
    --title {safe_title} \\
    --body-file {safe_body} \\
  {base_line}  --head "$(git branch --show-current)"
  """
      with open(script_path, "w") as f:
          f.write(script)
      os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
  ```

- [ ] **Step 4: Update the call site in `draft-pr.py`**

  Change line 118 from:

  ```python
  write_create_script(title, body_path, script_path)
  ```

  to:

  ```python
  write_create_script(title, body_path, script_path, base=data.get("base"))
  ```

- [ ] **Step 5: Run all draft-pr tests**

  ```
  cd devflow/draft-pr && python -m pytest tests/ -v
  ```

  Expected: all pass.

- [ ] **Step 6: Commit**

  ```bash
  git add devflow/draft-pr/build_pr_body.py devflow/draft-pr/draft-pr.py \
          devflow/draft-pr/tests/test_build_pr_body.py
  git commit -m "feat: pass --base to gh pr create so stacked PRs target the parent branch"
  ```

---

### Task 4: Stacked-mode detection and validation in `start-issue`

**Files:**
- Modify: `devflow/start-issue/start-issue.py` (lines 66–139)
- Test: `devflow/start-issue/tests/test_start_issue.py` (update or extend existing)

**Interfaces:**
- Consumes: `add_worktree(..., parent_branch=...)` from Task 1
- Consumes: `list_tracked_worktrees(purge_stale=False)` from `devflow_sdk.worktree_state`
- Consumes: `_cwd_inside_worktree(entry.path)` from `devflow_sdk.core.git.worktree`
- Consumes: `select(message, choices, single=True)` from `devflow_sdk.core.prompts`

- [ ] **Step 1: Write failing tests**

  Add to `devflow/start-issue/tests/test_start_issue.py` (or create the file):

  ```python
  import sys
  import os
  import unittest
  from unittest.mock import patch, MagicMock

  _HERE = os.path.dirname(__file__)
  sys.path.insert(0, os.path.join(_HERE, ".."))

  # Import helpers under test after path setup
  import start_issue as _si  # noqa — triggers module-level sys.path setup

  from start_issue import _detect_stack_parent, _validate_base_branch


  def _entry(path, parent_branch=None):
      from devflow_sdk.worktree_state import WorktreeEntry
      return WorktreeEntry(path=path, ticket_id="1", source="github",
                           parent_branch=parent_branch)


  class TestDetectStackParent(unittest.TestCase):
      def test_returns_none_when_not_in_tracked_worktree(self):
          with patch("devflow_sdk.worktree_state.list_tracked_worktrees", return_value=[]), \
               patch("devflow_sdk.core.git.worktree._cwd_inside_worktree", return_value=False):
              self.assertIsNone(_detect_stack_parent())

      def test_returns_current_branch_when_in_tracked_worktree(self):
          proc = MagicMock(); proc.returncode = 0; proc.stdout = "feat/wt/issue-1-base\n"
          with patch("devflow_sdk.worktree_state.list_tracked_worktrees",
                     return_value=[_entry("/repos/wt/feat-base")]), \
               patch("devflow_sdk.core.git.worktree._cwd_inside_worktree", return_value=True), \
               patch("subprocess.run", return_value=proc):
              self.assertEqual(_detect_stack_parent(), "feat/wt/issue-1-base")

      def test_returns_none_when_git_branch_fails(self):
          proc = MagicMock(); proc.returncode = 128; proc.stdout = ""
          with patch("devflow_sdk.worktree_state.list_tracked_worktrees",
                     return_value=[_entry("/repos/wt/feat-base")]), \
               patch("devflow_sdk.core.git.worktree._cwd_inside_worktree", return_value=True), \
               patch("subprocess.run", return_value=proc):
              self.assertIsNone(_detect_stack_parent())


  class TestValidateBaseBranch(unittest.TestCase):
      def _proc(self, returncode=0, stdout=""):
          p = MagicMock(); p.returncode = returncode; p.stdout = stdout
          return p

      def test_returns_true_when_up_to_date(self):
          fetch_ok = self._proc(0)
          behind_zero = self._proc(0, "0\n")
          with patch("subprocess.run", side_effect=[fetch_ok, behind_zero]):
              self.assertTrue(_validate_base_branch("feat/wt/issue-1-base"))

      def test_returns_true_when_behind_count_unreadable(self):
          fetch_ok = self._proc(0)
          count_fail = self._proc(1, "")
          with patch("subprocess.run", side_effect=[fetch_ok, count_fail]):
              self.assertTrue(_validate_base_branch("feat/wt/issue-1-base"))

      def test_accept_prints_warning_and_returns_true(self):
          fetch_ok = self._proc(0)
          behind_five = self._proc(0, "5\n")
          with patch("subprocess.run", side_effect=[fetch_ok, behind_five]), \
               patch("devflow_sdk.core.prompts.select", return_value="Accept"), \
               patch("sys.stderr"):
              result = _validate_base_branch("feat/wt/issue-1-base")
          self.assertTrue(result)

      def test_update_success_returns_true(self):
          fetch_ok = self._proc(0)
          behind_two = self._proc(0, "2\n")
          pull_ok = self._proc(0)
          with patch("subprocess.run", side_effect=[fetch_ok, behind_two, pull_ok]), \
               patch("devflow_sdk.core.prompts.select", return_value="Update"):
              self.assertTrue(_validate_base_branch("feat/wt/issue-1-base"))

      def test_update_rebase_conflict_aborts_and_exits(self):
          fetch_ok = self._proc(0)
          behind_two = self._proc(0, "2\n")
          pull_fail = self._proc(1)
          abort_ok = self._proc(0)
          with patch("subprocess.run", side_effect=[fetch_ok, behind_two, pull_fail, abort_ok]), \
               patch("devflow_sdk.core.prompts.select", return_value="Update"), \
               self.assertRaises(SystemExit) as cm:
              _validate_base_branch("feat/wt/issue-1-base")
          self.assertEqual(cm.exception.code, 1)
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```
  cd devflow/start-issue && python -m pytest tests/test_start_issue.py -v \
      -k "StackParent or ValidateBase" 2>&1 | head -30
  ```

  Expected: failures with `ImportError` or `AttributeError` since the functions don't exist yet.

- [ ] **Step 3: Add `_detect_stack_parent()` to `start-issue.py`**

  Add after the `_ai_infer_type` function (before `main()`):

  ```python
  def _detect_stack_parent() -> str | None:
      """Return the current branch if running inside a devflow-managed worktree, else None."""
      try:
          from devflow_sdk.worktree_state import list_tracked_worktrees
          from devflow_sdk.core.git.worktree import _cwd_inside_worktree
          for entry in list_tracked_worktrees(purge_stale=False):
              if _cwd_inside_worktree(entry.path):
                  result = subprocess.run(
                      ["git", "branch", "--show-current"],
                      capture_output=True, text=True,
                  )
                  if result.returncode == 0 and result.stdout.strip():
                      return result.stdout.strip()
      except Exception:
          pass
      return None
  ```

- [ ] **Step 4: Add `_validate_base_branch()` to `start-issue.py`**

  Add immediately after `_detect_stack_parent()`:

  ```python
  def _validate_base_branch(parent_branch: str) -> bool:
      """Fetch and check if parent_branch is behind remote. Prompts user if behind.
      Returns True to proceed, exits with code 1 on rebase conflict."""
      subprocess.run(
          ["git", "fetch", "origin", parent_branch],
          capture_output=True, text=True,
      )
      result = subprocess.run(
          ["git", "rev-list", "--count", f"HEAD..origin/{parent_branch}"],
          capture_output=True, text=True,
      )
      if result.returncode != 0:
          return True
      try:
          behind = int(result.stdout.strip())
      except ValueError:
          return True
      if behind == 0:
          return True

      from devflow_sdk.core.prompts import select
      answer = select(
          f"Base branch '{parent_branch}' is {behind} commit(s) behind origin/{parent_branch}.",
          choices=["Accept (proceed with stale base)", "Update (git pull --rebase)"],
          single=True,
      )
      if not answer or answer.startswith("Accept"):
          print(
              f"⚠️  Proceeding with stale base — your stack may need rebasing later.",
              file=sys.stderr,
          )
          return True

      pull = subprocess.run(["git", "pull", "--rebase"])
      if pull.returncode != 0:
          subprocess.run(["git", "rebase", "--abort"], capture_output=True)
          print(
              f"ERROR: Rebase of '{parent_branch}' failed. Resolve conflicts and re-run start-issue.",
              file=sys.stderr,
          )
          sys.exit(1)
      return True
  ```

- [ ] **Step 5: Wire stacked detection into `main()`**

  In `main()`, after line 110 (`repo_root = get_repo_root()`), add:

  ```python
  parent_branch = _detect_stack_parent()
  if parent_branch is not None:
      _validate_base_branch(parent_branch)
  ```

  Then on line 119, update the `add_worktree` call:

  ```python
  add_worktree(worktree_path, issue['id'], issue['source'], parent_branch=parent_branch)
  ```

- [ ] **Step 6: Run the new tests**

  ```
  cd devflow/start-issue && python -m pytest tests/test_start_issue.py -v \
      -k "StackParent or ValidateBase"
  ```

  Expected: all pass.

- [ ] **Step 7: Run all start-issue tests**

  ```
  python -m pytest tests/ -v
  ```

  Expected: all pass.

- [ ] **Step 8: Commit**

  ```bash
  git add devflow/start-issue/start-issue.py devflow/start-issue/tests/test_start_issue.py
  git commit -m "feat: detect stacked worktree context in start-issue and validate base branch"
  ```

---

## Review Focus — Tests to add per owning task

Each line from the Review Focus section above maps to an existing test task:

| Risk | Covered in | Test |
|---|---|---|
| Running from main checkout | Task 4, `TestDetectStackParent` | `test_returns_none_when_not_in_tracked_worktree` |
| Base ahead of remote | Task 4, `TestValidateBaseBranch` | `test_returns_true_when_up_to_date` (behind=0 covers ahead=0 too; add `test_returns_true_when_ahead_of_remote` with behind=0) |
| No upstream set | Task 4, `TestValidateBaseBranch` | `test_returns_true_when_behind_count_unreadable` |
| `draft-pr` non-stacked (`parent_branch=None`) | Task 2, `TestGetBaseBranch` | `test_falls_through_when_no_parent_branch_in_worktree` |
| Rebase conflict | Task 4, `TestValidateBaseBranch` | `test_update_rebase_conflict_aborts_and_exits` |

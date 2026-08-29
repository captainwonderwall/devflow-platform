# SDK Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `devflow-sdk` into a strict two-zone layout — `core/` for infrastructure, `domain/` for bounded business contexts — enforced by `import-linter`, while eliminating all legacy shims and pulling shared tool logic into the SDK.

**Architecture:** All infrastructure (AI, config, git primitives, plugin machinery, prompts) moves under `devflow_sdk/core/`. Business domains (`issue`, `workspace`) live under `devflow_sdk/domain/`. Tools are updated to import from the new paths. `import-linter` enforces that `core` never imports `domain` and that domains stay independent of each other.

**Tech Stack:** Python, pytest, import-linter, justfile, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-08-29-sdk-refactor-design.md`

## Global Constraints

- Haiku model for implementation; Sonnet 5 max for review; do not use Opus
- All `pytest devflow-sdk/tests/` must pass after every SDK task
- No shim files (forwarding-only modules) at any path
- `_worktrunk.py` remains private (underscore prefix); consumers go through `devflow_sdk.core.git.check_worktrunk` or `devflow_sdk.core.git.worktree.*`
- `start-issue`'s `_persist_branch_for_shell` (writes `~/.start-issue-branch`) is renamed `_persist_start_branch_for_shell` in `core/git/shell_state.py` to avoid collision with `finish-issue`'s version (writes `~/.finish-issue-branch`)
- External plugin authors import from `devflow_sdk.core.plugin` — this is the committed stable surface

---

## File Map

**Created:**
- `devflow_sdk/core/__init__.py` (empty)
- `devflow_sdk/core/branch_name.py` ← from `devflow_sdk/branch_name.py`
- `devflow_sdk/core/cost.py` ← from `devflow_sdk/cost.py`
- `devflow_sdk/core/prompts.py` ← from `devflow_sdk/prompts.py`
- `devflow_sdk/core/shell_function_check.py` ← from `devflow_sdk/shell_function_check.py`
- `devflow_sdk/core/summary.py` ← from `devflow_sdk/summary.py`; update import → `devflow_sdk.core.cost`
- `devflow_sdk/core/config/` ← from `devflow_sdk/config/` (structure unchanged)
- `devflow_sdk/core/ai/__init__.py` ← content of `devflow_sdk/ai.py`; update imports → `devflow_sdk.core.*`
- `devflow_sdk/core/ai/providers/` ← from `devflow_sdk/ai_providers/`
- `devflow_sdk/core/git/__init__.py` ← re-exports `worktree`, `check_worktrunk`, submodules
- `devflow_sdk/core/git/worktree.py` ← split from `worktrunk.py` + `start-issue/worktree.py`
- `devflow_sdk/core/git/_worktrunk.py` ← private wt CLI adapter (split from `worktrunk.py`)
- `devflow_sdk/core/git/git_ops.py` ← from `squash-commits/git_ops.py`
- `devflow_sdk/core/git/merge_check.py` ← from `finish-issue/merge_check.py`
- `devflow_sdk/core/git/shell_state.py` ← merged from `finish-issue/shell_state.py` + `start-issue/worktree.py`'s `_persist_branch_for_shell` (renamed)
- `devflow_sdk/core/plugin/__init__.py` ← new stable public API re-exports
- `devflow_sdk/core/plugin/contracts.py` ← from `devflow_sdk/plugin/draft_pr_plugin.py`
- `devflow_sdk/core/plugin/plugin_base.py` ← from `devflow_sdk/plugin/plugin_base.py`
- `devflow_sdk/core/plugin/plugin_loader.py` ← from `devflow_sdk/plugin/plugin_loader.py`
- `devflow_sdk/core/plugin/plugin_loader_impl.py` ← from `devflow_sdk/plugin/plugin_loader_impl.py`; update imports → `devflow_sdk.core.*`
- `devflow_sdk/core/plugin/plugin_registry.py` ← from `devflow_sdk/plugin/plugin_registry.py`
- `devflow_sdk/domain/__init__.py` (empty)
- `devflow_sdk/domain/issue/__init__.py` ← re-exports public API
- `devflow_sdk/domain/issue/ticket_info.py` ← from `devflow_sdk/ticket_info.py`
- `devflow_sdk/domain/issue/issue_context.py` ← from `devflow_sdk/issue_context.py`
- `devflow_sdk/domain/workspace/__init__.py` ← new; implements `check_manager`, `create`, `find_for_issue`, `list_workspaces`
- `devflow-sdk/tests/test_git_ops.py` ← from `squash-commits/tests/test_git_ops.py`
- `devflow-sdk/tests/test_merge_check.py` ← from `finish-issue/tests/test_merge_check.py`
- `devflow-sdk/tests/test_shell_state.py` ← from `finish-issue/tests/test_shell_state.py`
- `devflow-sdk/tests/test_worktree.py` ← merged from `devflow-sdk/tests/test_worktrunk.py` + `start-issue/tests/test_worktree.py`
- `devflow-sdk/tests/test_workspace.py` ← new tests for `domain/workspace`
- `devflow-sdk/tests/test_plugin_public_api.py` ← new smoke test for plugin re-exports

**Deleted:**
- `devflow_sdk/branch_name.py`, `cost.py`, `prompts.py`, `shell_function_check.py`, `summary.py`
- `devflow_sdk/ticket_info.py`, `issue_context.py`, `worktrunk.py`, `ai.py`
- `devflow_sdk/ai_providers/` (entire directory)
- `devflow_sdk/config/` (entire directory, replaced by `core/config/`)
- `devflow_sdk/plugin/` (entire directory, replaced by `core/plugin/`)
- `devflow_sdk/plugin_base.py`, `plugin_loader.py`, `plugin_registry.py`, `draft_pr_plugin.py` (root shims)
- `devflow-sdk/tests/test_worktrunk.py` (replaced by `test_worktree.py`)
- `devflow/plugin-manager/` (entire directory)
- `devflow/draft-pr/config.py`
- `devflow/start-issue/worktree.py`
- `devflow/finish-issue/shell_state.py`, `merge_check.py`
- `devflow/squash-commits/git_ops.py`
- `squash-commits/tests/test_git_ops.py`, `finish-issue/tests/test_merge_check.py`, `finish-issue/tests/test_shell_state.py`, `start-issue/tests/test_worktree.py`

---

### Task 1: Scaffold new package structure

**Files:**
- Create: `devflow_sdk/core/__init__.py`
- Create: `devflow_sdk/core/git/__init__.py`
- Create: `devflow_sdk/domain/__init__.py`
- Create: `devflow_sdk/domain/issue/__init__.py`
- Create: `devflow_sdk/domain/workspace/__init__.py`

**Interfaces:**
- Produces: empty package namespaces that Tasks 2–9 populate

- [ ] **Step 1: Create the five empty `__init__.py` files**

```python
# devflow_sdk/core/__init__.py  (empty)
# devflow_sdk/core/git/__init__.py  (empty — filled in Task 6)
# devflow_sdk/domain/__init__.py  (empty)
# devflow_sdk/domain/issue/__init__.py  (empty — filled in Task 8)
# devflow_sdk/domain/workspace/__init__.py  (empty — filled in Task 9)
```

- [ ] **Step 2: Verify the existing test suite still passes (no imports changed yet)**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

Expected: all tests pass (no file has been deleted yet).

- [ ] **Step 3: Commit**

```bash
git add devflow_sdk/core/__init__.py devflow_sdk/core/git/__init__.py \
        devflow_sdk/domain/__init__.py devflow_sdk/domain/issue/__init__.py \
        devflow_sdk/domain/workspace/__init__.py
git commit -m "chore: scaffold core/ and domain/ package structure"
```

---

### Task 2: Move leaf core modules

Move `branch_name.py`, `cost.py`, `prompts.py`, `shell_function_check.py` to `core/`. These have no SDK dependencies. Update every within-SDK import that references the old paths.

**Files:**
- Create: `devflow_sdk/core/branch_name.py`
- Create: `devflow_sdk/core/cost.py`
- Create: `devflow_sdk/core/prompts.py`
- Create: `devflow_sdk/core/shell_function_check.py`
- Modify: `devflow_sdk/worktrunk.py` — update `branch_name` import
- Modify: `devflow_sdk/plugin/plugin_loader_impl.py` — update `prompts` import
- Modify: `devflow-sdk/tests/test_branch_name.py`, `test_cost.py`, `test_prompts.py`, `test_shell_function_check.py`
- Delete: `devflow_sdk/branch_name.py`, `cost.py`, `prompts.py`, `shell_function_check.py`

**Interfaces:**
- Produces: `devflow_sdk.core.branch_name`, `devflow_sdk.core.cost`, `devflow_sdk.core.prompts`, `devflow_sdk.core.shell_function_check`

- [ ] **Step 1: Copy the four files to `core/` (content unchanged)**

```bash
cp devflow_sdk/branch_name.py devflow_sdk/core/branch_name.py
cp devflow_sdk/cost.py devflow_sdk/core/cost.py
cp devflow_sdk/prompts.py devflow_sdk/core/prompts.py
cp devflow_sdk/shell_function_check.py devflow_sdk/core/shell_function_check.py
```

- [ ] **Step 2: Update `devflow_sdk/worktrunk.py` — change `branch_name` import**

```python
# devflow_sdk/worktrunk.py — change line:
from devflow_sdk.branch_name import parse_branch
# to:
from devflow_sdk.core.branch_name import parse_branch
```

- [ ] **Step 3: Update `devflow_sdk/plugin/plugin_loader_impl.py` — change `prompts` import**

```python
# devflow_sdk/plugin/plugin_loader_impl.py — change line:
from devflow_sdk.prompts import select
# to:
from devflow_sdk.core.prompts import select
```

- [ ] **Step 4: Update SDK test imports to use new paths**

In each test file, replace the old SDK path with the new one:
- `tests/test_branch_name.py`: `from devflow_sdk.branch_name import` → `from devflow_sdk.core.branch_name import`
- `tests/test_cost.py`: `from devflow_sdk.cost import` → `from devflow_sdk.core.cost import`
- `tests/test_prompts.py`: `from devflow_sdk.prompts import` → `from devflow_sdk.core.prompts import`
- `tests/test_shell_function_check.py`: `from devflow_sdk.shell_function_check import` → `from devflow_sdk.core.shell_function_check import`

- [ ] **Step 5: Delete the old root-level files**

```bash
rm devflow_sdk/branch_name.py devflow_sdk/cost.py \
   devflow_sdk/prompts.py devflow_sdk/shell_function_check.py
```

- [ ] **Step 6: Run SDK tests**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add devflow_sdk/core/ devflow_sdk/worktrunk.py \
        devflow_sdk/plugin/plugin_loader_impl.py devflow-sdk/tests/
git commit -m "refactor: move leaf core modules to devflow_sdk/core/"
```

---

### Task 3: Move `summary.py` to `core/`

`summary.py` depends on `cost.py` (already moved in Task 2). Move it and update its internal import.

**Files:**
- Create: `devflow_sdk/core/summary.py`
- Modify: `devflow_sdk/core/summary.py` — update `cost` import
- Modify: `devflow-sdk/tests/test_summary.py`
- Delete: `devflow_sdk/summary.py`

**Interfaces:**
- Consumes: `devflow_sdk.core.cost.CostAccumulator`, `accumulator`
- Produces: `devflow_sdk.core.summary.Summary`, `summary`

- [ ] **Step 1: Copy `summary.py` to `core/` and update its import**

```python
# devflow_sdk/core/summary.py — change:
from devflow_sdk.cost import CostAccumulator, accumulator as _shared_accumulator
# to:
from devflow_sdk.core.cost import CostAccumulator, accumulator as _shared_accumulator
```

- [ ] **Step 2: Update `tests/test_summary.py` imports**

```python
# Change:
from devflow_sdk.summary import ...
# to:
from devflow_sdk.core.summary import ...
```

- [ ] **Step 3: Delete old `devflow_sdk/summary.py`**

```bash
rm devflow_sdk/summary.py
```

- [ ] **Step 4: Run SDK tests**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add devflow_sdk/core/summary.py devflow_sdk/summary.py devflow-sdk/tests/test_summary.py
git commit -m "refactor: move summary to devflow_sdk/core/"
```

---

### Task 4: Move `config/` to `core/config/`

`config/` is a full sub-package. Move it wholesale. Update `ai.py` (which imports from it) and all config-related SDK tests.

**Files:**
- Create: `devflow_sdk/core/config/` ← entire `devflow_sdk/config/` tree
- Modify: `devflow_sdk/ai.py` — update config import
- Modify: `devflow-sdk/tests/test_config.py`, `test_config_io.py`, `test_wizard.py`, `test_wizard_draft_pr.py`, `test_wizard_global_steps.py`, `test_model_discovery.py`
- Delete: `devflow_sdk/config/` (entire directory)

**Interfaces:**
- Produces: `devflow_sdk.core.config` (same API as `devflow_sdk.config`)

- [ ] **Step 1: Copy entire `config/` tree into `core/`**

```bash
cp -r devflow_sdk/config devflow_sdk/core/config
```

- [ ] **Step 2: Update all internal imports within `core/config/` that reference sibling SDK modules**

Check each file under `devflow_sdk/core/config/` for `from devflow_sdk.` imports and update to `devflow_sdk.core.` where applicable. Run:

```bash
grep -rn "from devflow_sdk\." devflow_sdk/core/config/
```

Update any found SDK imports to use `devflow_sdk.core.*` paths.

- [ ] **Step 3: Update `devflow_sdk/ai.py` — change config import**

```python
# devflow_sdk/ai.py — change:
from devflow_sdk.config import load_config
# to:
from devflow_sdk.core.config import load_config
```

- [ ] **Step 4: Update SDK test imports for config tests**

In each config test file, replace `from devflow_sdk.config` → `from devflow_sdk.core.config`:
- `tests/test_config.py`
- `tests/test_config_io.py`
- `tests/test_wizard.py`
- `tests/test_wizard_draft_pr.py`
- `tests/test_wizard_global_steps.py`
- `tests/test_model_discovery.py`

- [ ] **Step 5: Delete old `devflow_sdk/config/`**

```bash
rm -rf devflow_sdk/config
```

- [ ] **Step 6: Run SDK tests**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

- [ ] **Step 7: Commit**

```bash
git add devflow_sdk/core/config devflow_sdk/config devflow_sdk/ai.py devflow-sdk/tests/
git commit -m "refactor: move config/ to devflow_sdk/core/config/"
```

---

### Task 5: Move `ai/` to `core/ai/`

`ai.py` becomes `core/ai/__init__.py`. `ai_providers/` becomes `core/ai/providers/`. Update all internal imports in the new files.

**Files:**
- Create: `devflow_sdk/core/ai/__init__.py` ← content of `devflow_sdk/ai.py`
- Create: `devflow_sdk/core/ai/providers/` ← from `devflow_sdk/ai_providers/`
- Modify: `devflow_sdk/core/ai/__init__.py` — update imports
- Modify: `devflow-sdk/tests/test_ai.py`, `test_ai_providers.py`
- Delete: `devflow_sdk/ai.py`, `devflow_sdk/ai_providers/`

**Interfaces:**
- Produces: `devflow_sdk.core.ai.run_ai_prompt`, `launch_interactive_session`, `configured_provider_display_name`, `AiResult`

- [ ] **Step 1: Copy `ai.py` content to `core/ai/__init__.py` and update its imports**

```python
# devflow_sdk/core/ai/__init__.py — update these imports:
from devflow_sdk.ai_providers import get_provider      →  from devflow_sdk.core.ai.providers import get_provider
from devflow_sdk.ai_providers.base import AiResult     →  from devflow_sdk.core.ai.providers.base import AiResult
from devflow_sdk.config import load_config             →  from devflow_sdk.core.config import load_config
from devflow_sdk.cost import accumulator               →  from devflow_sdk.core.cost import accumulator
```

- [ ] **Step 2: Copy `ai_providers/` to `core/ai/providers/`**

```bash
cp -r devflow_sdk/ai_providers devflow_sdk/core/ai/providers
```

Check for any `from devflow_sdk.` imports inside `core/ai/providers/` and update them to `devflow_sdk.core.*`.

- [ ] **Step 3: Update test imports**

```python
# tests/test_ai.py — replace:
from devflow_sdk.ai import ...  →  from devflow_sdk.core.ai import ...

# tests/test_ai_providers.py — replace:
from devflow_sdk.ai_providers import ...  →  from devflow_sdk.core.ai.providers import ...
```

- [ ] **Step 4: Delete old files**

```bash
rm devflow_sdk/ai.py
rm -rf devflow_sdk/ai_providers
```

- [ ] **Step 5: Run SDK tests**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add devflow_sdk/core/ai devflow_sdk/ai.py devflow_sdk/ai_providers devflow-sdk/tests/
git commit -m "refactor: move ai/ to devflow_sdk/core/ai/"
```

---

### Task 6: Create `core/git/` package

This task has the most new code. It splits `worktrunk.py` into two files and ingests three modules from tool directories.

**Files:**
- Create: `devflow_sdk/core/git/worktree.py`
- Create: `devflow_sdk/core/git/_worktrunk.py`
- Create: `devflow_sdk/core/git/git_ops.py` ← from `squash-commits/git_ops.py`
- Create: `devflow_sdk/core/git/merge_check.py` ← from `finish-issue/merge_check.py`
- Create: `devflow_sdk/core/git/shell_state.py` ← merged from `finish-issue/shell_state.py` + `start-issue/worktree.py`
- Modify: `devflow_sdk/core/git/__init__.py`
- Create: `devflow-sdk/tests/test_worktree.py` ← replaces `test_worktrunk.py` + `start-issue/tests/test_worktree.py`
- Create: `devflow-sdk/tests/test_git_ops.py` ← from `squash-commits/tests/test_git_ops.py`
- Create: `devflow-sdk/tests/test_merge_check.py` ← from `finish-issue/tests/test_merge_check.py`
- Create: `devflow-sdk/tests/test_shell_state.py` ← from `finish-issue/tests/test_shell_state.py`
- Delete: `devflow_sdk/worktrunk.py`
- Delete: `devflow-sdk/tests/test_worktrunk.py`

**Interfaces:**
- Produces:
  - `devflow_sdk.core.git.worktree.create_worktree(branch: str) -> str | None`
  - `devflow_sdk.core.git.worktree.get_repo_root() -> str`
  - `devflow_sdk.core.git.worktree.list_worktrees() -> list`
  - `devflow_sdk.core.git.worktree.query_worktrees() -> list | None`
  - `devflow_sdk.core.git.worktree.is_dirty(path: str) -> bool`
  - `devflow_sdk.core.git.check_worktrunk() -> None` (re-exported from `_worktrunk`)
  - `devflow_sdk.core.git.shell_state._persist_start_branch_for_shell(branch: str) -> None`
  - `devflow_sdk.core.git.shell_state._persist_branch_for_shell(branch: str) -> bool`

- [ ] **Step 1: Create `core/git/_worktrunk.py`**

Extract the worktrunk-specific content from `devflow_sdk/worktrunk.py`:

```python
# devflow_sdk/core/git/_worktrunk.py
import subprocess
import sys

WORKTRUNK_INSTALL_HINT = (
    "ERROR: worktrunk (wt) not found. Install it with:\n"
    "  brew install worktrunk\n"
    "Then set up shell integration: wt config shell install"
)


def check_worktrunk() -> None:
    """Exit 1 with an install hint if the wt CLI is not available."""
    try:
        subprocess.run(["wt", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print(WORKTRUNK_INSTALL_HINT, file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 2: Create `core/git/worktree.py`**

Merge content from `devflow_sdk/worktrunk.py` (all functions except `check_worktrunk`) and `devflow/start-issue/worktree.py` (all functions except `_persist_branch_for_shell`). Update imports to `devflow_sdk.core.*`:

```python
# devflow_sdk/core/git/worktree.py
import json
import os
import subprocess
import sys

from devflow_sdk.core.branch_name import parse_branch
from devflow_sdk.core.git._worktrunk import check_worktrunk  # noqa: F401 — available for re-export
from devflow_sdk.core.prompts import confirm, select, Choice


def query_worktrees() -> list | None:
    """Return parsed wt list --format json output, or None on any failure."""
    try:
        result = subprocess.run(
            ["wt", "list", "--format", "json"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def list_worktrees() -> list:
    """Return the parsed wt list --format json payload, or exit 1 on failure."""
    from devflow_sdk.core.git._worktrunk import WORKTRUNK_INSTALL_HINT
    try:
        result = subprocess.run(
            ["wt", "list", "--format", "json"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        print(WORKTRUNK_INSTALL_HINT, file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0:
        print(f"ERROR: 'wt list' failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"ERROR: 'wt list' returned invalid JSON:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)


def is_dirty(path: str) -> bool:
    """Return True if the worktree at path has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True,
        )
    except OSError:
        return False
    return bool(result.stdout.strip())


def get_repo_root() -> str:
    """Return the root of the main worktree (not necessarily cwd)."""
    result = subprocess.run(
        ["wt", "list", "--format", "json"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        try:
            for wt in json.loads(result.stdout):
                if wt.get("is_main"):
                    return wt["path"]
        except (json.JSONDecodeError, KeyError):
            pass

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR: Not inside a git repository.", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def _find_worktree_path(branch: str) -> str | None:
    worktrees = query_worktrees()
    if worktrees is None:
        return None
    for wt in worktrees:
        if wt.get("branch") == branch:
            return wt.get("path")
    return None


def _detect_incoming_commits(branch: str) -> None:
    subprocess.run(
        ["git", "fetch", "origin", branch],
        capture_output=True, text=True,
    )
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{branch}..origin/{branch}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return
    try:
        count = int(result.stdout.strip())
    except ValueError:
        return
    if count == 0:
        return
    print(f"Remote has {count} commit(s) that '{branch}' does not have.")
    choice = select(
        "What would you like to do?",
        choices=[
            Choice("Pull latest changes", value="pull"),
            Choice("Continue without pulling", value="skip"),
        ],
    )
    if choice == "pull":
        subprocess.run(
            ["git", "fetch", "origin", f"{branch}:{branch}"],
            capture_output=True, text=True,
        )


def _branch_exists_locally(branch: str) -> bool:
    result = subprocess.run(
        ["git", "branch", "--list", branch],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git branch --list failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return bool(result.stdout.strip())


def create_worktree(branch: str) -> str | None:
    """Create or switch to a worktree for branch. Returns the worktree path."""
    if _branch_exists_locally(branch):
        _detect_incoming_commits(branch)
        print(f"Branch '{branch}' already exists.")
        if not confirm(f"Switch to existing branch '{branch}'?"):
            print("Aborted.")
            sys.exit(0)
        print(f"Switching to worktree for '{branch}'...")
        result = subprocess.run(["wt", "switch", "--no-cd", branch], text=True)
        if result.returncode != 0:
            sys.exit(1)
        return _find_worktree_path(branch)

    print(f"Creating worktree for '{branch}' (pre-start hooks may take a few minutes)...")
    result = subprocess.run(["wt", "switch", "--create", "--no-cd", branch], text=True)
    if result.returncode != 0:
        sys.exit(1)
    return _find_worktree_path(branch)
```

- [ ] **Step 3: Create `core/git/shell_state.py`**

Merge `finish-issue/shell_state.py` (all five functions) and add `_persist_start_branch_for_shell` from `start-issue/worktree.py` (renamed to avoid collision):

```python
# devflow_sdk/core/git/shell_state.py
import os
import sys


def _persist_start_branch_for_shell(branch: str) -> None:
    """Write new branch to ~/.start-issue-branch for shell integration."""
    branch_file = os.path.join(os.path.expanduser("~"), ".start-issue-branch")
    try:
        with open(branch_file, "w") as f:
            f.write(branch)
    except OSError as e:
        print(
            f"WARNING: Could not persist branch name for shell: {e}\n"
            "The worktree was created successfully, but shell integration will not "
            "switch to it automatically.",
            file=sys.stderr,
        )


def _persist_branch_for_shell(branch: str) -> bool:
    """Write main branch to ~/.finish-issue-branch for shell integration."""
    branch_file = os.path.join(os.path.expanduser("~"), ".finish-issue-branch")
    try:
        with open(branch_file, "w") as f:
            f.write(branch)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist branch name for shell: {e}\n"
            "The worktree was removed successfully, but shell integration will not "
            "switch back to the main branch automatically.",
            file=sys.stderr,
        )
        return False


def _persist_worktree_for_shell(worktree_name: str) -> bool:
    remove_file = os.path.join(os.path.expanduser("~"), ".finish-issue-remove")
    try:
        with open(remove_file, "w") as f:
            f.write(worktree_name)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist worktree name for shell: {e}\n"
            f"Run 'wt remove {worktree_name}' manually.",
            file=sys.stderr,
        )
        return False


def _persist_force_for_shell() -> bool:
    force_file = os.path.join(os.path.expanduser("~"), ".finish-issue-force")
    try:
        open(force_file, "w").close()
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist force-remove flag for shell: {e}\n"
            "Pre-cleaning uncommitted changes before 'wt remove' will be skipped.",
            file=sys.stderr,
        )
        return False


def _persist_worktree_path_for_shell(path: str) -> bool:
    path_file = os.path.join(os.path.expanduser("~"), ".finish-issue-worktree-path")
    try:
        with open(path_file, "w") as f:
            f.write(path)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not persist worktree path for shell: {e}\n"
            "Pre-cleaning uncommitted changes before 'wt remove' will be skipped.",
            file=sys.stderr,
        )
        return False


def _clear_force_marker_for_shell() -> bool:
    force_file = os.path.join(os.path.expanduser("~"), ".finish-issue-force")
    path_file = os.path.join(os.path.expanduser("~"), ".finish-issue-worktree-path")
    try:
        for f in (force_file, path_file):
            if os.path.exists(f):
                os.remove(f)
        return True
    except OSError as e:
        print(
            f"WARNING: Could not clear stale force-remove marker for shell: {e}",
            file=sys.stderr,
        )
        return False
```

- [ ] **Step 4: Copy `git_ops.py` and `merge_check.py` (content unchanged)**

```bash
cp devflow/squash-commits/git_ops.py devflow_sdk/core/git/git_ops.py
cp devflow/finish-issue/merge_check.py devflow_sdk/core/git/merge_check.py
```

Neither file imports from the SDK — no import updates needed.

- [ ] **Step 5: Update `core/git/__init__.py`**

```python
# devflow_sdk/core/git/__init__.py
from . import worktree
from . import git_ops
from . import merge_check
from . import shell_state
from ._worktrunk import check_worktrunk

__all__ = ["worktree", "git_ops", "merge_check", "shell_state", "check_worktrunk"]
```

- [ ] **Step 6: Write `devflow-sdk/tests/test_worktree.py`**

Merge coverage from `test_worktrunk.py` (updating import paths) and the worktree create logic. The `find_matching_worktrees` tests move to `test_workspace.py` in Task 9.

```python
# devflow-sdk/tests/test_worktree.py
import json
from unittest.mock import patch, MagicMock
import pytest

from devflow_sdk.core.git.worktree import (
    query_worktrees, list_worktrees, is_dirty, get_repo_root,
)
from devflow_sdk.core.git import check_worktrunk


def test_query_worktrees_returns_parsed_json():
    fake_output = json.dumps([{"branch": "main", "is_main": True}])
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
        result = query_worktrees()
    assert result == [{"branch": "main", "is_main": True}]


def test_query_worktrees_returns_none_on_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = query_worktrees()
    assert result is None


def test_is_dirty_true_when_porcelain_has_output():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=" M somefile.py\n")
        assert is_dirty("/some/path") is True


def test_is_dirty_false_when_clean():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert is_dirty("/some/path") is False


def test_check_worktrunk_exits_when_wt_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SystemExit):
            check_worktrunk()
```

- [ ] **Step 7: Copy and update tool test files to `devflow-sdk/tests/`**

Copy `squash-commits/tests/test_git_ops.py`, `finish-issue/tests/test_merge_check.py`, `finish-issue/tests/test_shell_state.py` into `devflow-sdk/tests/`. Update their import paths:
- `from git_ops import ...` → `from devflow_sdk.core.git.git_ops import ...`
- `from merge_check import ...` → `from devflow_sdk.core.git.merge_check import ...`
- `from shell_state import ...` → `from devflow_sdk.core.git.shell_state import ...`

- [ ] **Step 8: Delete old `worktrunk.py` and `test_worktrunk.py`**

```bash
rm devflow_sdk/worktrunk.py
rm devflow-sdk/tests/test_worktrunk.py
```

- [ ] **Step 9: Run SDK tests**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

- [ ] **Step 10: Commit**

```bash
git add devflow_sdk/core/git/ devflow_sdk/worktrunk.py \
        devflow-sdk/tests/ devflow/squash-commits/tests/ devflow/finish-issue/tests/
git commit -m "refactor: create core/git/ package; split worktrunk into worktree + _worktrunk"
```

---

### Task 7: Move `plugin/` to `core/plugin/`

Move the plugin sub-package, rename `draft_pr_plugin.py` → `contracts.py`, write the stable public API `__init__.py`, delete the four root shims.

**Files:**
- Create: `devflow_sdk/core/plugin/contracts.py` ← from `devflow_sdk/plugin/draft_pr_plugin.py`
- Create: `devflow_sdk/core/plugin/plugin_base.py` ← from `devflow_sdk/plugin/plugin_base.py`
- Create: `devflow_sdk/core/plugin/plugin_loader.py` ← from `devflow_sdk/plugin/plugin_loader.py`
- Create: `devflow_sdk/core/plugin/plugin_loader_impl.py` ← from `devflow_sdk/plugin/plugin_loader_impl.py`; update imports
- Create: `devflow_sdk/core/plugin/plugin_registry.py` ← from `devflow_sdk/plugin/plugin_registry.py`
- Modify: `devflow_sdk/core/plugin/__init__.py` ← write stable public API
- Create: `devflow-sdk/tests/test_plugin_public_api.py`
- Modify: `devflow-sdk/tests/test_plugin_base.py`, `test_plugin_loader.py`, `test_plugin_loader_impl.py`, `test_plugin_registry.py`, `test_draft_pr_plugin.py`
- Delete: `devflow_sdk/plugin/` (entire old directory)
- Delete: `devflow_sdk/plugin_base.py`, `plugin_loader.py`, `plugin_registry.py`, `draft_pr_plugin.py` (root shims)

**Interfaces:**
- Produces: `devflow_sdk.core.plugin.{PluginBase, DraftPrPlugin, PluginLoader, PluginLoaderBase, PluginEntry, select_plugin, register, unregister, list_plugins, discover}`

- [ ] **Step 1: Copy plugin files into `core/plugin/` with renames and import updates**

```bash
cp devflow_sdk/plugin/plugin_base.py     devflow_sdk/core/plugin/plugin_base.py
cp devflow_sdk/plugin/plugin_registry.py devflow_sdk/core/plugin/plugin_registry.py
cp devflow_sdk/plugin/plugin_loader.py   devflow_sdk/core/plugin/plugin_loader.py
cp devflow_sdk/plugin/draft_pr_plugin.py devflow_sdk/core/plugin/contracts.py
cp devflow_sdk/plugin/plugin_loader_impl.py devflow_sdk/core/plugin/plugin_loader_impl.py
```

- [ ] **Step 2: Update imports inside the copied files**

`devflow_sdk/core/plugin/contracts.py`:
```python
# Change:
from devflow_sdk.plugin.plugin_base import PluginBase
# to:
from devflow_sdk.core.plugin.plugin_base import PluginBase
```

`devflow_sdk/core/plugin/plugin_loader.py`:
```python
# Change:
from devflow_sdk.plugin.plugin_registry import PluginEntry
# to:
from devflow_sdk.core.plugin.plugin_registry import PluginEntry
```

`devflow_sdk/core/plugin/plugin_loader_impl.py`:
```python
# Change:
from devflow_sdk.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin.plugin_registry import PluginEntry
from devflow_sdk.prompts import select           # already updated in Task 2 — verify it reads:
# to:
from devflow_sdk.core.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.core.plugin.plugin_registry import PluginEntry
from devflow_sdk.core.prompts import select
```

- [ ] **Step 3: Write the stable public API `__init__.py`**

```python
# devflow_sdk/core/plugin/__init__.py
from devflow_sdk.core.plugin.plugin_base import PluginBase
from devflow_sdk.core.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.core.plugin.plugin_loader_impl import (
    PluginLoader,
    select_plugin,
    register,
    unregister,
    list_plugins,
    discover,
)
from devflow_sdk.core.plugin.plugin_registry import PluginEntry
from devflow_sdk.core.plugin.contracts import DraftPrPlugin

__all__ = [
    "PluginBase",
    "PluginLoaderBase",
    "PluginLoader",
    "PluginEntry",
    "DraftPrPlugin",
    "select_plugin",
    "register",
    "unregister",
    "list_plugins",
    "discover",
]
```

- [ ] **Step 4: Write `test_plugin_public_api.py`** (write this BEFORE deleting old paths)

```python
# devflow-sdk/tests/test_plugin_public_api.py
"""Smoke test: every symbol in core.plugin.__all__ must be importable.
This test fails at import-time if any re-export in __init__.py is broken."""


def test_all_public_symbols_importable():
    from devflow_sdk.core.plugin import (
        PluginBase,
        PluginLoaderBase,
        PluginLoader,
        PluginEntry,
        DraftPrPlugin,
        select_plugin,
        register,
        unregister,
        list_plugins,
        discover,
    )
    assert PluginBase is not None
    assert DraftPrPlugin is not None
    assert select_plugin is not None
```

- [ ] **Step 5: Run the new smoke test to verify it passes**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_public_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Update existing plugin test imports**

In each plugin test file, update imports from `devflow_sdk.plugin.*` and `devflow_sdk.draft_pr_plugin` → `devflow_sdk.core.plugin.*`:
- `tests/test_plugin_base.py`
- `tests/test_plugin_loader.py`
- `tests/test_plugin_loader_impl.py`
- `tests/test_plugin_registry.py`
- `tests/test_draft_pr_plugin.py` → rename to `tests/test_contracts.py`; update import to `from devflow_sdk.core.plugin.contracts import DraftPrPlugin`

- [ ] **Step 7: Delete old `plugin/` directory and root shims**

```bash
rm -rf devflow_sdk/plugin
rm devflow_sdk/plugin_base.py devflow_sdk/plugin_loader.py \
   devflow_sdk/plugin_registry.py devflow_sdk/draft_pr_plugin.py
```

- [ ] **Step 8: Run full SDK test suite**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

- [ ] **Step 9: Commit**

```bash
git add devflow_sdk/core/plugin/ devflow_sdk/plugin/ \
        devflow_sdk/plugin_base.py devflow_sdk/plugin_loader.py \
        devflow_sdk/plugin_registry.py devflow_sdk/draft_pr_plugin.py \
        devflow-sdk/tests/
git commit -m "refactor: move plugin/ to core/plugin/; rename draft_pr_plugin → contracts; add public API smoke test"
```

---

### Task 8: Create `domain/issue/`

Move `ticket_info.py` and `issue_context.py` into the issue domain. Neither imports from the SDK.

**Files:**
- Create: `devflow_sdk/domain/issue/ticket_info.py` ← from `devflow_sdk/ticket_info.py`
- Create: `devflow_sdk/domain/issue/issue_context.py` ← from `devflow_sdk/issue_context.py`
- Modify: `devflow_sdk/domain/issue/__init__.py`
- Modify: `devflow-sdk/tests/test_ticket_info.py`, `test_issue_context.py`
- Delete: `devflow_sdk/ticket_info.py`, `devflow_sdk/issue_context.py`

**Interfaces:**
- Produces: `devflow_sdk.domain.issue.{fetch, check_gh, check_acli, is_jira_key, get_ticket_context, format_ticket_context, write_issue_context, read_issue_context, remove_issue_context}`

- [ ] **Step 1: Copy files (content unchanged)**

```bash
cp devflow_sdk/ticket_info.py devflow_sdk/domain/issue/ticket_info.py
cp devflow_sdk/issue_context.py devflow_sdk/domain/issue/issue_context.py
```

- [ ] **Step 2: Write `domain/issue/__init__.py`**

```python
# devflow_sdk/domain/issue/__init__.py
from devflow_sdk.domain.issue.ticket_info import (
    fetch,
    check_gh,
    check_acli,
    is_jira_key,
    get_ticket_context,
    format_ticket_context,
)
from devflow_sdk.domain.issue.issue_context import (
    write_issue_context,
    read_issue_context,
    remove_issue_context,
)

__all__ = [
    "fetch", "check_gh", "check_acli", "is_jira_key",
    "get_ticket_context", "format_ticket_context",
    "write_issue_context", "read_issue_context", "remove_issue_context",
]
```

- [ ] **Step 3: Update test imports**

```python
# tests/test_ticket_info.py — replace:
from devflow_sdk.ticket_info import ...
# with:
from devflow_sdk.domain.issue.ticket_info import ...
# OR:
from devflow_sdk.domain.issue import ...

# tests/test_issue_context.py — replace:
from devflow_sdk.issue_context import ...
# with:
from devflow_sdk.domain.issue.issue_context import ...
# OR:
from devflow_sdk.domain.issue import ...
```

- [ ] **Step 4: Delete old root-level files**

```bash
rm devflow_sdk/ticket_info.py devflow_sdk/issue_context.py
```

- [ ] **Step 5: Run SDK tests**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add devflow_sdk/domain/issue/ devflow_sdk/ticket_info.py \
        devflow_sdk/issue_context.py devflow-sdk/tests/
git commit -m "refactor: create domain/issue/ from ticket_info and issue_context"
```

---

### Task 9: Create `domain/workspace/`

New business logic. TDD: write failing test first, then implement.

**Files:**
- Modify: `devflow_sdk/domain/workspace/__init__.py`
- Create: `devflow-sdk/tests/test_workspace.py`

**Interfaces:**
- Consumes: `devflow_sdk.core.git.worktree.{list_worktrees, create_worktree}`, `devflow_sdk.core.git.check_worktrunk`, `devflow_sdk.core.branch_name.parse_branch`
- Produces:
  - `check_manager() -> None`
  - `create(branch: str) -> str | None`
  - `find_for_issue(issue_id: str, source: str) -> list[dict]`
  - `list_workspaces() -> list`

- [ ] **Step 1: Write failing tests**

```python
# devflow-sdk/tests/test_workspace.py
from unittest.mock import patch
import pytest
from devflow_sdk.domain.workspace import find_for_issue, list_workspaces


FAKE_WORKTREES = [
    {"is_main": True, "branch": "main", "path": "/repo"},
    {"is_main": False, "branch": "feat-gh42-my-feature", "path": "/repo/feat-gh42"},
    {"is_main": False, "branch": "fix-gh99-other-bug", "path": "/repo/fix-gh99"},
    {"is_main": False, "branch": "fix-VDP-123-jira-issue", "path": "/repo/fix-VDP-123"},
]


def test_find_for_issue_github_matches():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("42", "github")
    assert len(result) == 1
    assert result[0]["branch"] == "feat-gh42-my-feature"
    assert result[0]["path"] == "/repo/feat-gh42"


def test_find_for_issue_jira_matches():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("VDP-123", "jira")
    assert len(result) == 1
    assert result[0]["branch"] == "fix-VDP-123-jira-issue"


def test_find_for_issue_no_match_returns_empty():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("999", "github")
    assert result == []


def test_find_for_issue_excludes_main_worktree():
    worktrees = [{"is_main": True, "branch": "main", "path": "/repo"}]
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=worktrees):
        result = find_for_issue("42", "github")
    assert result == []


def test_find_for_issue_case_insensitive():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = find_for_issue("vdp-123", "jira")
    assert len(result) == 1


def test_list_workspaces_excludes_main():
    with patch("devflow_sdk.domain.workspace.list_worktrees", return_value=FAKE_WORKTREES):
        result = list_workspaces()
    assert all(not wt.get("is_main") for wt in result)
    assert len(result) == 3
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_workspace.py -v
```

Expected: ImportError or AttributeError (module exists but functions not yet defined).

- [ ] **Step 3: Implement `domain/workspace/__init__.py`**

```python
# devflow_sdk/domain/workspace/__init__.py
from devflow_sdk.core.branch_name import parse_branch
from devflow_sdk.core.git import check_worktrunk
from devflow_sdk.core.git.worktree import create_worktree, list_worktrees


def check_manager() -> None:
    """Exit with install hint if the workspace manager (wt) is not available."""
    check_worktrunk()


def create(branch: str) -> str | None:
    """Create or switch to a worktree for branch. Returns the worktree path."""
    return create_worktree(branch)


def find_for_issue(issue_id: str, source: str) -> list[dict]:
    """Return worktrees whose branch matches issue_id and source.

    source is 'github' or 'jira'. Excludes the main worktree.
    """
    worktrees = list_worktrees()
    matches = []
    for wt in worktrees:
        if wt.get("is_main"):
            continue
        branch = wt.get("branch")
        parsed = parse_branch(branch)
        if (parsed
                and parsed["source"] == source
                and parsed["id"].lower() == str(issue_id).lower()):
            matches.append({"branch": branch, "path": wt.get("path")})
    return matches


def list_workspaces() -> list:
    """Return all non-main worktrees."""
    return [wt for wt in list_worktrees() if not wt.get("is_main")]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_workspace.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Run full SDK test suite**

```bash
cd devflow-sdk && python -m pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add devflow_sdk/domain/workspace/__init__.py devflow-sdk/tests/test_workspace.py
git commit -m "feat: create domain/workspace/ with find_for_issue and workspace lifecycle"
```

---

### Task 10: Migrate `draft-pr` tool

Remove `plugin-manager/`, remove local `config.py` shim, update all SDK imports in `draft-pr.py`.

**Files:**
- Modify: `devflow/draft-pr/draft-pr.py`
- Delete: `devflow/draft-pr/config.py`
- Delete: `devflow/plugin-manager/` (entire directory)
- Modify: `devflow/draft-pr/tests/test_draft_pr.py` and related test files

**Interfaces:**
- Consumes: `devflow_sdk.core.plugin.{DraftPrPlugin, select_plugin}`, `devflow_sdk.core.ai.run_ai_prompt`, `devflow_sdk.core.config.{load_config, load_tool_config}`, `devflow_sdk.core.prompts.{select, prompt}`, `devflow_sdk.core.config.wizard.tools.draft_pr.{DraftPrConfig, resolve_plugin}`

- [ ] **Step 1: Update `draft-pr/draft-pr.py` imports**

Remove these lines:
```python
PLUGIN_MANAGER_DIR = os.path.join(REPO_ROOT, "plugin-manager")
sys.path.insert(0, PLUGIN_MANAGER_DIR)
from plugin_loader import select_plugin
from config import DraftPrConfig, resolve_plugin
from devflow_sdk.plugin import DraftPrPlugin
```

Replace with:
```python
from devflow_sdk.core.plugin import DraftPrPlugin, select_plugin
from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrConfig, resolve_plugin
```

Also update remaining SDK imports in `draft-pr.py`:
```python
from devflow_sdk.ai import run_ai_prompt          →  from devflow_sdk.core.ai import run_ai_prompt
from devflow_sdk.prompts import select, prompt    →  from devflow_sdk.core.prompts import select, prompt
from devflow_sdk.config import load_config, load_tool_config  →  from devflow_sdk.core.config import load_config, load_tool_config
```

- [ ] **Step 2: Update test imports in `draft-pr/tests/`**

Grep for `devflow_sdk` imports and update to `devflow_sdk.core.*` or `devflow_sdk.domain.*` as appropriate:
```bash
grep -rn "from devflow_sdk" devflow/draft-pr/tests/
```

- [ ] **Step 3: Delete `config.py` shim and `plugin-manager/`**

```bash
rm devflow/draft-pr/config.py
rm -rf devflow/plugin-manager
```

- [ ] **Step 4: Run `draft-pr` tests**

```bash
cd devflow/draft-pr && python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add devflow/draft-pr/ devflow/plugin-manager/
git commit -m "refactor: migrate draft-pr to devflow_sdk.core.*; remove plugin-manager"
```

---

### Task 11: Migrate `start-issue` tool

Delete local `worktree.py` (absorbed into SDK). Update all SDK imports.

**Files:**
- Modify: `devflow/start-issue/start-issue.py`
- Delete: `devflow/start-issue/worktree.py`
- Delete: `devflow/start-issue/tests/test_worktree.py` (merged into SDK tests in Task 6)
- Modify: `devflow/start-issue/tests/test_start_issue.py` and related test files

**Interfaces:**
- Consumes: `devflow_sdk.domain.workspace.{check_manager, create}`, `devflow_sdk.core.git.worktree.get_repo_root`, `devflow_sdk.core.git.shell_state._persist_start_branch_for_shell`, `devflow_sdk.domain.issue.{fetch, write_issue_context}`, `devflow_sdk.core.branch_name.{make_branch, infer_type, VALID_TYPES}`, `devflow_sdk.core.ai.run_ai_prompt`, `devflow_sdk.core.summary.summary`, `devflow_sdk.core.shell_function_check.check_shell_function`

- [ ] **Step 1: Update `start-issue/start-issue.py` imports**

Remove:
```python
from worktree import check_worktrunk, create_worktree, get_repo_root, _persist_branch_for_shell
```

Replace with:
```python
from devflow_sdk.domain.workspace import check_manager, create as create_workspace
from devflow_sdk.core.git.worktree import get_repo_root
from devflow_sdk.core.git.shell_state import _persist_start_branch_for_shell
```

Update all other old SDK imports:
```python
from devflow_sdk.ticket_info import fetch          →  from devflow_sdk.domain.issue import fetch
from devflow_sdk.branch_name import make_branch, infer_type, VALID_TYPES  →  from devflow_sdk.core.branch_name import make_branch, infer_type, VALID_TYPES
from devflow_sdk.issue_context import write_issue_context  →  from devflow_sdk.domain.issue import write_issue_context
from devflow_sdk.shell_function_check import check_shell_function  →  from devflow_sdk.core.shell_function_check import check_shell_function
from devflow_sdk.summary import summary            →  from devflow_sdk.core.summary import summary
from devflow_sdk.ai import run_ai_prompt           →  from devflow_sdk.core.ai import run_ai_prompt
```

Update call sites in `start-issue.py`:
```python
check_worktrunk()          →  check_manager()
create_worktree(branch)    →  create_workspace(branch)
_persist_branch_for_shell(branch)  →  _persist_start_branch_for_shell(branch)
```

- [ ] **Step 2: Update `start-issue/tests/` imports**

```bash
grep -rn "from devflow_sdk\|from worktree\|import worktree" devflow/start-issue/tests/
```

Update all found imports to new paths.

- [ ] **Step 3: Delete local `worktree.py` and its test file**

```bash
rm devflow/start-issue/worktree.py
rm devflow/start-issue/tests/test_worktree.py
```

- [ ] **Step 4: Run `start-issue` tests**

```bash
cd devflow/start-issue && python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add devflow/start-issue/
git commit -m "refactor: migrate start-issue to devflow_sdk.core.* and domain.workspace"
```

---

### Task 12: Migrate `finish-issue` tool

Delete local `shell_state.py` and `merge_check.py` (both now in SDK). Update all imports.

**Files:**
- Modify: `devflow/finish-issue/finish-issue.py`
- Delete: `devflow/finish-issue/shell_state.py`
- Delete: `devflow/finish-issue/merge_check.py`
- Delete: `devflow/finish-issue/tests/test_shell_state.py` (merged to SDK in Task 6)
- Delete: `devflow/finish-issue/tests/test_merge_check.py` (merged to SDK in Task 6)
- Modify: `devflow/finish-issue/tests/test_finish_issue.py`

**Interfaces:**
- Consumes: `devflow_sdk.core.git.shell_state.*`, `devflow_sdk.core.git.merge_check.{get_main_branch, is_merged}`, `devflow_sdk.domain.workspace.{check_manager, find_for_issue}`, `devflow_sdk.core.git.worktree.{list_worktrees, is_dirty}`, `devflow_sdk.domain.issue.{fetch, read_issue_context, remove_issue_context}`

- [ ] **Step 1: Update `finish-issue/finish-issue.py` imports**

Remove:
```python
from shell_state import (
    _persist_branch_for_shell, _persist_worktree_for_shell,
    _persist_force_for_shell, _persist_worktree_path_for_shell,
    _clear_force_marker_for_shell,
)
from merge_check import get_main_branch, is_merged
from devflow_sdk.worktrunk import check_worktrunk, list_worktrees, find_matching_worktrees, is_dirty
```

Replace with:
```python
from devflow_sdk.core.git.shell_state import (
    _persist_branch_for_shell, _persist_worktree_for_shell,
    _persist_force_for_shell, _persist_worktree_path_for_shell,
    _clear_force_marker_for_shell,
)
from devflow_sdk.core.git.merge_check import get_main_branch, is_merged
from devflow_sdk.domain.workspace import check_manager, find_for_issue
from devflow_sdk.core.git.worktree import list_worktrees, is_dirty
```

Update remaining old SDK imports:
```python
from devflow_sdk.ticket_info import fetch              →  from devflow_sdk.domain.issue import fetch
from devflow_sdk.prompts import select, text           →  from devflow_sdk.core.prompts import select, text
from devflow_sdk.issue_context import remove_issue_context, read_issue_context  →  from devflow_sdk.domain.issue import remove_issue_context, read_issue_context
from devflow_sdk.shell_function_check import check_shell_function  →  from devflow_sdk.core.shell_function_check import check_shell_function
from devflow_sdk.worktrunk import check_worktrunk      →  (removed — use check_manager() below)
```

Update call sites:
```python
check_worktrunk()                    →  check_manager()
find_matching_worktrees(...)         →  find_for_issue(...)
```

Note: `is_merged(path, branch, main_branch)` signature is unchanged — `path` is the `repo_root` argument.

- [ ] **Step 2: Delete local files and tool test files already moved to SDK**

```bash
rm devflow/finish-issue/shell_state.py
rm devflow/finish-issue/merge_check.py
rm devflow/finish-issue/tests/test_shell_state.py
rm devflow/finish-issue/tests/test_merge_check.py
```

- [ ] **Step 3: Update remaining `finish-issue` test imports**

```bash
grep -rn "from devflow_sdk\|from shell_state\|from merge_check" devflow/finish-issue/tests/
```

- [ ] **Step 4: Run `finish-issue` tests**

```bash
cd devflow/finish-issue && python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add devflow/finish-issue/
git commit -m "refactor: migrate finish-issue to devflow_sdk.core.* and domain.workspace"
```

---

### Task 13: Migrate `squash-commits` tool

Delete local `git_ops.py` (now in SDK). Update import.

**Files:**
- Modify: `devflow/squash-commits/squash-commits.py`
- Delete: `devflow/squash-commits/git_ops.py`
- Delete: `devflow/squash-commits/tests/test_git_ops.py` (merged to SDK in Task 6)
- Modify: `devflow/squash-commits/tests/test_squash_commits.py`

**Interfaces:**
- Consumes: `devflow_sdk.core.git.git_ops` (as module), `devflow_sdk.core.ai.run_ai_prompt`, `devflow_sdk.core.summary.summary`, `devflow_sdk.core.prompts.select`

- [ ] **Step 1: Update `squash-commits/squash-commits.py` imports**

```python
# Remove:
import git_ops

# Add:
from devflow_sdk.core.git import git_ops

# Update remaining old SDK imports:
from devflow_sdk.ai import run_ai_prompt    →  from devflow_sdk.core.ai import run_ai_prompt
from devflow_sdk.summary import summary     →  from devflow_sdk.core.summary import summary
from devflow_sdk.prompts import select      →  from devflow_sdk.core.prompts import select
```

All call sites like `git_ops.current_branch()` remain unchanged since `git_ops` is still used as a module reference.

- [ ] **Step 2: Delete local `git_ops.py` and its test**

```bash
rm devflow/squash-commits/git_ops.py
rm devflow/squash-commits/tests/test_git_ops.py
```

- [ ] **Step 3: Update remaining test imports**

```bash
grep -rn "from devflow_sdk\|import git_ops" devflow/squash-commits/tests/
```

- [ ] **Step 4: Run `squash-commits` tests**

```bash
cd devflow/squash-commits && python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add devflow/squash-commits/
git commit -m "refactor: migrate squash-commits to devflow_sdk.core.git.git_ops"
```

---

### Task 14: Migrate `address-pr` and `devflow-config`

No local file deletions — just import path updates.

**Files:**
- Modify: `devflow/address-pr/address-pr.py`
- Modify: `devflow/devflow-config/devflow-config.py`
- Modify: test files in each tool's `tests/`

- [ ] **Step 1: Update `address-pr/address-pr.py` imports**

```python
from devflow_sdk.summary import summary                          →  from devflow_sdk.core.summary import summary
from devflow_sdk.ticket_info import check_gh                    →  from devflow_sdk.domain.issue import check_gh
from devflow_sdk.prompts import confirm                          →  from devflow_sdk.core.prompts import confirm
from devflow_sdk.ai import configured_provider_display_name     →  from devflow_sdk.core.ai import configured_provider_display_name
```

- [ ] **Step 2: Update `devflow-config/devflow-config.py` imports**

```python
from devflow_sdk.config.io import CONFIG_PATH, load_config, load_tool_config, repair_config  →  from devflow_sdk.core.config.io import CONFIG_PATH, load_config, load_tool_config, repair_config
from devflow_sdk.config.wizard import run_wizard                                              →  from devflow_sdk.core.config.wizard import run_wizard
from devflow_sdk.config.wizard.global_steps import ModelsStep, ProviderStep                  →  from devflow_sdk.core.config.wizard.global_steps import ModelsStep, ProviderStep
from devflow_sdk.config.wizard.tools import ALL_TOOL_STEPS                                   →  from devflow_sdk.core.config.wizard.tools import ALL_TOOL_STEPS
```

- [ ] **Step 3: Update test imports in both tools**

```bash
grep -rn "from devflow_sdk" devflow/address-pr/tests/ devflow/devflow-config/tests/
```

- [ ] **Step 4: Run tests for both tools**

```bash
cd devflow/address-pr && python -m pytest tests/ -q
cd devflow/devflow-config && python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add devflow/address-pr/ devflow/devflow-config/
git commit -m "refactor: migrate address-pr and devflow-config to devflow_sdk.core.*"
```

---

### Task 15: Update external consumers

Update the plugin scaffold and the `default-format` plugin to use the new canonical import path.

**Files:**
- Modify: `devflow-plugin-scaffold/scaffold.sh`
- Modify: `devflow-plugin-scaffold/README.md`
- Modify: `devflow-plugin-scaffold/tests/test_scaffold.sh`
- Modify: `~/personal/default-format/default_format.py`

- [ ] **Step 1: Update scaffold**

In `scaffold.sh`, `README.md`, and `tests/test_scaffold.sh`, replace:
```python
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
```
with:
```python
from devflow_sdk.core.plugin import DraftPrPlugin
```

- [ ] **Step 2: Update `default-format` plugin**

```python
# ~/personal/default-format/default_format.py — change line 8:
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
# to:
from devflow_sdk.core.plugin import DraftPrPlugin
```

- [ ] **Step 3: Run scaffold tests**

```bash
bash devflow-plugin-scaffold/tests/test_scaffold.sh
```

- [ ] **Step 4: Verify `default-format` imports cleanly**

```bash
cd ~/personal/default-format && python -c "from devflow_sdk.core.plugin import DraftPrPlugin; print('OK')"
```

- [ ] **Step 5: Commit scaffold changes**

```bash
git add devflow-plugin-scaffold/
git commit -m "chore: update scaffold to use devflow_sdk.core.plugin canonical import"
```

---

### Task 16: Add `import-linter` enforcement

Add build-time enforcement of the `core` → `domain` boundary and domain independence.

**Files:**
- Modify: `devflow-sdk/pyproject.toml`
- Modify: `devflow-sdk/justfile`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `import-linter` pip package

- [ ] **Step 1: Add `import-linter` to dev dependencies in `pyproject.toml`**

In `devflow-sdk/pyproject.toml`, add `import-linter` to the dev/test dependency group (check existing pattern — it may be under `[project.optional-dependencies]` or `[dependency-groups]`):

```toml
# In the dev/test dependencies section:
"import-linter>=2.0",
```

- [ ] **Step 2: Add `import-linter` contracts to `pyproject.toml`**

```toml
[tool.importlinter]
root_package = "devflow_sdk"

[[tool.importlinter.contracts]]
name = "Core must not import from domain"
type = "forbidden"
source_modules = ["devflow_sdk.core"]
forbidden_modules = ["devflow_sdk.domain"]

[[tool.importlinter.contracts]]
name = "Domains are independent of each other"
type = "independence"
modules = [
    "devflow_sdk.domain.issue",
    "devflow_sdk.domain.workspace",
]
```

- [ ] **Step 3: Install `import-linter` and run it to confirm zero violations**

```bash
cd devflow-sdk && pip install import-linter
lint-imports
```

Expected: "All contracts kept."

- [ ] **Step 4: Add `lint-imports` recipe to `justfile`**

```makefile
# In devflow-sdk/justfile, add or extend:
lint-imports:
    lint-imports

check: test lint-imports
```

If a `check` recipe already exists, add `lint-imports` to it. Otherwise create a new `check` recipe.

- [ ] **Step 5: Add `lint-imports` step to CI**

In `.github/workflows/ci.yml`, within the SDK job, add after the `pip install` step:

```yaml
- name: Check import boundaries
  run: |
    cd devflow-sdk
    lint-imports
```

- [ ] **Step 6: Run full SDK test suite one final time**

```bash
cd devflow-sdk && python -m pytest tests/ -q && lint-imports
```

Expected: all tests pass, all contracts kept.

- [ ] **Step 7: Commit**

```bash
git add devflow-sdk/pyproject.toml devflow-sdk/justfile .github/workflows/ci.yml
git commit -m "chore: add import-linter to enforce core/domain boundary"
```

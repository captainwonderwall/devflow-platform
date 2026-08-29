# SDK Refactor — Design

**Date:** 2026-08-29

## Model Selection

- **Implementation**: Haiku (fast, cost-efficient for mechanical moves and import updates)
- **Review**: Sonnet 5 max (thorough analysis of architectural boundaries and correctness)
- Do not use Opus

---

## Overview

Refactor `devflow-sdk` to be simpler and more coherent. The SDK becomes the single source of truth for all shared responsibilities. The repository gains a strict two-zone structure — `core/` for infrastructure, `domain/` for bounded business contexts — enforced at build time with `import-linter`.

## Motivation

- Root-level shims (`plugin_base.py`, `plugin_loader.py`, `plugin_registry.py`, `draft_pr_plugin.py`) are forwarding stubs left over from a migration — confusing and misleading
- `devflow/plugin-manager/` duplicates plugin loader functionality already in the SDK
- `draft-pr` reaches into `plugin-manager/` via `sys.path` manipulation instead of importing from the SDK
- Tool-specific modules that belong in the SDK (`worktree.py`, `shell_state.py`, `merge_check.py`, `git_ops.py`) live inside individual tool directories
- No naming distinction between git worktrees (technical primitive) and workspaces (devflow domain concept)
- No structural or build-enforced boundary between infrastructure and business logic

---

## SDK Structure After Refactor

```
devflow_sdk/
├── core/
│   ├── ai/
│   │   ├── __init__.py          ← was devflow_sdk/ai.py
│   │   └── providers/           ← was devflow_sdk/ai_providers/
│   │       ├── base.py
│   │       ├── claude_provider.py
│   │       └── opencode_provider.py
│   ├── config/                  ← moved from devflow_sdk/config/ (unchanged internally)
│   ├── git/
│   │   ├── __init__.py          ← re-exports: worktree, git_ops, merge_check, shell_state
│   │   ├── worktree.py          ← PUBLIC: git worktree primitives
│   │   ├── _worktrunk.py        ← PRIVATE: wt CLI adapter
│   │   ├── git_ops.py           ← moved from squash-commits/git_ops.py
│   │   ├── merge_check.py       ← moved from finish-issue/merge_check.py
│   │   └── shell_state.py       ← moved from finish-issue/shell_state.py
│   ├── plugin/
│   │   ├── __init__.py          ← stable public API re-exports
│   │   ├── contracts.py         ← DraftPrPlugin (was plugin/draft_pr_plugin.py)
│   │   ├── plugin_base.py
│   │   ├── plugin_loader.py
│   │   ├── plugin_loader_impl.py
│   │   └── plugin_registry.py
│   ├── branch_name.py           ← moved from devflow_sdk/branch_name.py
│   ├── cost.py                  ← moved from devflow_sdk/cost.py
│   ├── prompts.py               ← moved from devflow_sdk/prompts.py
│   ├── shell_function_check.py  ← moved from devflow_sdk/shell_function_check.py
│   └── summary.py               ← moved from devflow_sdk/summary.py
└── domain/
    ├── issue/
    │   ├── __init__.py          ← re-exports public API
    │   ├── ticket_info.py       ← moved from devflow_sdk/ticket_info.py
    │   └── issue_context.py     ← moved from devflow_sdk/issue_context.py
    └── workspace/
        └── __init__.py          ← business logic; delegates to core.git internally
```

---

## Core (`devflow_sdk/core/`)

Infrastructure modules. No devflow-specific business logic. Does not import from `devflow_sdk.domain`.

### `core/ai/`

Content of `devflow_sdk/ai.py` moves to `__init__.py`. The `ai_providers/` directory moves to `providers/` inside `ai/` — the `ai_` prefix is redundant once inside the `ai/` package.

Public API (unchanged):
```python
from devflow_sdk.core.ai import run_ai_prompt, launch_interactive_session, configured_provider_display_name, AiResult
```

### `core/config/`

Moved wholesale from `devflow_sdk/config/`. Structure and content unchanged. IO, schema, and wizard sub-modules stay in place.

Public API (unchanged):
```python
from devflow_sdk.core.config import load_config, load_tool_config
```

### `core/git/`

New package. Houses all git and worktree primitives.

**`worktree.py`** (public — exported from `__init__.py`):
- `create_worktree(branch: str) -> str | None` — runs `wt add <branch>`, returns worktree path
- `get_repo_root() -> str` — `git rev-parse --show-toplevel`
- `list_worktrees() -> list` — `wt list --format json`, exits on failure
- `query_worktrees() -> list | None` — soft version, returns `None` on failure
- `is_dirty(path: str) -> bool` — `git status --porcelain` on path

**`_worktrunk.py`** (private — underscore-prefixed, not exported):
- `check_worktrunk() -> None` — exits with install hint if `wt` CLI not found
- Low-level wt command execution helpers

**`git_ops.py`** — generic git utilities; moved from `squash-commits/git_ops.py`

**`merge_check.py`** — `get_main_branch`, `is_merged`; moved from `finish-issue/merge_check.py`

**`shell_state.py`** — shell state persistence (`_persist_branch_for_shell`, `_persist_worktree_for_shell`, etc.); moved from `finish-issue/shell_state.py` and consolidated with `start-issue/worktree.py`'s copy of `_persist_branch_for_shell` (one canonical copy)

**`git/__init__.py`** re-exports `worktree` as a submodule, `check_worktrunk` from `_worktrunk` (surfaced publicly here so consumers never need to reach into the private module), and submodules `git_ops`, `merge_check`, `shell_state`:
```python
from devflow_sdk.core.git import worktree          # submodule
from devflow_sdk.core.git import check_worktrunk   # re-exported from _worktrunk
from devflow_sdk.core.git import git_ops           # submodule
from devflow_sdk.core.git.shell_state import _persist_branch_for_shell
```

### `core/plugin/`

Moved from `devflow_sdk/plugin/`. Internal structure preserved; `draft_pr_plugin.py` renamed to `contracts.py`.

**`contracts.py`** — `DraftPrPlugin` abstract base class. This is the only plugin type contract currently; future tool plugin types (`AddressPrPlugin`, etc.) are added here.

**`__init__.py`** — the stable public API surface that external plugin authors and tools import from. Explicitly re-exports all public symbols:
```python
from devflow_sdk.core.plugin.plugin_base import PluginBase
from devflow_sdk.core.plugin.contracts import DraftPrPlugin
from devflow_sdk.core.plugin.plugin_loader_impl import (
    PluginLoader, select_plugin, register, unregister, list_plugins, discover,
)
```

A test (`tests/test_plugin_public_api.py`) imports every symbol listed in `__init__.py` to catch any drift between the re-exports and the implementations.

### Flat core modules

`branch_name.py`, `cost.py`, `prompts.py`, `shell_function_check.py`, `summary.py` — moved from `devflow_sdk/` root into `devflow_sdk/core/`. Content unchanged.

`branch_name.py` is core (not domain) because `parse_branch` is used by both the workspace domain and the git core's worktree matching — it is a shared naming convention, not an issue-tracking concern.

---

## Domain (`devflow_sdk/domain/`)

Business logic bounded contexts. May import from `devflow_sdk.core`. Must not import from other domain packages.

### `domain/issue/`

Bounded context for issue-tracking integration (Jira, GitHub).

**`ticket_info.py`** — `fetch(issue_ref)`, `check_gh()`; moved from `devflow_sdk/ticket_info.py`

**`issue_context.py`** — `write_issue_context`, `read_issue_context`, `remove_issue_context`; moved from `devflow_sdk/issue_context.py`

**`__init__.py`** re-exports the public API:
```python
from devflow_sdk.domain.issue.ticket_info import fetch, check_gh
from devflow_sdk.domain.issue.issue_context import (
    write_issue_context, read_issue_context, remove_issue_context,
)
```

### `domain/workspace/`

Bounded context for the in-progress development workspace lifecycle. A workspace is a git worktree that is associated with a devflow issue. This is the devflow business concept; `core.git.worktree` is the git primitive underneath it.

The workspace domain is implemented entirely in `__init__.py` — it has no private submodules; all delegation goes to `devflow_sdk.core.git`.

**`__init__.py`** — all public API for this domain:

- `check_manager() -> None` — delegates to `core.git.check_worktrunk` (re-exported from `_worktrunk`); exits if `wt` not installed
- `create(branch: str) -> str | None` — delegates to `core.git.worktree.create_worktree()`
- `find_for_issue(issue_id: str, source: str) -> list[dict]` — calls `core.git.worktree.list_worktrees()` then matches using `core.branch_name.parse_branch()`; this is the business rule that a workspace belongs to an issue
- `list_workspaces() -> list` — lists active workspaces (delegates to `core.git.worktree.list_worktrees()`, excludes main)


---

## Deletions

### From `devflow_sdk/` root (all content moved)
- `ai.py`, `ai_providers/`
- `branch_name.py`
- `config/`
- `cost.py`
- `draft_pr_plugin.py` (shim)
- `issue_context.py`
- `plugin/`
- `plugin_base.py` (shim)
- `plugin_loader.py` (shim)
- `plugin_registry.py` (shim)
- `prompts.py`
- `shell_function_check.py`
- `summary.py`
- `ticket_info.py`
- `worktrunk.py`

### From `devflow/` (tool directories)
- `devflow/plugin-manager/` — entire directory; functionality already in SDK
- `devflow/draft-pr/config.py` — thin re-export shim; tool imports directly from SDK
- `devflow/start-issue/worktree.py` — absorbed into `core/git/worktree.py` and `domain/workspace/`
- `devflow/finish-issue/shell_state.py` — moved to `core/git/shell_state.py`
- `devflow/finish-issue/merge_check.py` — moved to `core/git/merge_check.py`
- `devflow/squash-commits/git_ops.py` — moved to `core/git/git_ops.py`

---

## Tool Import Migration

Each tool drops local module files and updates to SDK imports.

### `draft-pr/draft-pr.py`
```python
# Remove:
PLUGIN_MANAGER_DIR = os.path.join(REPO_ROOT, "plugin-manager")
sys.path.insert(0, PLUGIN_MANAGER_DIR)
from plugin_loader import select_plugin
from config import DraftPrConfig, resolve_plugin
from devflow_sdk.plugin import DraftPrPlugin

# Replace with:
from devflow_sdk.core.plugin import DraftPrPlugin, select_plugin
from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrConfig, resolve_plugin
from devflow_sdk.core.ai import run_ai_prompt
from devflow_sdk.core.prompts import select, prompt
from devflow_sdk.core.config import load_config, load_tool_config
```

### `start-issue/start-issue.py`
```python
# Remove:
from worktree import check_worktrunk, create_worktree, get_repo_root, _persist_branch_for_shell

# Replace with:
from devflow_sdk.domain.workspace import check_manager, create, find_for_issue
from devflow_sdk.core.git.worktree import get_repo_root
from devflow_sdk.core.git.shell_state import _persist_branch_for_shell
from devflow_sdk.domain.issue import fetch, write_issue_context
from devflow_sdk.core.branch_name import make_branch, infer_type, VALID_TYPES
from devflow_sdk.core.ai import run_ai_prompt
from devflow_sdk.core.summary import summary
from devflow_sdk.core.shell_function_check import check_shell_function
```

### `finish-issue/finish-issue.py`
```python
# Remove:
from shell_state import _persist_branch_for_shell, _persist_worktree_for_shell, ...
from merge_check import get_main_branch, is_merged
from devflow_sdk.worktrunk import check_worktrunk, list_worktrees, find_matching_worktrees, is_dirty

# Replace with:
from devflow_sdk.core.git.shell_state import (
    _persist_branch_for_shell, _persist_worktree_for_shell,
    _persist_force_for_shell, _persist_worktree_path_for_shell,
    _clear_force_marker_for_shell,
)
from devflow_sdk.core.git.merge_check import get_main_branch, is_merged
from devflow_sdk.domain.workspace import check_manager, find_for_issue
from devflow_sdk.core.git.worktree import list_worktrees, is_dirty
from devflow_sdk.domain.issue import fetch, read_issue_context, remove_issue_context
```

### `squash-commits/squash-commits.py`
```python
# Remove:
import git_ops

# Replace with:
from devflow_sdk.core.git import git_ops
```

### `address-pr/address-pr.py`
```python
# Update:
from devflow_sdk.domain.issue import check_gh
from devflow_sdk.core.ai import run_ai_prompt, configured_provider_display_name
from devflow_sdk.core.prompts import confirm
from devflow_sdk.core.summary import summary
```

### `devflow-config/devflow-config.py`
```python
# Update:
from devflow_sdk.core.config.io import CONFIG_PATH, load_config, load_tool_config, repair_config
from devflow_sdk.core.config.wizard import run_wizard
from devflow_sdk.core.config.wizard.global_steps import ModelsStep, ProviderStep
from devflow_sdk.core.config.wizard.tools import ALL_TOOL_STEPS
```

---

## External Consumer Changes

**`devflow-plugin-scaffold/scaffold.sh`** and **`README.md`**:
```python
# Before:
from devflow_sdk.draft_pr_plugin import DraftPrPlugin

# After:
from devflow_sdk.core.plugin import DraftPrPlugin
```

**`~/personal/default-format/default_format.py`**:
```python
# Before:
from devflow_sdk.draft_pr_plugin import DraftPrPlugin

# After:
from devflow_sdk.core.plugin import DraftPrPlugin
```

---

## Build Enforcement (`import-linter`)

Add `import-linter` to dev dependencies in `devflow-sdk/pyproject.toml`.

**`pyproject.toml` configuration:**
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

**`devflow-sdk/justfile`** — add a `lint-imports` recipe:
```makefile
lint-imports:
    lint-imports
```

Include `lint-imports` in the existing `check` or `ci` recipe so it runs alongside pytest.

**`.github/workflows/ci.yml`** — add `lint-imports` step after the install step in the SDK job.

**Note:** `import-linter` checks static imports only and will not flag dynamic `importlib` loading used by the plugin loader — this is intentional.

---

## Testing

### Moved test files
These tests move into `devflow-sdk/tests/` and have their imports updated to match new paths:
- `squash-commits/tests/test_git_ops.py` → `devflow-sdk/tests/test_git_ops.py`
- `finish-issue/tests/test_merge_check.py` → `devflow-sdk/tests/test_merge_check.py`
- `finish-issue/tests/test_shell_state.py` → `devflow-sdk/tests/test_shell_state.py`
- `start-issue/tests/test_worktree.py` → `devflow-sdk/tests/test_worktree.py` (expanded to cover `core/git/worktree.py`)

### Updated test files
All existing SDK tests update their imports to the new module paths:
- `test_ticket_info.py` → imports from `devflow_sdk.domain.issue`
- `test_issue_context.py` → imports from `devflow_sdk.domain.issue`
- `test_worktrunk.py` → renamed `test_worktree.py`; tests `core.git.worktree` and `core.git._worktrunk`
- `test_plugin_*.py` files → imports from `devflow_sdk.core.plugin`
- `test_ai*.py`, `test_config*.py`, `test_prompts.py`, etc. → imports from `devflow_sdk.core.*`

### New test file
**`devflow-sdk/tests/test_plugin_public_api.py`** — imports every symbol listed in `devflow_sdk.core.plugin.__init__` to catch re-export drift:
```python
from devflow_sdk.core.plugin import (
    PluginBase, DraftPrPlugin,
    PluginLoader, select_plugin,
    register, unregister, list_plugins, discover,
)
```

This test will fail at import time if any symbol is missing from the re-export.

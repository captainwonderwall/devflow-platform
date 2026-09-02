# Plugin/Core Re-organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `devflow_sdk/core/plugin/` to a top-level `devflow_sdk/plugin/` package, break the resulting `core → plugin` cycle in the wizard, enforce the layering with import-linter, and keep all existing callers working via a deprecation shim.

**Architecture:** The plugin package moves verbatim to `devflow_sdk/plugin/`; the old path becomes a thin re-export shim with a `DeprecationWarning`. The one `core → plugin` import (`draft_pr.py` importing `PluginLoader`) is eliminated by dependency inversion: `DraftPrWizardStep` accepts an injected `plugin_names` callable, and the composition root (`devflow-config.py`) supplies it. The import-linter enforces the new layers contract.

**Tech Stack:** Python 3.10+, pytest, import-linter (`lint-imports`), Homebrew Ruby formula.

**Spec:** `docs/superpowers/specs/2026-08-30-plugin-core-reorganization-design.md`

## Global Constraints

- Behaviour-preserving: no logic changes, no signature changes to public API.
- All existing tests must pass after import-path updates; `resolve_plugin` / `DirectoryRule` / plugin loader/registry tests need no logic changes.
- `devflow_sdk.core.plugin` stays importable (with `DeprecationWarning`) throughout.
- `ALL_TOOL_STEPS` stays exported from `devflow_sdk.core.config.wizard.tools` so existing code that hasn't adopted `build_tool_steps` continues to work.
- No new dependencies; no feature additions.

---

### Task 1: Create `devflow_sdk/plugin/` package

Move all seven modules verbatim (updating only internal import paths). The new `__init__.py` becomes the authoritative public surface. No logic changes.

**Files:**
- Create: `devflow-sdk/devflow_sdk/plugin/__init__.py`
- Create: `devflow-sdk/devflow_sdk/plugin/plugin_base.py`
- Create: `devflow-sdk/devflow_sdk/plugin/plugin_registry.py`
- Create: `devflow-sdk/devflow_sdk/plugin/contracts.py`
- Create: `devflow-sdk/devflow_sdk/plugin/plugin_loader.py`
- Create: `devflow-sdk/devflow_sdk/plugin/plugin_loader_impl.py`
- Create: `devflow-sdk/devflow_sdk/plugin/cli.py`

**Interfaces:**
- Produces: `devflow_sdk.plugin` exports `PluginBase, PluginLoaderBase, PluginLoader, PluginEntry, DraftPrPlugin, select_plugin, register, unregister, list_plugins, discover`

- [ ] **Step 1: Create `devflow_sdk/plugin/plugin_base.py`** — identical to `core/plugin/plugin_base.py`

```python
# devflow-sdk/devflow_sdk/plugin/plugin_base.py
from abc import ABC


class PluginBase(ABC):
    name: str = ""
```

- [ ] **Step 2: Create `devflow_sdk/plugin/plugin_registry.py`** — identical to `core/plugin/plugin_registry.py`

```python
# devflow-sdk/devflow_sdk/plugin/plugin_registry.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class PluginEntry:
    name: str
    path: str
    formula: str | None = None
```

- [ ] **Step 3: Create `devflow_sdk/plugin/contracts.py`** — update import to `devflow_sdk.plugin`

```python
# devflow-sdk/devflow_sdk/plugin/contracts.py
from abc import abstractmethod

from devflow_sdk.plugin.plugin_base import PluginBase


class DraftPrPlugin(PluginBase):
    @abstractmethod
    def get_questions(self, data: dict) -> list[dict]:
        """Return questions to ask the user before calling the AI.

        Each dict must have:
          id: str   — used as the key in user_inputs
          text: str — displayed to the user
        """

    @abstractmethod
    def build_prompt(self, data: dict, user_inputs: dict) -> str:
        """Build and return the AI prompt string.

        data: output of gather_pr_data.collect()
        user_inputs: answers to get_questions(), plus standard inputs
                     (jira_ticket, github_issue, issue_type, customer_visible)
        """

    @abstractmethod
    def build_body(self, ai_result: dict, user_inputs: dict) -> str:
        """Render and return the PR body markdown.

        ai_result: parsed JSON dict returned by the AI
        user_inputs: same dict passed to build_prompt
        """
```

- [ ] **Step 4: Create `devflow_sdk/plugin/plugin_loader.py`** — update import to `devflow_sdk.plugin`

```python
# devflow-sdk/devflow_sdk/plugin/plugin_loader.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypeVar

from devflow_sdk.plugin.plugin_registry import PluginEntry

T = TypeVar("T")


class PluginLoaderBase(ABC):

    @abstractmethod
    def register(self, name: str, path: str, formula: str | None = None) -> None:
        """Add or update a plugin entry in the registry."""

    @abstractmethod
    def unregister(self, name: str) -> None:
        """Remove a plugin entry. No-op if name not found."""

    @abstractmethod
    def list_plugins(self) -> dict[str, PluginEntry]:
        """Return all registered plugins keyed by name."""

    @abstractmethod
    def discover(self, base_cls: type[T]) -> dict[str, T]:
        """Load and instantiate registered plugins that are subclasses of base_cls."""

    @abstractmethod
    def select_plugin(self, base_cls: type[T], configured_name: str | None = None) -> T | None:
        """Discover plugins and select: by name, auto if one, or interactive prompt."""
```

- [ ] **Step 5: Create `devflow_sdk/plugin/plugin_loader_impl.py`** — update all three internal imports to `devflow_sdk.plugin`

```python
# devflow-sdk/devflow_sdk/plugin/plugin_loader_impl.py
from __future__ import annotations

import fcntl
import importlib.util
import inspect
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import TypeVar

from devflow_sdk.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin.plugin_registry import PluginEntry
from devflow_sdk.core.prompts import select

REGISTRY_PATH = Path.home() / ".devflow" / "plugin-registry.json"
REGISTRY_VERSION = 1

T = TypeVar("T")


def _load_registry(registry_path: Path = REGISTRY_PATH) -> dict[str, PluginEntry]:
    if not registry_path.exists():
        return {}
    try:
        data = json.loads(registry_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"[devflow] Warning: plugin registry is unreadable: {e}", file=sys.stderr)
        return {}
    if not isinstance(data, dict) or data.get("version") != REGISTRY_VERSION:
        print("[devflow] Warning: plugin registry format is unrecognized.", file=sys.stderr)
        return {}
    return {
        name: PluginEntry(name=name, path=entry["path"], formula=entry.get("formula"))
        for name, entry in data.get("plugins", {}).items()
        if isinstance(entry, dict) and "path" in entry
    }


def _save_registry(plugins: dict[str, PluginEntry], registry_path: Path = REGISTRY_PATH) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": REGISTRY_VERSION,
        "plugins": {
            name: {
                "path": e.path,
                **({"formula": e.formula} if e.formula else {}),
            }
            for name, e in plugins.items()
        },
    }
    fd, tmp_path = tempfile.mkstemp(dir=registry_path.parent, prefix=".registry-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.rename(tmp_path, registry_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_update_registry(mutation_fn, registry_path: Path = REGISTRY_PATH) -> None:
    lock_path = registry_path.parent / ".registry.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            plugins = _load_registry(registry_path)
            mutation_fn(plugins)
            _save_registry(plugins, registry_path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class PluginLoader(PluginLoaderBase):

    def __init__(self, registry_path: Path = REGISTRY_PATH) -> None:
        self._registry_path = registry_path

    def register(self, name: str, path: str, formula: str | None = None) -> None:
        def mutate(plugins):
            plugins[name] = PluginEntry(name=name, path=path, formula=formula)
        _atomic_update_registry(mutate, self._registry_path)

    def unregister(self, name: str) -> None:
        def mutate(plugins):
            if name in plugins:
                del plugins[name]
        _atomic_update_registry(mutate, self._registry_path)

    def list_plugins(self) -> dict[str, PluginEntry]:
        return _load_registry(self._registry_path)

    def discover(self, base_cls: type[T]) -> dict[str, T]:
        stale: list[str] = []

        def _purge_stale(plugins: dict[str, PluginEntry]) -> None:
            for name in list(plugins):
                if not os.path.exists(plugins[name].path):
                    stale.append(name)
                    del plugins[name]

        _atomic_update_registry(_purge_stale, self._registry_path)
        for name in stale:
            logging.warning(
                "[devflow] plugin '%s' not found on disk — purging stale registry entry.", name
            )

        found: dict[str, T] = {}
        for name, entry in _load_registry(self._registry_path).items():
            path = Path(entry.path)
            try:
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception:
                print(
                    f"[devflow] Warning: plugin '{name}' failed to load — it may be incompatible "
                    "with this version of devflow. Check for an updated release.",
                    file=sys.stderr,
                )
                continue
            for attr in vars(mod).values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, base_cls)
                    and attr is not base_cls
                    and not inspect.isabstract(attr)
                ):
                    try:
                        found[name] = attr()
                    except Exception:
                        print(
                            f"[devflow] Warning: plugin '{name}' failed to instantiate — "
                            "it may be incompatible with this version of devflow. "
                            "Check for an updated release.",
                            file=sys.stderr,
                        )
                    break
        return found

    def select_plugin(self, base_cls: type[T], configured_name: str | None = None) -> T | None:
        plugins = self.discover(base_cls)
        if not plugins:
            return None
        if configured_name:
            if configured_name in plugins:
                return plugins[configured_name]
            print(
                f"[devflow] Warning: configured plugin '{configured_name}' not found. "
                f"Available: {', '.join(plugins.keys())}",
                file=sys.stderr,
            )
        if len(plugins) == 1:
            return next(iter(plugins.values()))
        chosen = select("Select plugin", choices=list(plugins.keys()))
        return plugins[chosen]


_loader = PluginLoader()
register = _loader.register
unregister = _loader.unregister
list_plugins = _loader.list_plugins
discover = _loader.discover
select_plugin = _loader.select_plugin
```

- [ ] **Step 6: Create `devflow_sdk/plugin/cli.py`** — update import to `devflow_sdk.plugin`

```python
# devflow-sdk/devflow_sdk/plugin/cli.py
"""Command-line entry point for managing the devflow plugin registry."""
from __future__ import annotations

import argparse

from devflow_sdk.plugin.plugin_loader_impl import PluginLoader


def main() -> None:
    parser = argparse.ArgumentParser(prog="devflow-plugin")
    sub = parser.add_subparsers(dest="cmd", required=True)

    reg_p = sub.add_parser("register", help="Register a plugin")
    reg_p.add_argument("name", help="Plugin name")
    reg_p.add_argument("path", help="Absolute path to the plugin .py file")
    reg_p.add_argument("--formula", default=None, help="Homebrew formula identifier (tap/name)")

    unreg_p = sub.add_parser("unregister", help="Unregister a plugin")
    unreg_p.add_argument("name", help="Plugin name to remove")

    sub.add_parser("list", help="List all registered plugins")

    args = parser.parse_args()
    loader = PluginLoader()

    if args.cmd == "register":
        loader.register(args.name, args.path, args.formula)
    elif args.cmd == "unregister":
        loader.unregister(args.name)
    elif args.cmd == "list":
        found = loader.list_plugins()
        if not found:
            print("No plugins registered.")
        else:
            for pname, entry in found.items():
                print(f"{pname}: {entry.path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Create `devflow_sdk/plugin/__init__.py`** — authoritative public surface

```python
# devflow-sdk/devflow_sdk/plugin/__init__.py
from devflow_sdk.plugin.plugin_base import PluginBase
from devflow_sdk.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin.plugin_loader_impl import (
    PluginLoader,
    select_plugin,
    register,
    unregister,
    list_plugins,
    discover,
)
from devflow_sdk.plugin.plugin_registry import PluginEntry
from devflow_sdk.plugin.contracts import DraftPrPlugin

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

- [ ] **Step 8: Verify `devflow_sdk.plugin` imports correctly**

```bash
cd devflow-sdk && python -c "from devflow_sdk.plugin import PluginBase, PluginLoader, PluginEntry, DraftPrPlugin; print('OK')"
```
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add devflow-sdk/devflow_sdk/plugin/
git commit -m "feat(sdk): add devflow_sdk.plugin top-level package"
```

---

### Task 2: Convert `core/plugin/__init__.py` to deprecation shim; delete old modules

The old path re-exports everything from `devflow_sdk.plugin` and emits a `DeprecationWarning`. All files except `__init__.py` are deleted.

**Files:**
- Modify: `devflow-sdk/devflow_sdk/core/plugin/__init__.py`
- Delete: `devflow-sdk/devflow_sdk/core/plugin/plugin_base.py`
- Delete: `devflow-sdk/devflow_sdk/core/plugin/contracts.py`
- Delete: `devflow-sdk/devflow_sdk/core/plugin/plugin_loader.py`
- Delete: `devflow-sdk/devflow_sdk/core/plugin/plugin_loader_impl.py`
- Delete: `devflow-sdk/devflow_sdk/core/plugin/plugin_registry.py`
- Delete: `devflow-sdk/devflow_sdk/core/plugin/cli.py`

**Interfaces:**
- Consumes: `devflow_sdk.plugin` (from Task 1)
- Produces: `devflow_sdk.core.plugin` still importable, emits `DeprecationWarning`

- [ ] **Step 1: Rewrite `devflow_sdk/core/plugin/__init__.py` as the shim**

```python
# devflow-sdk/devflow_sdk/core/plugin/__init__.py
import warnings
from devflow_sdk.plugin import *          # noqa: F401,F403
from devflow_sdk.plugin import __all__    # noqa: F401

warnings.warn(
    "devflow_sdk.core.plugin is deprecated; import from devflow_sdk.plugin instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

- [ ] **Step 2: Verify shim re-exports and emits warning**

```bash
cd devflow-sdk && python -W all -c "
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    from devflow_sdk.core.plugin import PluginBase, PluginLoader, PluginEntry, DraftPrPlugin
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert 'deprecated' in str(w[0].message)
print('shim OK')
"
```
Expected: `shim OK`

- [ ] **Step 3: Delete old module files**

```bash
rm devflow-sdk/devflow_sdk/core/plugin/plugin_base.py \
   devflow-sdk/devflow_sdk/core/plugin/contracts.py \
   devflow-sdk/devflow_sdk/core/plugin/plugin_loader.py \
   devflow-sdk/devflow_sdk/core/plugin/plugin_loader_impl.py \
   devflow-sdk/devflow_sdk/core/plugin/plugin_registry.py \
   devflow-sdk/devflow_sdk/core/plugin/cli.py
```

- [ ] **Step 4: Run the plugin test suite — all tests must pass**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_base.py tests/test_plugin_loader.py tests/test_plugin_loader_impl.py tests/test_plugin_registry.py -v
```
Expected: all PASS (the shim satisfies the existing `core.plugin` imports)

- [ ] **Step 5: Commit**

```bash
git add devflow-sdk/devflow_sdk/core/plugin/__init__.py \
        devflow-sdk/devflow_sdk/core/plugin/plugin_base.py \
        devflow-sdk/devflow_sdk/core/plugin/contracts.py \
        devflow-sdk/devflow_sdk/core/plugin/plugin_loader.py \
        devflow-sdk/devflow_sdk/core/plugin/plugin_loader_impl.py \
        devflow-sdk/devflow_sdk/core/plugin/plugin_registry.py \
        devflow-sdk/devflow_sdk/core/plugin/cli.py
git commit -m "feat(sdk): replace core/plugin/ with deprecation shim pointing to devflow_sdk.plugin"
```

---

### Task 3: Break the `core → plugin` cycle in the wizard

`draft_pr.py` currently imports `PluginLoader` directly. Replace it with an injected `plugin_names` callable. Add `build_tool_steps` factory to `wizard/tools/__init__.py`. Update `devflow-config.py` to supply the provider at the composition root.

**Files:**
- Modify: `devflow-sdk/devflow_sdk/core/config/wizard/tools/draft_pr.py:1-10,58-70`
- Modify: `devflow-sdk/devflow_sdk/core/config/wizard/tools/__init__.py`
- Modify: `devflow/devflow-config/devflow-config.py`

**Interfaces:**
- Consumes: `devflow_sdk.plugin.PluginLoader` (used only in `devflow-config.py`, not in `core`)
- Produces:
  - `DraftPrWizardStep(plugin_names: Callable[[], list[str]] | None = None)`
  - `build_tool_steps(plugin_names: Callable[[], list[str]] | None = None) -> list[WizardStep]`
  - `ALL_TOOL_STEPS: list[WizardStep]` — unchanged, kept for backward compat

- [ ] **Step 1: Rewrite the top of `draft_pr.py` to remove `PluginLoader`; update `DraftPrWizardStep.__init__` and `run`**

Replace the entire file's imports and `DraftPrWizardStep` class. All other code (`DirectoryRule`, `DraftPrConfig`, `resolve_plugin`, `_rules_to_dicts`) is untouched:

```python
# devflow-sdk/devflow_sdk/core/config/wizard/tools/draft_pr.py
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field

from devflow_sdk.core.config.schema import DevflowConfig, PluginConfig
from devflow_sdk.core.config.wizard import WizardStep
from devflow_sdk.core.prompts import Choice, checkbox, confirm, select, text


@dataclass
class DirectoryRule:
    paths: list[str]
    plugin: str


@dataclass
class DraftPrConfig:
    plugin: PluginConfig[DirectoryRule] = field(default_factory=PluginConfig)

    def __post_init__(self):
        if isinstance(self.plugin, dict):
            raw_rules = self.plugin.get("rules", [])
            rules = [DirectoryRule(**r) for r in raw_rules]
            self.plugin = PluginConfig(
                default=self.plugin.get("default"),
                rules=rules,
            )
        self.plugin.rules.sort(
            key=lambda r: max((len(p) for p in r.paths), default=0),
            reverse=True,
        )

    def validate(self) -> None:
        if not self.plugin.rules and self.plugin.default is None:
            raise ValueError(
                "draft-pr: plugin config must have at least one rule or a default"
            )
        for rule in self.plugin.rules:
            if not rule.paths:
                raise ValueError(
                    "draft-pr: each plugin rule must have at least one path"
                )


def resolve_plugin(config: DraftPrConfig, cwd: str) -> str | None:
    for rule in config.plugin.rules:
        if any(cwd == p.rstrip("/") or cwd.startswith(p.rstrip("/") + "/") for p in rule.paths):
            return rule.plugin
    return config.plugin.default


def _rules_to_dicts(rules: list[DirectoryRule]) -> list[dict]:
    return [{"paths": r.paths, "plugin": r.plugin} for r in rules]


class DraftPrWizardStep(WizardStep):
    section = "draft-pr: Plugin Routing"
    tool_name = "draft-pr"
    schema_cls = DraftPrConfig

    def __init__(self, plugin_names: Callable[[], list[str]] | None = None):
        self._plugin_names = plugin_names or (lambda: [])

    def run(self, current: DevflowConfig) -> DevflowConfig:
        try:
            plugin_names = self._plugin_names()
        except Exception as e:
            print(f"  Warning: could not read plugin registry: {e}")
            return current
        if not plugin_names:
            print("  No plugins registered — skipping draft-pr plugin routing configuration.")
            return current

        # Load existing draft-pr config
        raw_draft_pr = current.tools.get("draft-pr", {})
        raw_plugin = raw_draft_pr.get("plugin", {})
        current_default = raw_plugin.get("default")
        current_rules: list[DirectoryRule] = [
            DirectoryRule(**r) for r in raw_plugin.get("rules", [])
        ]

        # Select default plugin
        default_choices = [
            Choice(name, checked=(name == current_default))
            for name in plugin_names
        ]
        chosen_default = select("Default plugin for draft-pr:", choices=default_choices)
        if chosen_default is None:
            return current

        # Show existing rules; user picks which to keep
        kept_rules: list[DirectoryRule] = []
        if current_rules:
            rule_choices = [
                Choice(
                    f"{', '.join(r.paths)} → {r.plugin}",
                    value=r,
                    checked=True,
                )
                for r in current_rules
            ]
            answer = checkbox("Which path rules should be kept?", choices=rule_choices, allow_empty=True)
            if answer is None:
                return current  # user cancelled; leave config unchanged
            kept_rules = answer  # may be [] if user deliberately deselected all

        # Offer to add new rules
        while confirm("Add a new path rule?", default=False):
            raw_paths = text("Path patterns (comma-separated):")
            if not raw_paths:
                break
            paths = [p.strip() for p in raw_paths.split(",") if p.strip()]
            rule_plugin_choices = [
                Choice(name, checked=(name == chosen_default))
                for name in plugin_names
            ]
            rule_plugin = select("Plugin for this path:", choices=rule_plugin_choices)
            if rule_plugin and paths:
                kept_rules.append(DirectoryRule(paths=paths, plugin=rule_plugin))

        updated_tools = {
            **current.tools,
            "draft-pr": {
                **raw_draft_pr,
                "plugin": {
                    "default": chosen_default,
                    "rules": _rules_to_dicts(kept_rules),
                },
            },
        }
        return dataclasses.replace(current, tools=updated_tools)
```

- [ ] **Step 2: Update `wizard/tools/__init__.py` to add `build_tool_steps`**

```python
# devflow-sdk/devflow_sdk/core/config/wizard/tools/__init__.py
from __future__ import annotations

from collections.abc import Callable

from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrWizardStep
from devflow_sdk.core.config.wizard import WizardStep


def build_tool_steps(plugin_names: Callable[[], list[str]] | None = None) -> list[WizardStep]:
    return [DraftPrWizardStep(plugin_names)]


ALL_TOOL_STEPS: list[WizardStep] = build_tool_steps()
```

- [ ] **Step 3: Update `devflow-config.py` to supply the plugin-names provider**

Make three targeted edits to `devflow/devflow-config/devflow-config.py` — everything else stays unchanged:

**Edit 1** — add `import sys` to the stdlib imports block (after `import shutil`):
```python
import sys
```

**Edit 2** — in the SDK imports block, replace the `ALL_TOOL_STEPS` import line:
```python
# old
from devflow_sdk.core.config.wizard.tools import ALL_TOOL_STEPS
# new
from devflow_sdk.core.config.wizard.tools import build_tool_steps
from devflow_sdk.plugin import PluginLoader
```

**Edit 3** — replace the entire `main()` function:
```python
def main():
    def _plugin_names() -> list[str]:
        try:
            return sorted(PluginLoader().list_plugins())
        except Exception as e:
            print(f"  Warning: could not read plugin registry: {e}", file=sys.stderr)
            return []

    steps = [ProviderStep(), ModelsStep()] + build_tool_steps(_plugin_names)
    tool_registry = {s.tool_name: s.schema_cls for s in steps if s.tool_name}

    if not _config_is_valid(tool_registry):
        _backup_config()
        repair_config(path=CONFIG_PATH, tool_registry=tool_registry)

    config = run_wizard(steps)
    if config.global_config.ai_provider == "opencode":
        _install_opencode_config()
    print("\nConfig saved to ~/.devflow/config.json")
```

- [ ] **Step 4: Commit**

```bash
git add devflow-sdk/devflow_sdk/core/config/wizard/tools/draft_pr.py \
        devflow-sdk/devflow_sdk/core/config/wizard/tools/__init__.py \
        devflow/devflow-config/devflow-config.py
git commit -m "refactor(sdk): break core→plugin cycle via DraftPrWizardStep dependency injection"
```

---

### Task 4: Update remaining callers and Homebrew formula

`draft-pr.py` imports `DraftPrPlugin, select_plugin` from the old path. The Homebrew formula hardcodes the old module path for the `devflow-plugin` CLI wrapper.

**Files:**
- Modify: `devflow/draft-pr/draft-pr.py:14`
- Modify: `homebrew-devflow/Formula/devflow.rb:57`

**Interfaces:**
- Consumes: `devflow_sdk.plugin` (Task 1)

- [ ] **Step 1: Update import in `draft-pr.py`**

Find line 14 in `devflow/draft-pr/draft-pr.py`:

```python
# old
from devflow_sdk.core.plugin import DraftPrPlugin, select_plugin
```

Replace with:

```python
# new
from devflow_sdk.plugin import DraftPrPlugin, select_plugin
```

- [ ] **Step 2: Update module path string in `devflow.rb`**

Find line 57 in `homebrew-devflow/Formula/devflow.rb`:

```ruby
      exec python3 -m devflow_sdk.core.plugin.cli "$@"
```

Replace with:

```ruby
      exec python3 -m devflow_sdk.plugin.cli "$@"
```

- [ ] **Step 3: Verify `draft-pr.py` imports resolve**

```bash
cd devflow-sdk && python -c "
import sys; sys.path.insert(0, '.')
from devflow_sdk.plugin import DraftPrPlugin, select_plugin
print('draft-pr imports OK')
"
```
Expected: `draft-pr imports OK`

- [ ] **Step 4: Commit**

```bash
git add devflow/draft-pr/draft-pr.py homebrew-devflow/Formula/devflow.rb
git commit -m "fix: update devflow_sdk.plugin import paths in draft-pr and Homebrew formula"
```

---

### Task 5: Update import-linter contracts

Replace the "Core must not import from domain" forbidden contract with the stricter "SDK layers" layers contract. Keep "Domains are independent of each other" unchanged.

**Files:**
- Modify: `devflow-sdk/pyproject.toml`

**Interfaces:**
- Consumes: the broken `core → plugin` cycle from Task 3

- [ ] **Step 1: Update `[tool.importlinter]` section in `devflow-sdk/pyproject.toml`**

Find the entire import-linter block:

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

Replace with:

```toml
[tool.importlinter]
root_package = "devflow_sdk"

[[tool.importlinter.contracts]]
name = "SDK layers"
type = "layers"
layers = [
    "devflow_sdk.domain",
    "devflow_sdk.plugin",
    "devflow_sdk.core",
]
ignore_imports = [
    # Deprecation shim only; delete this line when core/plugin/ is removed.
    "devflow_sdk.core.plugin -> devflow_sdk.plugin",
]

[[tool.importlinter.contracts]]
name = "Domains are independent of each other"
type = "independence"
modules = [
    "devflow_sdk.domain.issue",
    "devflow_sdk.domain.workspace",
]
```

- [ ] **Step 2: Run import-linter and confirm both contracts pass**

```bash
cd devflow-sdk && python -m importlinter
```
Expected output includes:
```
SDK layers                                         KEPT (1 ignored import)
Domains are independent of each other              KEPT
```

If `lint-imports` is the project's alias, use that instead:
```bash
cd devflow-sdk && python -m pytest --co -q 2>/dev/null | head -5  # check if lint-imports is a pytest plugin
# or:
cd devflow-sdk && lint-imports
```

- [ ] **Step 3: Commit**

```bash
git add devflow-sdk/pyproject.toml
git commit -m "chore(sdk): enforce SDK layer contract via import-linter; remove superseded forbidden contract"
```

---

### Task 6: Update and add tests

Update all test files that reference changed APIs. Add the new `test_plugin_cli.py`. The goal is: all tests pass, and the test suite proves the move is behaviour-preserving.

**Files:**
- Modify: `devflow-sdk/tests/test_plugin_base.py`
- Modify: `devflow-sdk/tests/test_plugin_loader.py`
- Modify: `devflow-sdk/tests/test_plugin_loader_impl.py`
- Modify: `devflow-sdk/tests/test_plugin_registry.py`
- Modify: `devflow-sdk/tests/test_plugin_public_api.py`
- Modify: `devflow-sdk/tests/test_wizard_draft_pr.py`
- Modify: `devflow/devflow-config/tests/test_wizard.py`
- Create: `devflow-sdk/tests/test_plugin_cli.py`

**Interfaces:**
- Consumes: `devflow_sdk.plugin` (Task 1), deprecation shim (Task 2), `DraftPrWizardStep(plugin_names=...)` (Task 3), `build_tool_steps` (Task 3)

- [ ] **Step 1: Update `test_plugin_base.py` — swap import path**

```python
# devflow-sdk/tests/test_plugin_base.py
from devflow_sdk.plugin import PluginBase


def test_plugin_base_is_instantiable():
    p = PluginBase()
    assert isinstance(p, PluginBase)


def test_plugin_name_defaults_to_empty_string():
    assert PluginBase.name == ""


def test_subclass_can_set_name():
    class Named(PluginBase):
        name = "My Plugin"
    assert Named().name == "My Plugin"


def test_subclass_inherits_plugin_base():
    class Sub(PluginBase):
        pass
    assert issubclass(Sub, PluginBase)
```

- [ ] **Step 2: Update `test_plugin_loader.py` — swap import path**

```python
# devflow-sdk/tests/test_plugin_loader.py
import unittest
from devflow_sdk.plugin import PluginLoaderBase


class TestPluginLoaderBase(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            PluginLoaderBase()

    def test_all_five_methods_are_abstract(self):
        abstract = PluginLoaderBase.__abstractmethods__
        self.assertIn("register", abstract)
        self.assertIn("unregister", abstract)
        self.assertIn("list_plugins", abstract)
        self.assertIn("discover", abstract)
        self.assertIn("select_plugin", abstract)

    def test_subclass_missing_methods_cannot_instantiate(self):
        class Partial(PluginLoaderBase):
            def register(self, name, path, formula=None): pass
            def unregister(self, name): pass

        with self.assertRaises(TypeError):
            Partial()

    def test_complete_subclass_can_instantiate(self):
        class Complete(PluginLoaderBase):
            def register(self, name, path, formula=None): pass
            def unregister(self, name): pass
            def list_plugins(self): return {}
            def discover(self, base_cls): return {}
            def select_plugin(self, base_cls, configured_name=None): return None

        instance = Complete()
        self.assertIsInstance(instance, PluginLoaderBase)
```

- [ ] **Step 3: Update `test_plugin_loader_impl.py` — swap import paths**

```python
# devflow-sdk/tests/test_plugin_loader_impl.py
import json
import pytest
from pathlib import Path

from devflow_sdk.plugin.plugin_loader_impl import PluginLoader
from devflow_sdk.plugin import PluginEntry


@pytest.fixture
def registry_path(tmp_path):
    return tmp_path / "plugin-registry.json"


def test_list_plugins_empty(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    assert loader.list_plugins() == {}


def test_register_then_list(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.register("smoke-check", "/some/path/smoke_check.py", formula="captainwonderwall/devflow/devflow-plugin-smoke-check")
    plugins = loader.list_plugins()
    assert "smoke-check" in plugins
    assert plugins["smoke-check"].path == "/some/path/smoke_check.py"
    assert plugins["smoke-check"].formula == "captainwonderwall/devflow/devflow-plugin-smoke-check"


def test_register_then_unregister(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.register("smoke-check", "/some/path/smoke_check.py")
    loader.unregister("smoke-check")
    assert loader.list_plugins() == {}


def test_unregister_nonexistent_is_noop(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.unregister("does-not-exist")


def test_register_updates_existing(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.register("plugin-a", "/old/path.py")
    loader.register("plugin-a", "/new/path.py")
    assert loader.list_plugins()["plugin-a"].path == "/new/path.py"


def test_registry_file_written_as_valid_json(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.register("my-plugin", "/path/to/plugin.py")
    data = json.loads(registry_path.read_text())
    assert data["version"] == 1
    assert "my-plugin" in data["plugins"]
```

- [ ] **Step 4: Update `test_plugin_registry.py` — swap import path**

```python
# devflow-sdk/tests/test_plugin_registry.py
import unittest
from devflow_sdk.plugin import PluginEntry


class TestPluginEntry(unittest.TestCase):
    def test_required_fields(self):
        entry = PluginEntry(name="my-plugin", path="/opt/homebrew/opt/devflow-plugin-my/lib/my.py")
        self.assertEqual(entry.name, "my-plugin")
        self.assertEqual(entry.path, "/opt/homebrew/opt/devflow-plugin-my/lib/my.py")
        self.assertIsNone(entry.formula)

    def test_with_formula(self):
        entry = PluginEntry(
            name="my-plugin",
            path="/some/path.py",
            formula="org/tap/devflow-plugin-my",
        )
        self.assertEqual(entry.formula, "org/tap/devflow-plugin-my")

    def test_equality(self):
        a = PluginEntry(name="x", path="/a.py")
        b = PluginEntry(name="x", path="/a.py")
        self.assertEqual(a, b)

    def test_inequality_different_path(self):
        a = PluginEntry(name="x", path="/a.py")
        b = PluginEntry(name="x", path="/b.py")
        self.assertNotEqual(a, b)
```

- [ ] **Step 5: Update `test_plugin_public_api.py` — test new path AND shim**

```python
# devflow-sdk/tests/test_plugin_public_api.py
"""Smoke test: public API accessible from both the new and deprecated paths."""
import warnings

_EXPECTED_NAMES = [
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


def test_new_path_exports_all_public_symbols():
    from devflow_sdk.plugin import (
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


def test_new_path_all_matches_expected():
    import devflow_sdk.plugin as pkg
    for name in _EXPECTED_NAMES:
        assert name in pkg.__all__, f"{name!r} missing from devflow_sdk.plugin.__all__"
        assert getattr(pkg, name) is not None


def test_deprecated_path_reexports_same_symbols():
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        import devflow_sdk.core.plugin as shim
        import devflow_sdk.plugin as new_pkg
    for name in _EXPECTED_NAMES:
        assert getattr(shim, name) is getattr(new_pkg, name), \
            f"{name!r} identity mismatch between shim and new package"


def test_deprecated_path_emits_deprecation_warning():
    # Re-import in a fresh scope to ensure the warning fires
    import importlib
    import sys
    # Remove cached module so the warning triggers again
    for key in list(sys.modules):
        if "devflow_sdk.core.plugin" in key and key != "devflow_sdk.core":
            del sys.modules[key]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import devflow_sdk.core.plugin  # noqa: F401
        assert any(
            issubclass(warning.category, DeprecationWarning)
            and "deprecated" in str(warning.message)
            for warning in w
        ), "Expected DeprecationWarning from devflow_sdk.core.plugin import"
```

- [ ] **Step 6: Run public API tests**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_public_api.py -v
```
Expected: all PASS

- [ ] **Step 7: Update `test_wizard_draft_pr.py` — use injected `plugin_names` callable; assert no plugin import**

Replace only `TestDraftPrWizardStep` class and the import of `PluginEntry`. `TestDraftPrConfig` and `TestResolvePlugin` classes are untouched:

```python
# devflow-sdk/tests/test_wizard_draft_pr.py
import dataclasses
import importlib
import pytest
from unittest.mock import patch

from devflow_sdk.core.config import DevflowConfig, GlobalConfig
from devflow_sdk.core.config.wizard.tools.draft_pr import (
    DraftPrConfig,
    DraftPrWizardStep,
    DirectoryRule,
    resolve_plugin,
)
from devflow_sdk.plugin import PluginEntry


def _make_config(draft_pr_tools=None):
    tools = {}
    if draft_pr_tools is not None:
        tools["draft-pr"] = draft_pr_tools
    return DevflowConfig(global_config=GlobalConfig(), tools=tools)


def _make_entry(name):
    return PluginEntry(name=name, path=f"/path/{name}.py", formula=None)


class TestDraftPrConfig:
    def test_defaults(self):
        cfg = DraftPrConfig()
        assert cfg.plugin.default is None
        assert cfg.plugin.rules == []

    def test_post_init_converts_dict(self):
        raw = {
            "plugin": {
                "default": "smoke-check",
                "rules": [{"paths": ["/src"], "plugin": "other"}],
            }
        }
        from devflow_sdk.core.config import load_tool_config, DevflowConfig, GlobalConfig
        config = DevflowConfig(global_config=GlobalConfig(), tools={"draft-pr": raw})
        draft_cfg = load_tool_config(config, "draft-pr", DraftPrConfig)
        assert draft_cfg.plugin.default == "smoke-check"
        assert draft_cfg.plugin.rules[0].paths == ["/src"]

    def test_validate_raises_when_no_default_and_no_rules(self):
        cfg = DraftPrConfig()
        with pytest.raises(ValueError, match="plugin config must have"):
            cfg.validate()

    def test_validate_passes_with_default(self):
        from devflow_sdk.core.config.schema import PluginConfig
        cfg = DraftPrConfig(plugin=PluginConfig(default="smoke-check"))
        cfg.validate()

    def test_rules_sorted_by_path_length_descending(self):
        from devflow_sdk.core.config.schema import PluginConfig
        rules = [
            DirectoryRule(paths=["/a"], plugin="short"),
            DirectoryRule(paths=["/a/b/c/d"], plugin="longest"),
            DirectoryRule(paths=["/a/b"], plugin="medium"),
        ]
        cfg = DraftPrConfig(plugin=PluginConfig(default=None, rules=rules))
        assert cfg.plugin.rules[0].plugin == "longest"
        assert cfg.plugin.rules[1].plugin == "medium"
        assert cfg.plugin.rules[2].plugin == "short"


class TestResolvePlugin:
    def test_matches_first_rule_by_path_prefix(self):
        from devflow_sdk.core.config.schema import PluginConfig
        rules = [DirectoryRule(paths=["/Users/foo/projects"], plugin="proj-plugin")]
        cfg = DraftPrConfig(plugin=PluginConfig(default="default-plugin", rules=rules))
        assert resolve_plugin(cfg, "/Users/foo/projects/myrepo") == "proj-plugin"

    def test_falls_back_to_default(self):
        from devflow_sdk.core.config.schema import PluginConfig
        cfg = DraftPrConfig(plugin=PluginConfig(default="fallback"))
        assert resolve_plugin(cfg, "/unmatched/path") == "fallback"

    def test_does_not_match_path_prefix_sibling(self):
        from devflow_sdk.core.config.schema import PluginConfig
        rules = [DirectoryRule(paths=["/foo/proj"], plugin="proj-plugin")]
        cfg = DraftPrConfig(plugin=PluginConfig(default="fallback", rules=rules))
        assert resolve_plugin(cfg, "/foo/projectX") == "fallback"

    def test_matches_exact_path(self):
        from devflow_sdk.core.config.schema import PluginConfig
        rules = [DirectoryRule(paths=["/foo/proj"], plugin="proj-plugin")]
        cfg = DraftPrConfig(plugin=PluginConfig(default="fallback", rules=rules))
        assert resolve_plugin(cfg, "/foo/proj") == "proj-plugin"


class TestDraftPrWizardStep:
    def test_section_label(self):
        assert DraftPrWizardStep().section == "draft-pr: Plugin Routing"

    def test_module_does_not_import_plugin_package(self):
        import importlib.util
        import devflow_sdk.core.config.wizard.tools.draft_pr as m
        src = importlib.util.find_spec(m.__name__).origin
        content = open(src).read()
        assert "devflow_sdk.plugin" not in content
        assert "devflow_sdk.core.plugin" not in content

    def test_skips_when_no_plugins_registered(self, capsys):
        step = DraftPrWizardStep(plugin_names=lambda: [])
        current = _make_config()
        result = step.run(current)
        assert result == current
        assert "No plugins" in capsys.readouterr().out

    def test_skips_when_no_provider_given(self, capsys):
        step = DraftPrWizardStep()
        current = _make_config()
        result = step.run(current)
        assert result == current

    def test_degrades_when_provider_raises(self, capsys):
        def _broken():
            raise RuntimeError("registry broken")
        step = DraftPrWizardStep(plugin_names=_broken)
        current = _make_config()
        result = step.run(current)
        assert result == current
        assert "Warning" in capsys.readouterr().out

    def test_sets_default_plugin(self):
        step = DraftPrWizardStep(plugin_names=lambda: ["smoke-check"])
        current = _make_config()
        with (
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=[]),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.confirm", return_value=False),
        ):
            result = step.run(current)
        assert result.tools["draft-pr"]["plugin"]["default"] == "smoke-check"

    def test_existing_rules_kept_when_all_selected(self):
        step = DraftPrWizardStep(plugin_names=lambda: ["smoke-check", "other-plugin"])
        existing_tools = {
            "plugin": {
                "default": "smoke-check",
                "rules": [{"paths": ["/src"], "plugin": "other-plugin"}],
            }
        }
        current = _make_config(draft_pr_tools=existing_tools)
        rule = DirectoryRule(paths=["/src"], plugin="other-plugin")
        with (
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=[rule]),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.confirm", return_value=False),
        ):
            result = step.run(current)
        rules = result.tools["draft-pr"]["plugin"]["rules"]
        assert any(r["paths"] == ["/src"] for r in rules)

    def test_cancel_on_rules_prompt_returns_config_unchanged(self):
        step = DraftPrWizardStep(plugin_names=lambda: ["smoke-check", "other-plugin"])
        existing_tools = {
            "plugin": {
                "default": "smoke-check",
                "rules": [{"paths": ["/src"], "plugin": "other-plugin"}],
            }
        }
        current = _make_config(draft_pr_tools=existing_tools)
        with (
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=None),
        ):
            result = step.run(current)
        assert result == current

    def test_new_rule_added(self):
        step = DraftPrWizardStep(plugin_names=lambda: ["smoke-check"])
        current = _make_config()
        with (
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=[]),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.confirm", side_effect=[True, False]),
            patch("devflow_sdk.core.config.wizard.tools.draft_pr.text", return_value="/work/myproject"),
        ):
            result = step.run(current)
        rules = result.tools["draft-pr"]["plugin"]["rules"]
        assert any("/work/myproject" in r["paths"] for r in rules)
```

- [ ] **Step 8: Run updated `test_wizard_draft_pr.py`**

```bash
cd devflow-sdk && python -m pytest tests/test_wizard_draft_pr.py -v
```
Expected: all PASS

- [ ] **Step 9: Create `test_plugin_cli.py`**

```python
# devflow-sdk/tests/test_plugin_cli.py
"""Verify devflow_sdk.plugin.cli is importable and runnable as a module."""
import subprocess
import sys


def test_cli_module_is_importable():
    from devflow_sdk.plugin import cli
    assert callable(cli.main)


def test_cli_module_runnable_via_dash_m():
    result = subprocess.run(
        [sys.executable, "-m", "devflow_sdk.plugin.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr}"
    assert "devflow-plugin" in result.stdout
```

- [ ] **Step 10: Run `test_plugin_cli.py`**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_cli.py -v
```
Expected: both PASS

- [ ] **Step 11: Update `devflow/devflow-config/tests/test_wizard.py` — add `build_tool_steps` coverage**

Add these tests after the existing `test_all_tool_steps_*` tests (all existing tests remain unchanged):

```python
# Add after the existing ALL_TOOL_STEPS tests block in test_wizard.py

# ── build_tool_steps ────────────────────────────────────────────────────────────

def test_build_tool_steps_with_no_argument_matches_all_tool_steps():
    from devflow_sdk.core.config.wizard.tools import build_tool_steps, ALL_TOOL_STEPS
    steps = build_tool_steps()
    assert len(steps) == len(ALL_TOOL_STEPS)
    assert type(steps[0]) is type(ALL_TOOL_STEPS[0])


def test_build_tool_steps_with_populated_provider(capsys):
    from devflow_sdk.core.config.wizard.tools import build_tool_steps
    from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrWizardStep
    from unittest.mock import patch

    steps = build_tool_steps(lambda: ["smoke-check"])
    draft_step = next(s for s in steps if isinstance(s, DraftPrWizardStep))

    from devflow_sdk.core.config.schema import DevflowConfig, GlobalConfig
    current = DevflowConfig(global_config=GlobalConfig(), tools={})

    with (
        patch("devflow_sdk.core.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
        patch("devflow_sdk.core.config.wizard.tools.draft_pr.checkbox", return_value=[]),
        patch("devflow_sdk.core.config.wizard.tools.draft_pr.confirm", return_value=False),
    ):
        result = draft_step.run(current)

    assert result.tools["draft-pr"]["plugin"]["default"] == "smoke-check"


def test_build_tool_steps_with_empty_provider(capsys):
    from devflow_sdk.core.config.wizard.tools import build_tool_steps
    from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrWizardStep

    steps = build_tool_steps(lambda: [])
    draft_step = next(s for s in steps if isinstance(s, DraftPrWizardStep))

    from devflow_sdk.core.config.schema import DevflowConfig, GlobalConfig
    current = DevflowConfig(global_config=GlobalConfig(), tools={})
    result = draft_step.run(current)

    assert result == current
    assert "No plugins" in capsys.readouterr().out


def test_build_tool_steps_with_raising_provider_degrades_gracefully(capsys):
    from devflow_sdk.core.config.wizard.tools import build_tool_steps
    from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrWizardStep

    def _broken():
        raise RuntimeError("registry unreadable")

    steps = build_tool_steps(_broken)
    draft_step = next(s for s in steps if isinstance(s, DraftPrWizardStep))

    from devflow_sdk.core.config.schema import DevflowConfig, GlobalConfig
    current = DevflowConfig(global_config=GlobalConfig(), tools={})
    result = draft_step.run(current)

    assert result == current
    assert "Warning" in capsys.readouterr().out
```

- [ ] **Step 12: Update `devflow-sdk/README.md` and `DEVELOPMENT.md` — document the new import path and deprecation**

In `devflow-sdk/README.md`, find any reference to `devflow_sdk.core.plugin` in import examples and update to `devflow_sdk.plugin`. Add a note that `devflow_sdk.core.plugin` still works but emits a `DeprecationWarning`.

In `devflow-sdk/DEVELOPMENT.md` (or equivalent developer guide), find the import-linter / layering documentation section and update it to reflect the new "SDK layers" contract: `domain` → `plugin` → `core`, with `core` importing neither.

If the import path does not appear in either file, add a one-sentence migration note to the relevant section of whichever file discusses plugin authorship.

- [ ] **Step 13: Run all updated tests end-to-end**

```bash
cd devflow-sdk && python -m pytest tests/ -v
cd devflow/devflow-config && python -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 14: Commit**

```bash
git add devflow-sdk/tests/test_plugin_base.py \
        devflow-sdk/tests/test_plugin_loader.py \
        devflow-sdk/tests/test_plugin_loader_impl.py \
        devflow-sdk/tests/test_plugin_registry.py \
        devflow-sdk/tests/test_plugin_public_api.py \
        devflow-sdk/tests/test_wizard_draft_pr.py \
        devflow-sdk/tests/test_plugin_cli.py \
        devflow/devflow-config/tests/test_wizard.py \
        devflow-sdk/README.md \
        devflow-sdk/DEVELOPMENT.md
git commit -m "test(sdk): update tests for devflow_sdk.plugin move; add CLI smoke test and build_tool_steps coverage; update docs"
```

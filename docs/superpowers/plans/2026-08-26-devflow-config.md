# devflow-config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `devflow-config` interactive wizard binary and consolidate all config/plugin-loader code into `devflow-sdk`.

**Architecture:** `devflow_sdk/config.py` becomes a package (`devflow_sdk/config/`) containing the schema, I/O, and a wizard sub-package of self-contained `WizardStep` classes. The concrete `PluginLoader` moves from `devflow/plugin-manager/plugin_loader.py` into `devflow_sdk/plugin/plugin_loader_impl.py`. Migration shims keep the original file paths importable so no existing tool script needs changes. A new `devflow/devflow-config/devflow-config.py` (~15 lines) is the only new binary — it just chains wizard steps and calls `run_wizard()`.

**Tech Stack:** Python 3.11+, `questionary 2.1.1` (via `devflow_sdk.prompts`), `pytest`, `uv`

**Spec:** `docs/superpowers/specs/2026-08-26-devflow-config-design.md`

## Global Constraints

- Python ≥ 3.11 throughout
- All interactive prompts use `devflow_sdk.prompts` wrappers (`select`, `text`, `confirm`, `checkbox`, `Choice`) — never import `questionary` directly in new code
- Backward-compat: `from devflow_sdk.config import load_config, DevflowConfig, ...` must continue to work in all six existing tool scripts without any edits to those scripts
- `devflow/draft-pr/config.py` becomes a shim; `devflow/plugin-manager/plugin_loader.py` becomes a shim — the tool scripts themselves (`draft-pr.py`, etc.) are not touched
- `devflow_sdk` version bumps `1.0.1 → 1.1.0` (minor — new public surface, nothing removed)
- Test commands: `cd devflow-sdk && uv run --extra dev pytest` (SDK), `uv run --no-project pytest devflow/` (tool tests)

---

## File Map

| Status | Path | Responsibility |
|--------|------|----------------|
| CREATE | `devflow_sdk/config/__init__.py` | Backward-compat re-exports of full `config.py` surface |
| CREATE | `devflow_sdk/config/schema.py` | Dataclasses: `ModelConfig`, `GlobalConfig`, `DevflowConfig`, `PluginConfig` |
| CREATE | `devflow_sdk/config/io.py` | `load_config()`, `save_config()`, `merge_config()`, `load_tool_config()`, `_config_to_dict()`, `CONFIG_PATH` |
| CREATE | `devflow_sdk/config/wizard/__init__.py` | `WizardStep` ABC, `run_wizard()` |
| CREATE | `devflow_sdk/config/wizard/global_steps.py` | `ProviderStep`, `ModelsStep` |
| CREATE | `devflow_sdk/config/wizard/tools/__init__.py` | `ALL_TOOL_STEPS` registry list |
| CREATE | `devflow_sdk/config/wizard/tools/draft_pr.py` | `DraftPrConfig`, `DirectoryRule`, `resolve_plugin()`, `DraftPrWizardStep` |
| CREATE | `devflow_sdk/plugin/plugin_loader_impl.py` | Concrete `PluginLoader` class + registry helpers |
| CREATE | `devflow_sdk/tests/test_config_io.py` | Tests for `save_config`, `merge_config` |
| CREATE | `devflow_sdk/tests/test_wizard.py` | Tests for `WizardStep` protocol and `run_wizard` |
| CREATE | `devflow_sdk/tests/test_wizard_global_steps.py` | Tests for `ProviderStep`, `ModelsStep` |
| CREATE | `devflow_sdk/tests/test_wizard_draft_pr.py` | Tests for `DraftPrWizardStep` |
| CREATE | `devflow_sdk/tests/test_plugin_loader_impl.py` | Tests for concrete `PluginLoader` |
| CREATE | `devflow/devflow-config/devflow-config.py` | Thin orchestrator script (~15 lines) |
| DELETE | `devflow_sdk/devflow_sdk/config.py` | Replaced by `config/` package |
| MODIFY | `devflow_sdk/tests/test_config.py` | Update `monkeypatch.setattr` targets to `devflow_sdk.config.io.CONFIG_PATH` |
| MODIFY | `devflow_sdk/devflow_sdk/prompts.py` | Add `default=""` parameter to `text()` |
| MODIFY | `devflow_sdk/plugin/__init__.py` | Re-export `PluginLoader` from `plugin_loader_impl` |
| MODIFY | `devflow/draft-pr/config.py` | Shim → re-exports from `devflow_sdk.config.wizard.tools.draft_pr` |
| MODIFY | `devflow/plugin-manager/plugin_loader.py` | Shim → delegates to `devflow_sdk.plugin.plugin_loader_impl` |
| MODIFY | `devflow_sdk/pyproject.toml` | Version `1.0.1 → 1.1.0` |
| MODIFY | `homebrew-devflow/Formula/devflow.rb` | Add `devflow-config` binary; bump SDK resource version |

---

## Task 1: Refactor `devflow_sdk/config.py` into `devflow_sdk/config/` package

**Files:**
- Create: `devflow_sdk/devflow_sdk/config/__init__.py`
- Create: `devflow_sdk/devflow_sdk/config/schema.py`
- Create: `devflow_sdk/devflow_sdk/config/io.py`
- Create: `devflow_sdk/tests/test_config_io.py`
- Delete: `devflow_sdk/devflow_sdk/config.py`
- Modify: `devflow_sdk/tests/test_config.py` (monkeypatch targets)

**Interfaces:**
- Produces: `load_config(path: Path | None = None) -> DevflowConfig`, `save_config(config: DevflowConfig, path: Path | None = None) -> None`, `merge_config(base: DevflowConfig, overlay: DevflowConfig) -> DevflowConfig`, `load_tool_config(config: DevflowConfig, tool_name: str, schema_cls: type[T]) -> T`, `CONFIG_PATH: Path` — all importable from `devflow_sdk.config`

- [ ] **Step 1: Write failing tests for `save_config` and `merge_config`**

Create `devflow_sdk/tests/test_config_io.py`:

```python
import json
import pytest
from pathlib import Path

from devflow_sdk.config import (
    DevflowConfig,
    GlobalConfig,
    ModelConfig,
    load_config,
    save_config,
    merge_config,
)


def test_save_config_creates_valid_json(tmp_path):
    config_path = tmp_path / "config.json"
    config = DevflowConfig(
        global_config=GlobalConfig(
            ai_provider="opencode",
            models={"fast": ModelConfig(name="my-fast")},
        )
    )
    save_config(config, path=config_path)
    data = json.loads(config_path.read_text())
    assert data["global"]["ai_provider"] == "opencode"
    assert data["global"]["models"]["fast"]["name"] == "my-fast"


def test_save_config_roundtrip(tmp_path):
    config_path = tmp_path / "config.json"
    original = DevflowConfig(
        global_config=GlobalConfig(
            ai_provider="claude",
            models={
                "fast": ModelConfig(
                    name="claude-haiku-4-5-20251001",
                    pricing={"input": 0.8, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
                ),
                "capable": ModelConfig(name="claude-sonnet-4-6"),
            },
        ),
        tools={"draft-pr": {"plugin": {"default": "smoke-check"}}},
    )
    save_config(original, path=config_path)
    loaded = load_config(path=config_path)
    assert loaded.global_config.ai_provider == "claude"
    assert loaded.global_config.models["fast"].name == "claude-haiku-4-5-20251001"
    assert loaded.tools["draft-pr"]["plugin"]["default"] == "smoke-check"


def test_save_config_leaves_no_temp_files(tmp_path):
    config_path = tmp_path / "config.json"
    save_config(DevflowConfig(), path=config_path)
    leftovers = [f for f in tmp_path.iterdir() if f.name.startswith(".config-")]
    assert leftovers == []


def test_merge_config_overlay_ai_provider_wins():
    base = DevflowConfig(global_config=GlobalConfig(ai_provider="claude"))
    overlay = DevflowConfig(global_config=GlobalConfig(ai_provider="opencode"))
    result = merge_config(base, overlay)
    assert result.global_config.ai_provider == "opencode"


def test_merge_config_models_merged_by_key():
    fast = ModelConfig(name="haiku")
    capable = ModelConfig(name="sonnet")
    base = DevflowConfig(global_config=GlobalConfig(models={"fast": fast}))
    overlay = DevflowConfig(global_config=GlobalConfig(models={"capable": capable}))
    result = merge_config(base, overlay)
    assert "fast" in result.global_config.models
    assert "capable" in result.global_config.models


def test_merge_config_tools_merged_by_key():
    base = DevflowConfig(tools={"draft-pr": {"x": 1}})
    overlay = DevflowConfig(tools={"squash-commits": {"y": 2}})
    result = merge_config(base, overlay)
    assert "draft-pr" in result.tools
    assert "squash-commits" in result.tools


def test_merge_config_overlay_tool_wins():
    base = DevflowConfig(tools={"draft-pr": {"plugin": {"default": "old"}}})
    overlay = DevflowConfig(tools={"draft-pr": {"plugin": {"default": "new"}}})
    result = merge_config(base, overlay)
    assert result.tools["draft-pr"]["plugin"]["default"] == "new"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_config_io.py -v
```
Expected: `ImportError` or `AttributeError` — `save_config` and `merge_config` not yet defined.

- [ ] **Step 3: Create `devflow_sdk/config/schema.py`**

Move all dataclasses from `devflow_sdk/config.py` verbatim:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class ModelConfig:
    name: str
    pricing: dict | None = None


@dataclass
class GlobalConfig:
    ai_provider: str = "claude"
    models: dict[str, ModelConfig] = field(default_factory=dict)


@dataclass
class DevflowConfig:
    global_config: GlobalConfig = field(default_factory=GlobalConfig)
    tools: dict[str, dict] = field(default_factory=dict)


@dataclass
class PluginConfig(Generic[T]):
    default: str | None = None
    rules: list[T] = field(default_factory=list)
```

- [ ] **Step 4: Create `devflow_sdk/config/io.py`**

```python
from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import TypeVar

from devflow_sdk.config.schema import DevflowConfig, GlobalConfig, ModelConfig

CONFIG_PATH = Path.home() / ".devflow" / "config.json"
_VALID_TIERS = {"fast", "capable"}

T = TypeVar("T")


def _parse_models(models_data: dict, source: str) -> dict[str, ModelConfig]:
    models: dict[str, ModelConfig] = {}
    for tier, entry in models_data.items():
        if tier not in _VALID_TIERS:
            raise ValueError(
                f"{source}: unknown model tier '{tier}'. "
                f"Valid tiers: {', '.join(sorted(_VALID_TIERS))}"
            )
        try:
            name = entry["name"]
        except KeyError as exc:
            raise ValueError(
                f"{source}: models.{tier} entry is missing required 'name' field"
            ) from exc
        pricing = entry.get("pricing")
        if pricing is not None:
            required = {"input", "output", "cache_read", "cache_write"}
            missing = required - pricing.keys()
            if missing:
                raise ValueError(
                    f"{source}: models.{tier}.pricing is missing "
                    f"required keys: {', '.join(sorted(missing))}"
                )
        models[tier] = ModelConfig(name=name, pricing=pricing)
    return models


def _config_to_dict(config: DevflowConfig) -> dict:
    models_dict: dict[str, dict] = {}
    for tier, mc in config.global_config.models.items():
        entry: dict = {"name": mc.name}
        if mc.pricing is not None:
            entry["pricing"] = mc.pricing
        models_dict[tier] = entry
    return {
        "global": {
            "ai_provider": config.global_config.ai_provider,
            "models": models_dict,
        },
        "tools": config.tools,
    }


def load_config(path: Path | None = None) -> DevflowConfig:
    target = path or CONFIG_PATH
    if not target.exists():
        return DevflowConfig()
    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{target} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{target} must contain a JSON object, got {type(data).__name__}"
        )

    if "global" not in data:
        print(
            '[devflow] Warning: config format is outdated. '
            'Wrap your config under a "global" key.',
            file=sys.stderr,
        )
        global_data = data
        tools_data: dict[str, dict] = {}
    else:
        global_data = data.get("global", {})
        tools_data = data.get("tools", {})

    models = _parse_models(global_data.get("models", {}), str(target))
    global_config = GlobalConfig(
        ai_provider=global_data.get("ai_provider", "claude"),
        models=models,
    )
    return DevflowConfig(global_config=global_config, tools=tools_data)


def save_config(config: DevflowConfig, path: Path | None = None) -> None:
    target = path or CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _config_to_dict(config)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".config-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.rename(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def merge_config(base: DevflowConfig, overlay: DevflowConfig) -> DevflowConfig:
    merged_models = {**base.global_config.models, **overlay.global_config.models}
    merged_global = GlobalConfig(
        ai_provider=overlay.global_config.ai_provider or base.global_config.ai_provider,
        models=merged_models,
    )
    merged_tools = {**base.tools, **overlay.tools}
    return DevflowConfig(global_config=merged_global, tools=merged_tools)


def load_tool_config(config: DevflowConfig, tool_name: str, schema_cls: type[T]) -> T:
    raw = config.tools.get(tool_name)
    if raw is None:
        return schema_cls()
    known_fields = {f.name for f in dataclasses.fields(schema_cls)}
    filtered = {k: v for k, v in raw.items() if k in known_fields}
    instance = schema_cls(**filtered)
    if hasattr(instance, "validate"):
        instance.validate()
    return instance
```

- [ ] **Step 5: Create `devflow_sdk/config/__init__.py`**

```python
from devflow_sdk.config.schema import (
    ModelConfig,
    GlobalConfig,
    DevflowConfig,
    PluginConfig,
)
from devflow_sdk.config.io import (
    CONFIG_PATH,
    load_config,
    save_config,
    merge_config,
    load_tool_config,
)

__all__ = [
    "ModelConfig",
    "GlobalConfig",
    "DevflowConfig",
    "PluginConfig",
    "CONFIG_PATH",
    "load_config",
    "save_config",
    "merge_config",
    "load_tool_config",
]
```

- [ ] **Step 6: Delete the old `devflow_sdk/devflow_sdk/config.py`**

```bash
rm devflow-sdk/devflow_sdk/config.py
```

- [ ] **Step 7: Update monkeypatch targets in `devflow_sdk/tests/test_config.py`**

All lines that read:
```python
monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", ...)
```
must change to:
```python
monkeypatch.setattr("devflow_sdk.config.io.CONFIG_PATH", ...)
```

There are 8 such lines (lines 63, 72–73, 83, 96, 111, 121, 131, 141). Make the replacement throughout the file.

- [ ] **Step 8: Run all existing config tests plus new io tests**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_config.py tests/test_config_io.py -v
```
Expected: all green.

- [ ] **Step 9: Run full tool test suite to confirm no regressions**

```bash
uv run --no-project pytest devflow/ -v
```
Expected: all green (tool scripts import `devflow_sdk.config` and see the same symbols via `__init__.py`).

- [ ] **Step 10: Commit**

```bash
git add devflow-sdk/devflow_sdk/config/ devflow-sdk/tests/test_config_io.py devflow-sdk/tests/test_config.py
git commit -m "refactor: move devflow_sdk/config.py into config/ package with save_config and merge_config"
```

---

## Task 2: Move concrete `PluginLoader` to SDK

**Files:**
- Create: `devflow_sdk/devflow_sdk/plugin/plugin_loader_impl.py`
- Create: `devflow_sdk/tests/test_plugin_loader_impl.py`
- Modify: `devflow_sdk/devflow_sdk/plugin/__init__.py`
- Modify: `devflow/plugin-manager/plugin_loader.py`

**Interfaces:**
- Consumes: `devflow_sdk.config.io.CONFIG_PATH` pattern; `PluginLoaderBase`, `PluginEntry` from `devflow_sdk.plugin`
- Produces: `PluginLoader` class importable from `devflow_sdk.plugin.plugin_loader_impl` and re-exported from `devflow_sdk.plugin`; module-level aliases `register`, `unregister`, `list_plugins`, `discover`, `select_plugin` on `PluginLoader()` instance still accessible from `devflow.plugin-manager.plugin_loader`

- [ ] **Step 1: Write failing tests for `PluginLoader` in the SDK**

Create `devflow_sdk/tests/test_plugin_loader_impl.py`:

```python
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
    loader.unregister("does-not-exist")  # should not raise


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

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_plugin_loader_impl.py -v
```
Expected: `ImportError` — `plugin_loader_impl` does not exist yet.

- [ ] **Step 3: Create `devflow_sdk/plugin/plugin_loader_impl.py`**

Copy the entire `PluginLoader` class and its helper functions from `devflow/plugin-manager/plugin_loader.py` verbatim (all imports, `_load_registry`, `_save_registry`, `_atomic_update_registry`, the `PluginLoader` class, and the module-level aliases). Do **not** copy the `if __name__ == "__main__"` block — that stays in the shim.

```python
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

from devflow_sdk.plugin import PluginLoaderBase, PluginEntry
from devflow_sdk.prompts import select

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

- [ ] **Step 4: Re-export `PluginLoader` from `devflow_sdk/plugin/__init__.py`**

Add to the existing imports and `__all__`:

```python
from devflow_sdk.plugin.plugin_base import PluginBase
from devflow_sdk.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin.plugin_loader_impl import PluginLoader   # NEW
from devflow_sdk.plugin.plugin_registry import PluginEntry
from devflow_sdk.plugin.draft_pr_plugin import DraftPrPlugin

__all__ = ["PluginBase", "PluginLoaderBase", "PluginLoader", "PluginEntry", "DraftPrPlugin"]
```

- [ ] **Step 5: Run new plugin_loader_impl tests**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_plugin_loader_impl.py -v
```
Expected: all green.

- [ ] **Step 6: Replace `devflow/plugin-manager/plugin_loader.py` with a shim**

The shim re-exports everything and keeps the `__main__` block so the `devflow-plugin` binary continues to work:

```python
from __future__ import annotations

from devflow_sdk.plugin.plugin_loader_impl import (
    PluginLoader,
    _load_registry,
    _save_registry,
    _atomic_update_registry,
    REGISTRY_PATH,
    REGISTRY_VERSION,
)

_loader = PluginLoader()
register = _loader.register
unregister = _loader.unregister
list_plugins = _loader.list_plugins
discover = _loader.discover
select_plugin = _loader.select_plugin


if __name__ == "__main__":
    import argparse

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
```

- [ ] **Step 7: Run full test suite**

```bash
cd devflow-sdk && uv run --extra dev pytest -v
uv run --no-project pytest devflow/ -v
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add devflow-sdk/devflow_sdk/plugin/plugin_loader_impl.py \
        devflow-sdk/devflow_sdk/plugin/__init__.py \
        devflow-sdk/tests/test_plugin_loader_impl.py \
        devflow/plugin-manager/plugin_loader.py
git commit -m "refactor: move concrete PluginLoader into devflow_sdk; plugin-manager becomes a shim"
```

---

## Task 3: Add `default` parameter to `devflow_sdk.prompts.text()`

**Files:**
- Modify: `devflow_sdk/devflow_sdk/prompts.py`
- Modify: `devflow_sdk/tests/test_prompts.py`

**Interfaces:**
- Produces: `text(message: str, default: str = "") -> str | None` — backward-compatible (callers that omit `default` get the empty-string default, same as before)

- [ ] **Step 1: Write failing test**

Add to `devflow_sdk/tests/test_prompts.py`:

```python
def test_text_passes_default_to_questionary(monkeypatch):
    calls = []

    class FakeText:
        def __init__(self, message, default=""):
            calls.append({"message": message, "default": default})
        def ask(self):
            return "result"

    monkeypatch.setattr("questionary.text", FakeText)
    from devflow_sdk.prompts import text
    result = text("Enter something:", default="pre-filled")
    assert result == "result"
    assert calls[0]["default"] == "pre-filled"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_prompts.py::test_text_passes_default_to_questionary -v
```
Expected: FAIL — `text()` does not accept `default` yet.

- [ ] **Step 3: Update `text()` in `devflow_sdk/prompts.py`**

Change:
```python
def text(message):
    """..."""
    return questionary.text(message).ask()
```
To:
```python
def text(message, default=""):
    """..."""
    return questionary.text(message, default=default).ask()
```

- [ ] **Step 4: Run prompts tests**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_prompts.py -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add devflow-sdk/devflow_sdk/prompts.py devflow-sdk/tests/test_prompts.py
git commit -m "feat: add default parameter to devflow_sdk.prompts.text()"
```

---

## Task 4: Implement `WizardStep` ABC and `run_wizard()`

**Files:**
- Create: `devflow_sdk/devflow_sdk/config/wizard/__init__.py`
- Create: `devflow_sdk/tests/test_wizard.py`

**Interfaces:**
- Consumes: `load_config() -> DevflowConfig`, `save_config(config, path=None) -> None` from `devflow_sdk.config.io`
- Produces: `WizardStep` ABC with `section: str` and `run(current: DevflowConfig) -> DevflowConfig`; `run_wizard(steps: list[WizardStep], path: Path | None = None) -> DevflowConfig`

- [ ] **Step 1: Write failing tests**

Create `devflow_sdk/tests/test_wizard.py`:

```python
import dataclasses
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from devflow_sdk.config import DevflowConfig, GlobalConfig
from devflow_sdk.config.wizard import WizardStep, run_wizard


class _ProviderSwitchStep(WizardStep):
    section = "Test Section"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, ai_provider="opencode"),
        )


def test_wizard_step_is_abstract():
    import inspect
    assert inspect.isabstract(WizardStep)


def test_wizard_step_section_required():
    with pytest.raises(TypeError):
        WizardStep()


def test_run_wizard_calls_steps_in_order(tmp_path):
    order = []

    class StepA(WizardStep):
        section = "A"
        def run(self, current):
            order.append("A")
            return current

    class StepB(WizardStep):
        section = "B"
        def run(self, current):
            order.append("B")
            return current

    config_path = tmp_path / "config.json"
    run_wizard([StepA(), StepB()], path=config_path)
    assert order == ["A", "B"]


def test_run_wizard_saves_final_config(tmp_path):
    config_path = tmp_path / "config.json"
    run_wizard([_ProviderSwitchStep()], path=config_path)
    from devflow_sdk.config import load_config
    result = load_config(path=config_path)
    assert result.global_config.ai_provider == "opencode"


def test_run_wizard_loads_existing_config(tmp_path):
    config_path = tmp_path / "config.json"
    from devflow_sdk.config import save_config
    save_config(
        DevflowConfig(global_config=GlobalConfig(ai_provider="opencode")),
        path=config_path,
    )

    seen = []

    class InspectStep(WizardStep):
        section = "Inspect"
        def run(self, current):
            seen.append(current.global_config.ai_provider)
            return current

    run_wizard([InspectStep()], path=config_path)
    assert seen[0] == "opencode"


def test_run_wizard_step_return_propagates_to_next(tmp_path):
    config_path = tmp_path / "config.json"

    class SetProvider(WizardStep):
        section = "Provider"
        def run(self, current):
            return dataclasses.replace(
                current,
                global_config=dataclasses.replace(current.global_config, ai_provider="opencode"),
            )

    class AssertProvider(WizardStep):
        section = "Assert"
        def run(self, current):
            assert current.global_config.ai_provider == "opencode"
            return current

    run_wizard([SetProvider(), AssertProvider()], path=config_path)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_wizard.py -v
```
Expected: `ImportError` — `devflow_sdk.config.wizard` does not exist yet.

- [ ] **Step 3: Create `devflow_sdk/config/wizard/__init__.py`**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from devflow_sdk.config.io import load_config, save_config
from devflow_sdk.config.schema import DevflowConfig


class WizardStep(ABC):
    section: str

    @abstractmethod
    def run(self, current: DevflowConfig) -> DevflowConfig:
        ...


def run_wizard(steps: list[WizardStep], path: Path | None = None) -> DevflowConfig:
    config = load_config(path=path)
    for step in steps:
        print(f"\n=== {step.section} ===")
        config = step.run(config)
    save_config(config, path=path)
    return config
```

- [ ] **Step 4: Run wizard tests**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_wizard.py -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add devflow-sdk/devflow_sdk/config/wizard/__init__.py devflow-sdk/tests/test_wizard.py
git commit -m "feat: add WizardStep ABC and run_wizard() to devflow_sdk.config.wizard"
```

---

## Task 5: Implement `ProviderStep` and `ModelsStep`

**Files:**
- Create: `devflow_sdk/devflow_sdk/config/wizard/global_steps.py`
- Create: `devflow_sdk/tests/test_wizard_global_steps.py`

**Interfaces:**
- Consumes: `WizardStep` from `devflow_sdk.config.wizard`; `DevflowConfig`, `GlobalConfig`, `ModelConfig` from `devflow_sdk.config.schema`; `select`, `text`, `checkbox`, `Choice` from `devflow_sdk.prompts`
- Produces: `ProviderStep(WizardStep)`, `ModelsStep(WizardStep)` — importable from `devflow_sdk.config.wizard.global_steps`

- [ ] **Step 1: Write failing tests**

Create `devflow_sdk/tests/test_wizard_global_steps.py`:

```python
import dataclasses
import pytest
from unittest.mock import patch

from devflow_sdk.config import DevflowConfig, GlobalConfig, ModelConfig
from devflow_sdk.config.wizard.global_steps import ProviderStep, ModelsStep


def make_config(provider="claude", models=None):
    return DevflowConfig(
        global_config=GlobalConfig(
            ai_provider=provider,
            models=models or {
                "fast": ModelConfig(name="haiku"),
                "capable": ModelConfig(name="sonnet"),
            },
        )
    )


class TestProviderStep:
    def test_section_label(self):
        assert ProviderStep().section == "AI Provider"

    def test_switches_provider_to_opencode(self):
        step = ProviderStep()
        current = make_config(provider="claude")
        # select() returns "opencode" — simulate user choosing opencode
        with patch("devflow_sdk.config.wizard.global_steps.select", return_value="opencode"):
            result = step.run(current)
        assert result.global_config.ai_provider == "opencode"

    def test_preserves_provider_when_unchanged(self):
        step = ProviderStep()
        current = make_config(provider="opencode")
        with patch("devflow_sdk.config.wizard.global_steps.select", return_value="opencode"):
            result = step.run(current)
        assert result.global_config.ai_provider == "opencode"

    def test_other_fields_untouched(self):
        step = ProviderStep()
        current = make_config(provider="claude")
        with patch("devflow_sdk.config.wizard.global_steps.select", return_value="opencode"):
            result = step.run(current)
        assert result.global_config.models == current.global_config.models
        assert result.tools == current.tools


class TestModelsStep:
    def test_section_label(self):
        assert ModelsStep().section == "Model Configuration"

    def test_updates_fast_model_name(self):
        step = ModelsStep()
        current = make_config()
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["new-haiku", "0.8", "4.0", "0.08", "1.0"]),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].name == "new-haiku"

    def test_skips_unselected_tier(self):
        step = ModelsStep()
        current = make_config()
        # Only "capable" selected — "fast" should be unchanged
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["capable"]),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["new-sonnet", "3.0", "15.0", "0.3", "3.75"]),
        ):
            result = step.run(current)
        assert result.global_config.models["fast"].name == "haiku"
        assert result.global_config.models["capable"].name == "new-sonnet"

    def test_no_tiers_selected_leaves_models_unchanged(self):
        step = ModelsStep()
        current = make_config()
        with patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=[]):
            result = step.run(current)
        assert result.global_config.models == current.global_config.models

    def test_pricing_stored_when_provided(self):
        step = ModelsStep()
        current = make_config(models={"fast": ModelConfig(name="haiku")})
        with (
            patch("devflow_sdk.config.wizard.global_steps.checkbox", return_value=["fast"]),
            patch("devflow_sdk.config.wizard.global_steps.text", side_effect=["haiku", "0.8", "4.0", "0.08", "1.0"]),
        ):
            result = step.run(current)
        pricing = result.global_config.models["fast"].pricing
        assert pricing["input"] == 0.8
        assert pricing["output"] == 4.0
        assert pricing["cache_read"] == 0.08
        assert pricing["cache_write"] == 1.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_wizard_global_steps.py -v
```
Expected: `ImportError` — module not yet created.

- [ ] **Step 3: Create `devflow_sdk/config/wizard/global_steps.py`**

```python
from __future__ import annotations

import dataclasses

from devflow_sdk.config.schema import DevflowConfig, GlobalConfig, ModelConfig
from devflow_sdk.config.wizard import WizardStep
from devflow_sdk.prompts import Choice, checkbox, select, text

_PROVIDER_CHOICES = ["claude", "opencode"]


class ProviderStep(WizardStep):
    section = "AI Provider"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        current_provider = current.global_config.ai_provider
        choices = [
            Choice(p, checked=(p == current_provider))
            for p in _PROVIDER_CHOICES
        ]
        provider = select("Which AI provider should devflow use?", choices=choices)
        if provider is None:
            return current
        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, ai_provider=provider),
        )


class ModelsStep(WizardStep):
    section = "Model Configuration"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        existing = current.global_config.models
        tier_choices = [
            Choice(
                tier,
                label=f"{tier.capitalize()}  (current: {existing[tier].name if tier in existing else 'not set'})",
                checked=True,
            )
            for tier in ("fast", "capable")
        ]
        selected_tiers = checkbox("Select model tiers to configure:", choices=tier_choices)
        if not selected_tiers:
            return current

        updated_models = dict(existing)
        for tier in selected_tiers:
            current_name = existing[tier].name if tier in existing else ""
            current_pricing = existing[tier].pricing if tier in existing else None

            name = text(f"{tier.capitalize()} model name:", default=current_name)
            if name is None:
                continue

            input_price = text(
                f"{tier.capitalize()} input price ($/M tokens):",
                default=str(current_pricing["input"]) if current_pricing else "",
            )
            output_price = text(
                f"{tier.capitalize()} output price ($/M tokens):",
                default=str(current_pricing["output"]) if current_pricing else "",
            )
            cache_read_price = text(
                f"{tier.capitalize()} cache read price ($/M tokens):",
                default=str(current_pricing["cache_read"]) if current_pricing else "",
            )
            cache_write_price = text(
                f"{tier.capitalize()} cache write price ($/M tokens):",
                default=str(current_pricing["cache_write"]) if current_pricing else "",
            )

            pricing: dict | None = None
            if all(p for p in [input_price, output_price, cache_read_price, cache_write_price]):
                pricing = {
                    "input": float(input_price),
                    "output": float(output_price),
                    "cache_read": float(cache_read_price),
                    "cache_write": float(cache_write_price),
                }

            updated_models[tier] = ModelConfig(name=name, pricing=pricing)

        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, models=updated_models),
        )
```

- [ ] **Step 4: Run global steps tests**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_wizard_global_steps.py -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add devflow-sdk/devflow_sdk/config/wizard/global_steps.py \
        devflow-sdk/tests/test_wizard_global_steps.py
git commit -m "feat: add ProviderStep and ModelsStep wizard steps"
```

---

## Task 6: Implement `DraftPrWizardStep` and migrate `DraftPrConfig`

**Files:**
- Create: `devflow_sdk/devflow_sdk/config/wizard/tools/__init__.py`
- Create: `devflow_sdk/devflow_sdk/config/wizard/tools/draft_pr.py`
- Create: `devflow_sdk/tests/test_wizard_draft_pr.py`
- Modify: `devflow/draft-pr/config.py` (shim)

**Interfaces:**
- Consumes: `WizardStep`, `run_wizard`; `PluginLoader` from `devflow_sdk.plugin.plugin_loader_impl`; `select`, `checkbox`, `confirm`, `text`, `Choice` from `devflow_sdk.prompts`
- Produces: `DraftPrConfig`, `DirectoryRule`, `resolve_plugin()` importable from `devflow_sdk.config.wizard.tools.draft_pr`; `ALL_TOOL_STEPS: list[WizardStep]` importable from `devflow_sdk.config.wizard.tools`

- [ ] **Step 1: Write failing tests**

Create `devflow_sdk/tests/test_wizard_draft_pr.py`:

```python
import dataclasses
import pytest
from unittest.mock import MagicMock, patch

from devflow_sdk.config import DevflowConfig, GlobalConfig
from devflow_sdk.config.wizard.tools.draft_pr import (
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
        from devflow_sdk.config import load_tool_config, DevflowConfig, GlobalConfig
        config = DevflowConfig(global_config=GlobalConfig(), tools={"draft-pr": raw})
        draft_cfg = load_tool_config(config, "draft-pr", DraftPrConfig)
        assert draft_cfg.plugin.default == "smoke-check"
        assert draft_cfg.plugin.rules[0].paths == ["/src"]

    def test_validate_raises_when_no_default_and_no_rules(self):
        cfg = DraftPrConfig()
        with pytest.raises(ValueError, match="plugin config must have"):
            cfg.validate()

    def test_validate_passes_with_default(self):
        from devflow_sdk.config.schema import PluginConfig
        cfg = DraftPrConfig(plugin=PluginConfig(default="smoke-check"))
        cfg.validate()  # should not raise

    def test_rules_sorted_by_path_length_descending(self):
        from devflow_sdk.config.schema import PluginConfig
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
        from devflow_sdk.config.schema import PluginConfig
        rules = [DirectoryRule(paths=["/Users/foo/projects"], plugin="proj-plugin")]
        cfg = DraftPrConfig(plugin=PluginConfig(default="default-plugin", rules=rules))
        assert resolve_plugin(cfg, "/Users/foo/projects/myrepo") == "proj-plugin"

    def test_falls_back_to_default(self):
        from devflow_sdk.config.schema import PluginConfig
        cfg = DraftPrConfig(plugin=PluginConfig(default="fallback"))
        assert resolve_plugin(cfg, "/unmatched/path") == "fallback"


class TestDraftPrWizardStep:
    def test_section_label(self):
        assert DraftPrWizardStep().section == "draft-pr: Plugin Routing"

    def test_skips_when_no_plugins_registered(self, capsys):
        step = DraftPrWizardStep()
        current = _make_config()
        with patch(
            "devflow_sdk.config.wizard.tools.draft_pr.PluginLoader.list_plugins",
            return_value={},
        ):
            result = step.run(current)
        assert result == current
        captured = capsys.readouterr()
        assert "No plugins" in captured.out

    def test_sets_default_plugin(self):
        step = DraftPrWizardStep()
        current = _make_config()
        plugins = {"smoke-check": _make_entry("smoke-check")}
        with (
            patch("devflow_sdk.config.wizard.tools.draft_pr.PluginLoader.list_plugins", return_value=plugins),
            patch("devflow_sdk.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.config.wizard.tools.draft_pr.checkbox", return_value=[]),
            patch("devflow_sdk.config.wizard.tools.draft_pr.confirm", return_value=False),
        ):
            result = step.run(current)
        assert result.tools["draft-pr"]["plugin"]["default"] == "smoke-check"

    def test_existing_rules_kept_when_all_selected(self):
        step = DraftPrWizardStep()
        existing_tools = {
            "plugin": {
                "default": "smoke-check",
                "rules": [{"paths": ["/src"], "plugin": "other-plugin"}],
            }
        }
        current = _make_config(draft_pr_tools=existing_tools)
        plugins = {
            "smoke-check": _make_entry("smoke-check"),
            "other-plugin": _make_entry("other-plugin"),
        }
        rule = DirectoryRule(paths=["/src"], plugin="other-plugin")
        with (
            patch("devflow_sdk.config.wizard.tools.draft_pr.PluginLoader.list_plugins", return_value=plugins),
            patch("devflow_sdk.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.config.wizard.tools.draft_pr.checkbox", return_value=[rule]),
            patch("devflow_sdk.config.wizard.tools.draft_pr.confirm", return_value=False),
        ):
            result = step.run(current)
        rules = result.tools["draft-pr"]["plugin"]["rules"]
        assert any(r["paths"] == ["/src"] for r in rules)

    def test_new_rule_added(self):
        step = DraftPrWizardStep()
        current = _make_config()
        plugins = {"smoke-check": _make_entry("smoke-check")}
        with (
            patch("devflow_sdk.config.wizard.tools.draft_pr.PluginLoader.list_plugins", return_value=plugins),
            patch("devflow_sdk.config.wizard.tools.draft_pr.select", return_value="smoke-check"),
            patch("devflow_sdk.config.wizard.tools.draft_pr.checkbox", return_value=[]),
            patch("devflow_sdk.config.wizard.tools.draft_pr.confirm", side_effect=[True, False]),
            patch("devflow_sdk.config.wizard.tools.draft_pr.text", return_value="/work/myproject"),
        ):
            result = step.run(current)
        rules = result.tools["draft-pr"]["plugin"]["rules"]
        assert any("/work/myproject" in r["paths"] for r in rules)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_wizard_draft_pr.py -v
```
Expected: `ImportError` — module not yet created.

- [ ] **Step 3: Create `devflow_sdk/config/wizard/tools/draft_pr.py`**

```python
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from devflow_sdk.config.schema import DevflowConfig, PluginConfig
from devflow_sdk.config.wizard import WizardStep
from devflow_sdk.plugin.plugin_loader_impl import PluginLoader
from devflow_sdk.prompts import Choice, checkbox, confirm, select, text


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
        if any(cwd.startswith(p) for p in rule.paths):
            return rule.plugin
    return config.plugin.default


def _rules_to_dicts(rules: list[DirectoryRule]) -> list[dict]:
    return [{"paths": r.paths, "plugin": r.plugin} for r in rules]


class DraftPrWizardStep(WizardStep):
    section = "draft-pr: Plugin Routing"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        loader = PluginLoader()
        available = loader.list_plugins()
        if not available:
            print("  No plugins registered — skipping draft-pr plugin routing configuration.")
            return current

        plugin_names = list(available.keys())

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
                    r,
                    label=f"{', '.join(r.paths)} → {r.plugin}",
                    checked=True,
                )
                for r in current_rules
            ]
            kept_rules = checkbox("Which path rules should be kept?", choices=rule_choices) or []

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

- [ ] **Step 4: Create `devflow_sdk/config/wizard/tools/__init__.py`**

```python
from devflow_sdk.config.wizard.tools.draft_pr import DraftPrWizardStep
from devflow_sdk.config.wizard import WizardStep

ALL_TOOL_STEPS: list[WizardStep] = [DraftPrWizardStep()]
```

- [ ] **Step 5: Run draft_pr wizard tests**

```bash
cd devflow-sdk && uv run --extra dev pytest tests/test_wizard_draft_pr.py -v
```
Expected: all green.

- [ ] **Step 6: Replace `devflow/draft-pr/config.py` with a shim**

```python
from devflow_sdk.config.wizard.tools.draft_pr import (  # noqa: F401
    DraftPrConfig,
    DirectoryRule,
    resolve_plugin,
)
```

- [ ] **Step 7: Run full test suite to confirm draft-pr tool still works**

```bash
cd devflow-sdk && uv run --extra dev pytest -v
uv run --no-project pytest devflow/ -v
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add devflow-sdk/devflow_sdk/config/wizard/tools/ \
        devflow-sdk/tests/test_wizard_draft_pr.py \
        devflow/draft-pr/config.py
git commit -m "feat: add DraftPrWizardStep; move DraftPrConfig into SDK; draft-pr/config.py becomes shim"
```

---

## Task 7: Add `devflow-config` script + version bump + Homebrew wiring

**Files:**
- Create: `devflow/devflow-config/devflow-config.py`
- Modify: `devflow-sdk/pyproject.toml`
- Modify: `homebrew-devflow/Formula/devflow.rb`

**Interfaces:**
- Consumes: `run_wizard`, `ProviderStep`, `ModelsStep` from `devflow_sdk.config.wizard.*`; `ALL_TOOL_STEPS` from `devflow_sdk.config.wizard.tools`

- [ ] **Step 1: Create `devflow/devflow-config/devflow-config.py`**

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

vendor_dir = Path(__file__).parent.parent / "vendor"
for whl in sorted(vendor_dir.glob("*.whl")):
    sys.path.insert(0, str(whl))

from devflow_sdk.config.wizard import run_wizard
from devflow_sdk.config.wizard.global_steps import ModelsStep, ProviderStep
from devflow_sdk.config.wizard.tools import ALL_TOOL_STEPS


def main():
    steps = [ProviderStep(), ModelsStep()] + ALL_TOOL_STEPS
    run_wizard(steps)
    print("\nConfig saved to ~/.devflow/config.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script imports cleanly against the dev SDK**

```bash
PYTHONPATH=devflow-sdk python3 devflow/devflow-config/devflow-config.py --help 2>&1 | head -5 || true
uv run --no-project python3 -c "
import sys; sys.path.insert(0, 'devflow-sdk')
from devflow_sdk.config.wizard import run_wizard
from devflow_sdk.config.wizard.global_steps import ProviderStep, ModelsStep
from devflow_sdk.config.wizard.tools import ALL_TOOL_STEPS
print('imports OK')
"
```
Expected: prints `imports OK`.

- [ ] **Step 3: Bump `devflow-sdk` version to `1.1.0`**

In `devflow-sdk/pyproject.toml`, change:
```toml
version = "1.0.1"
```
to:
```toml
version = "1.1.0"
```

- [ ] **Step 4: Add `devflow-config` to `homebrew-devflow/Formula/devflow.rb`**

Inside the `def install` block, after the existing `%w[draft-pr ...]` loop and the `devflow-plugin` block, add:

```ruby
    (bin/"devflow-config").write <<~BASH
      #!/bin/bash
      export PYTHONPATH="#{libexec}/plugin-manager:#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
      exec python3 "#{libexec}/devflow-config/devflow-config.py" "$@"
    BASH
    (bin/"devflow-config").chmod 0755
```

Also update the `resource "devflow-sdk"` block version from `1.0.1` to `1.1.0`. The `url` and `sha256` are placeholders that must be updated after the SDK wheel is built and released — add a comment:

```ruby
  # TODO: update url and sha256 after releasing devflow-sdk/v1.1.0
  resource "devflow-sdk" do
    url "https://github.com/captainwonderwall/devflow-platform/releases/download/devflow-sdk%2Fv1.1.0/devflow_sdk-1.1.0-py3-none-any.whl"
    sha256 "PLACEHOLDER_UPDATE_AFTER_RELEASE"
  end
```

- [ ] **Step 5: Run full test suite one final time**

```bash
cd devflow-sdk && uv run --extra dev pytest -v
uv run --no-project pytest devflow/ -v
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add devflow/devflow-config/devflow-config.py \
        devflow-sdk/pyproject.toml \
        homebrew-devflow/Formula/devflow.rb
git commit -m "feat: add devflow-config interactive wizard binary; bump devflow-sdk to 1.1.0"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by |
|---|---|
| Interactive wizard, pre-populated | Tasks 4–6: `run_wizard` loads existing, steps receive current |
| `devflow_sdk/config/` package layout | Task 1 |
| `WizardStep` ABC + `run_wizard` | Task 4 |
| `ProviderStep` + `ModelsStep` using SDK prompts | Task 5 |
| `DraftPrWizardStep` with `checkbox`, `select`, `confirm`, `text` | Task 6 |
| `DraftPrConfig` / `DirectoryRule` moved to SDK | Task 6 |
| Concrete `PluginLoader` moved to SDK | Task 2 |
| `devflow/draft-pr/config.py` shim | Task 6 |
| `devflow/plugin-manager/plugin_loader.py` shim | Task 2 |
| `ALL_TOOL_STEPS` registry | Task 6 |
| `devflow-config` binary | Task 7 |
| Homebrew formula updated | Task 7 |
| SDK version bumped to 1.1.0 | Task 7 |
| `text()` `default` parameter | Task 3 |
| All existing tool scripts unchanged | Verified in Tasks 1, 2, 6 step 7 |
| Atomic `save_config` | Task 1 (`io.py`) |
| `merge_config` | Task 1 (`io.py`) |

**Placeholder scan:** No TBD or TODO in task steps.

**Type consistency:**
- `DevflowConfig.global_config: GlobalConfig` used consistently (not `global_`)
- `GlobalConfig.models: dict[str, ModelConfig]` used consistently
- `run_wizard(steps: list[WizardStep], path: Path | None = None) -> DevflowConfig` consistent across Tasks 4 and 7
- `WizardStep.run(current: DevflowConfig) -> DevflowConfig` consistent across Tasks 4, 5, 6
- `save_config(config: DevflowConfig, path: Path | None = None)` consistent across Tasks 1 and 4
- `load_config(path: Path | None = None) -> DevflowConfig` consistent across Tasks 1 and 4

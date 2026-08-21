# AI Provider Config Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a two-layer config schema (`global` + per-tool) to the devflow-sdk, with a uniform `PluginConfig[T]` convention and a `load_tool_config` helper, then wire `draft-pr` to use it.

**Architecture:** `DevflowConfig` gains a `global_config: GlobalConfig` field (provider + models) and a `tools: dict[str, dict]` field (opaque per-tool dicts). The SDK provides `PluginConfig[T]` as a generic container and `load_tool_config` to hydrate and validate any tool's config. `draft-pr` defines its own `DraftPrConfig` with `DirectoryRule`-based plugin routing.

**Tech Stack:** Python 3.10+, dataclasses, typing.Generic — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-21-ai-provider-config-rework-design.md`

## Global Constraints

- No new third-party dependencies — use only stdlib dataclasses and typing.
- `load_config` must remain backwards-compatible with flat legacy configs (no `global` key).
- New fields on tool config dataclasses must always have default values.
- `get_provider` signature changes from `DevflowConfig` → `GlobalConfig`; all callers must be updated in the same task.
- All test commands run from the package directory containing `pytest.ini` or `pyproject.toml`.

---

### Task 1: Rework `devflow_sdk/config.py`

**Files:**
- Modify: `devflow-sdk/devflow_sdk/config.py`
- Create: `devflow-sdk/tests/test_config.py`

**Interfaces:**
- Produces:
  - `GlobalConfig(ai_provider: str = "claude", models: dict[str, ModelConfig] = {})` — dataclass
  - `DevflowConfig(global_config: GlobalConfig = GlobalConfig(), tools: dict[str, dict] = {})` — dataclass
  - `PluginConfig(default: str | None = None, rules: list[T] = [])` — generic dataclass
  - `load_config() -> DevflowConfig` — reads `~/.devflow/config.json`; auto-migrates flat legacy format with a deprecation warning to stderr
  - `load_tool_config(config: DevflowConfig, tool_name: str, schema_cls: type[T]) -> T` — extracts `config.tools[tool_name]`, filters to known fields, instantiates, calls `instance.validate()` if defined

- [ ] **Step 1: Write failing tests for `GlobalConfig`, `DevflowConfig`, and `PluginConfig` types**

Create `devflow-sdk/tests/test_config.py`:

```python
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from devflow_sdk.config import (
    DevflowConfig,
    GlobalConfig,
    ModelConfig,
    PluginConfig,
    load_config,
    load_tool_config,
)


# ── Type shape ────────────────────────────────────────────────────────────────

def test_global_config_defaults():
    cfg = GlobalConfig()
    assert cfg.ai_provider == "claude"
    assert cfg.models == {}


def test_devflow_config_defaults():
    cfg = DevflowConfig()
    assert isinstance(cfg.global_config, GlobalConfig)
    assert cfg.tools == {}


def test_plugin_config_defaults():
    pc = PluginConfig()
    assert pc.default is None
    assert pc.rules == []


def test_plugin_config_holds_typed_rules():
    @dataclasses.dataclass
    class MyRule:
        key: str

    pc = PluginConfig(default="fallback", rules=[MyRule(key="a")])
    assert pc.rules[0].key == "a"
    assert pc.default == "fallback"


# ── load_config: new two-layer format ─────────────────────────────────────────

def test_load_config_new_format(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "global": {
            "ai_provider": "opencode",
            "models": {
                "fast": {"name": "my-fast-model"},
            }
        },
        "tools": {
            "draft-pr": {"title_format": "feat: {title}"}
        }
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)

    result = load_config()
    assert result.global_config.ai_provider == "opencode"
    assert result.global_config.models["fast"].name == "my-fast-model"
    assert result.tools["draft-pr"]["title_format"] == "feat: {title}"


def test_load_config_missing_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "devflow_sdk.config.CONFIG_PATH", tmp_path / "nonexistent.json"
    )
    result = load_config()
    assert result.global_config.ai_provider == "claude"
    assert result.tools == {}


def test_load_config_empty_tools(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"global": {"ai_provider": "claude"}}))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    result = load_config()
    assert result.tools == {}


# ── load_config: legacy flat format ──────────────────────────────────────────

def test_load_config_legacy_flat_format_migrates(tmp_path, monkeypatch, capsys):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "ai_provider": "opencode",
        "models": {"fast": {"name": "legacy-model"}}
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)

    result = load_config()
    assert result.global_config.ai_provider == "opencode"
    assert result.global_config.models["fast"].name == "legacy-model"
    assert result.tools == {}
    err = capsys.readouterr().err
    assert "outdated" in err


# ── load_config: validation errors ────────────────────────────────────────────

def test_load_config_invalid_json_raises(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{bad json")
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    with pytest.raises(ValueError, match="not valid JSON"):
        load_config()


def test_load_config_unknown_tier_raises(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "global": {"models": {"turbo": {"name": "x"}}}
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    with pytest.raises(ValueError, match="unknown model tier 'turbo'"):
        load_config()


def test_load_config_missing_model_name_raises(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "global": {"models": {"fast": {"pricing": None}}}
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    with pytest.raises(ValueError, match="missing required 'name' field"):
        load_config()


def test_load_config_incomplete_pricing_raises(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "global": {"models": {"fast": {"name": "m", "pricing": {"input": 1.0}}}}
    }))
    monkeypatch.setattr("devflow_sdk.config.CONFIG_PATH", cfg_file)
    with pytest.raises(ValueError, match="pricing is missing required keys"):
        load_config()


# ── load_tool_config ──────────────────────────────────────────────────────────

def test_load_tool_config_returns_typed_instance():
    @dataclasses.dataclass
    class MyConfig:
        title: str = "default"

    cfg = DevflowConfig(tools={"my-tool": {"title": "hello"}})
    result = load_tool_config(cfg, "my-tool", MyConfig)
    assert isinstance(result, MyConfig)
    assert result.title == "hello"


def test_load_tool_config_missing_tool_returns_defaults_without_calling_validate():
    @dataclasses.dataclass
    class MyConfig:
        title: str = "default"

        def validate(self):
            raise ValueError("should not be called for unconfigured tools")

    cfg = DevflowConfig(tools={})
    result = load_tool_config(cfg, "missing-tool", MyConfig)
    assert result.title == "default"  # no exception means validate was not called


def test_load_tool_config_ignores_unknown_keys():
    @dataclasses.dataclass
    class MyConfig:
        title: str = "default"

    cfg = DevflowConfig(tools={"t": {"title": "hi", "unknown_key": "boom"}})
    result = load_tool_config(cfg, "t", MyConfig)
    assert result.title == "hi"


def test_load_tool_config_calls_validate_when_defined():
    @dataclasses.dataclass
    class StrictConfig:
        value: int = 0

        def validate(self):
            if self.value < 0:
                raise ValueError("value must be non-negative")

    cfg = DevflowConfig(tools={"t": {"value": -1}})
    with pytest.raises(ValueError, match="non-negative"):
        load_tool_config(cfg, "t", StrictConfig)


def test_load_tool_config_skips_validate_when_absent():
    @dataclasses.dataclass
    class SimpleConfig:
        value: int = 0

    cfg = DevflowConfig(tools={"t": {"value": 5}})
    result = load_tool_config(cfg, "t", SimpleConfig)
    assert result.value == 5
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd devflow-sdk && python -m pytest tests/test_config.py -v 2>&1 | head -40
```

Expected: ImportError or multiple FAILs (types don't exist yet).

- [ ] **Step 3: Rewrite `devflow_sdk/config.py`**

Replace the entire file:

```python
from __future__ import annotations

import dataclasses
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

CONFIG_PATH = Path.home() / ".devflow" / "config.json"

T = TypeVar("T")

_VALID_TIERS = {"fast", "capable"}


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


def load_config() -> DevflowConfig:
    if not CONFIG_PATH.exists():
        return DevflowConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{CONFIG_PATH} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{CONFIG_PATH} must contain a JSON object, got {type(data).__name__}"
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

    models = _parse_models(global_data.get("models", {}), str(CONFIG_PATH))
    global_config = GlobalConfig(
        ai_provider=global_data.get("ai_provider", "claude"),
        models=models,
    )
    return DevflowConfig(global_config=global_config, tools=tools_data)


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

- [ ] **Step 4: Run tests and confirm they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_config.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add devflow-sdk/devflow_sdk/config.py devflow-sdk/tests/test_config.py
git commit -m "feat: rework DevflowConfig to global+tools schema with PluginConfig and load_tool_config"
```

---

### Task 2: Update `get_provider` and all callers

`get_provider` currently accepts `DevflowConfig` but now must accept `GlobalConfig`. Three call sites need updating: `ai.py` (×2) and `apply_changes.py` (×1). Existing tests in `test_ai_providers.py` also need updating.

**Files:**
- Modify: `devflow-sdk/devflow_sdk/ai_providers/__init__.py`
- Modify: `devflow-sdk/devflow_sdk/ai.py`
- Modify: `devflow/address-pr/apply_changes.py`
- Modify: `devflow-sdk/tests/test_ai_providers.py`

**Interfaces:**
- Consumes: `GlobalConfig` from Task 1
- Produces: `get_provider(global_config: GlobalConfig) -> AiProvider`

- [ ] **Step 1: Update the three existing `get_provider` tests in `test_ai_providers.py`**

Find the block starting at line 156 in `devflow-sdk/tests/test_ai_providers.py`. Replace it:

```python
from devflow_sdk.ai_providers import get_provider
from devflow_sdk.config import GlobalConfig


def test_get_provider_claude():
    provider = get_provider(GlobalConfig(ai_provider="claude"))
    assert provider.name == "claude"


def test_get_provider_opencode():
    provider = get_provider(GlobalConfig(ai_provider="opencode"))
    assert provider.name == "opencode"


def test_get_provider_unknown_raises_with_valid_names_listed():
    with pytest.raises(ValueError, match="claude"):
        get_provider(GlobalConfig(ai_provider="bogus"))
```

- [ ] **Step 2: Run the updated tests to confirm they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_ai_providers.py::test_get_provider_claude tests/test_ai_providers.py::test_get_provider_opencode tests/test_ai_providers.py::test_get_provider_unknown_raises_with_valid_names_listed -v
```

Expected: FAIL — `get_provider` still expects `DevflowConfig`.

- [ ] **Step 3: Update `get_provider` in `devflow_sdk/ai_providers/__init__.py`**

Change the import and signature (the body logic is unchanged — it reads `.ai_provider` and `.models` which both exist on `GlobalConfig`):

```python
import re

from devflow_sdk.ai_providers.claude_provider import ClaudeProvider
from devflow_sdk.ai_providers.opencode_provider import OpenCodeProvider
from devflow_sdk.config import GlobalConfig

_PROVIDERS = {
    "claude": ClaudeProvider,
    "opencode": OpenCodeProvider,
}

_DATE_SUFFIX_RE = re.compile(r'-\d{8}$')


def get_provider(config: GlobalConfig):
    provider_cls = _PROVIDERS.get(config.ai_provider)
    if provider_cls is None:
        allowed = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(
            f"Unknown AI_PROVIDER '{config.ai_provider}'. Valid providers: {allowed}."
        )
    provider = provider_cls()
    if config.models:
        merged_models = dict(provider.models)
        merged_pricing = dict(provider.pricing)
        for tier, model_config in config.models.items():
            merged_models[tier] = model_config.name
            if model_config.pricing is not None:
                merged_pricing[_DATE_SUFFIX_RE.sub('', model_config.name)] = model_config.pricing
        provider.models = merged_models
        provider.pricing = merged_pricing
    return provider
```

- [ ] **Step 4: Update the two call sites in `devflow-sdk/devflow_sdk/ai.py`**

At line 48, change:
```python
        provider = get_provider(config)
```
to:
```python
        provider = get_provider(config.global_config)
```

At line 78, change:
```python
        provider = get_provider(config)
```
to:
```python
        provider = get_provider(config.global_config)
```

- [ ] **Step 5: Update the call site in `devflow/address-pr/apply_changes.py`**

At line 252, change:
```python
                provider = get_provider(config)
```
to:
```python
                provider = get_provider(config.global_config)
```

- [ ] **Step 6: Run the updated tests to confirm they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_ai_providers.py -v
```

Expected: all green including the three updated tests.

- [ ] **Step 7: Run the full SDK test suite to catch any other breakage**

```bash
cd devflow-sdk && python -m pytest -v
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add devflow-sdk/devflow_sdk/ai_providers/__init__.py \
        devflow-sdk/devflow_sdk/ai.py \
        devflow/address-pr/apply_changes.py \
        devflow-sdk/tests/test_ai_providers.py
git commit -m "refactor: update get_provider to accept GlobalConfig; update all callers"
```

---

### Task 3: Add `draft-pr` tool config and wire it into the tool

**Files:**
- Create: `devflow/draft-pr/config.py`
- Create: `devflow/draft-pr/tests/test_draft_pr_config.py`
- Modify: `devflow/draft-pr/draft-pr.py`

**Interfaces:**
- Consumes:
  - `PluginConfig` from Task 1 (`from devflow_sdk.config import PluginConfig`)
  - `load_config`, `load_tool_config` from Task 1
- Produces:
  - `DirectoryRule(paths: list[str], plugin: str)` — dataclass
  - `DraftPrConfig(plugin: PluginConfig[DirectoryRule] = PluginConfig())` — dataclass with `__post_init__` sorting and `validate()`
  - `resolve_plugin(config: DraftPrConfig, cwd: str) -> str | None`

**Notes on deserialization:** `load_tool_config` passes the raw JSON dict value for `"plugin"` as a plain `dict` to `DraftPrConfig.__init__`. `DraftPrConfig.__post_init__` must detect `isinstance(self.plugin, dict)` and convert it to a `PluginConfig[DirectoryRule]`.

- [ ] **Step 1: Write failing tests for `DraftPrConfig` and `resolve_plugin`**

Create `devflow/draft-pr/tests/test_draft_pr_config.py`:

```python
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from config import DirectoryRule, DraftPrConfig, resolve_plugin
from devflow_sdk.config import DevflowConfig, PluginConfig, load_tool_config


# ── DirectoryRule ─────────────────────────────────────────────────────────────

def test_directory_rule_fields():
    rule = DirectoryRule(paths=["frontend/", "ui/"], plugin="frontend-pr")
    assert rule.paths == ["frontend/", "ui/"]
    assert rule.plugin == "frontend-pr"


# ── DraftPrConfig defaults ────────────────────────────────────────────────────

def test_draft_pr_config_defaults():
    cfg = DraftPrConfig()
    assert cfg.plugin.default is None
    assert cfg.plugin.rules == []


# ── DraftPrConfig: raw dict deserialization ───────────────────────────────────

def test_draft_pr_config_hydrates_plugin_from_dict():
    raw_plugin = {
        "default": "default-pr",
        "rules": [
            {"paths": ["frontend/", "ui/"], "plugin": "frontend-pr"},
            {"paths": ["backend/"], "plugin": "backend-pr"},
        ]
    }
    cfg = DraftPrConfig(plugin=raw_plugin)
    assert cfg.plugin.default == "default-pr"
    assert len(cfg.plugin.rules) == 2
    assert isinstance(cfg.plugin.rules[0], DirectoryRule)


# ── DraftPrConfig: sorting ────────────────────────────────────────────────────

def test_draft_pr_config_sorts_rules_longest_path_first():
    raw_plugin = {
        "rules": [
            {"paths": ["a/"], "plugin": "short"},
            {"paths": ["a/very/long/path/"], "plugin": "long"},
            {"paths": ["a/medium/"], "plugin": "medium"},
        ]
    }
    cfg = DraftPrConfig(plugin=raw_plugin)
    plugins_in_order = [r.plugin for r in cfg.plugin.rules]
    assert plugins_in_order == ["long", "medium", "short"]


# ── DraftPrConfig: validate ───────────────────────────────────────────────────

def test_draft_pr_config_validate_passes_with_rules():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": ["frontend/"], "plugin": "fp"}]
    })
    cfg.validate()  # should not raise


def test_draft_pr_config_validate_passes_with_default_only():
    cfg = DraftPrConfig(plugin={"default": "fallback"})
    cfg.validate()  # should not raise


def test_draft_pr_config_validate_fails_with_no_rules_and_no_default():
    cfg = DraftPrConfig()
    with pytest.raises(ValueError, match="at least one rule or a default"):
        cfg.validate()


def test_draft_pr_config_validate_fails_with_empty_paths_in_rule():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": [], "plugin": "fp"}]
    })
    with pytest.raises(ValueError, match="at least one path"):
        cfg.validate()


# ── load_tool_config integration ──────────────────────────────────────────────

def test_load_tool_config_produces_valid_draft_pr_config():
    devflow_cfg = DevflowConfig(tools={
        "draft-pr": {
            "plugin": {
                "default": "default-pr",
                "rules": [{"paths": ["frontend/"], "plugin": "frontend-pr"}]
            }
        }
    })
    cfg = load_tool_config(devflow_cfg, "draft-pr", DraftPrConfig)
    assert isinstance(cfg, DraftPrConfig)
    assert cfg.plugin.default == "default-pr"
    assert cfg.plugin.rules[0].plugin == "frontend-pr"


def test_load_tool_config_calls_validate_on_draft_pr_config():
    devflow_cfg = DevflowConfig(tools={"draft-pr": {"plugin": {}}})
    with pytest.raises(ValueError, match="at least one rule or a default"):
        load_tool_config(devflow_cfg, "draft-pr", DraftPrConfig)


# ── resolve_plugin ────────────────────────────────────────────────────────────

def test_resolve_plugin_matches_prefix():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": ["frontend/"], "plugin": "frontend-pr"}]
    })
    assert resolve_plugin(cfg, "/home/user/work/frontend/my-app") == "frontend-pr"


def test_resolve_plugin_returns_default_when_no_match():
    cfg = DraftPrConfig(plugin={
        "default": "default-pr",
        "rules": [{"paths": ["frontend/"], "plugin": "frontend-pr"}]
    })
    assert resolve_plugin(cfg, "/home/user/work/backend/service") == "default-pr"


def test_resolve_plugin_returns_none_when_no_match_and_no_default():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": ["frontend/"], "plugin": "frontend-pr"}]
    })
    assert resolve_plugin(cfg, "/home/user/work/backend/service") is None


def test_resolve_plugin_longer_path_wins_over_shorter():
    cfg = DraftPrConfig(plugin={
        "rules": [
            {"paths": ["frontend/"], "plugin": "generic-frontend"},
            {"paths": ["frontend/payments/"], "plugin": "payments"},
        ]
    })
    assert resolve_plugin(cfg, "frontend/payments/checkout") == "payments"


def test_resolve_plugin_matches_any_path_in_rule():
    cfg = DraftPrConfig(plugin={
        "rules": [{"paths": ["ui/", "frontend/"], "plugin": "frontend-pr"}]
    })
    assert resolve_plugin(cfg, "ui/components") == "frontend-pr"
    assert resolve_plugin(cfg, "frontend/app") == "frontend-pr"
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd devflow/draft-pr && python -m pytest tests/test_draft_pr_config.py -v 2>&1 | head -20
```

Expected: ImportError — `config.py` doesn't exist yet.

- [ ] **Step 3: Create `devflow/draft-pr/config.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from devflow_sdk.config import PluginConfig


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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd devflow/draft-pr && python -m pytest tests/test_draft_pr_config.py -v
```

Expected: all green.

- [ ] **Step 5: Wire `DraftPrConfig` into `draft-pr.py`**

In `devflow/draft-pr/draft-pr.py`, after the existing imports, add:

```python
from devflow_sdk.config import load_config, load_tool_config
from config import DraftPrConfig, resolve_plugin
```

In `main()`, replace the existing plugin discovery block (lines 81–92):

```python
    plugins = discover(PLUGIN_DIR)
    if not plugins:
        print(f"Error: no plugins found in {PLUGIN_DIR}", file=sys.stderr)
        print("Install a plugin into the plugins directory to continue.", file=sys.stderr)
        sys.exit(1)

    if len(plugins) == 1:
        plugin = plugins[0]
    else:
        plugin_names = [p.name or type(p).__name__ for p in plugins]
        chosen_name = select("Select format", choices=plugin_names)
        plugin = plugins[plugin_names.index(chosen_name)]
```

with:

```python
    devflow_cfg = load_config()
    draft_pr_cfg = load_tool_config(devflow_cfg, "draft-pr", DraftPrConfig)
    configured_plugin_name = resolve_plugin(draft_pr_cfg, os.getcwd())

    plugins = discover(PLUGIN_DIR)
    if not plugins:
        print(f"Error: no plugins found in {PLUGIN_DIR}", file=sys.stderr)
        print("Install a plugin into the plugins directory to continue.", file=sys.stderr)
        sys.exit(1)

    if configured_plugin_name:
        plugin_names = [p.name or type(p).__name__ for p in plugins]
        if configured_plugin_name in plugin_names:
            plugin = plugins[plugin_names.index(configured_plugin_name)]
        else:
            print(
                f"Warning: configured plugin '{configured_plugin_name}' not found. "
                f"Available: {', '.join(plugin_names)}",
                file=sys.stderr,
            )
            plugin = plugins[0] if len(plugins) == 1 else plugins[plugin_names.index(
                select("Select format", choices=plugin_names)
            )]
    elif len(plugins) == 1:
        plugin = plugins[0]
    else:
        plugin_names = [p.name or type(p).__name__ for p in plugins]
        chosen_name = select("Select format", choices=plugin_names)
        plugin = plugins[plugin_names.index(chosen_name)]
```

- [ ] **Step 6: Run the existing `draft-pr` tests to confirm nothing is broken**

```bash
cd devflow/draft-pr && python -m pytest tests/ -v
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add devflow/draft-pr/config.py \
        devflow/draft-pr/tests/test_draft_pr_config.py \
        devflow/draft-pr/draft-pr.py
git commit -m "feat: add DraftPrConfig with directory-based plugin routing for draft-pr"
```

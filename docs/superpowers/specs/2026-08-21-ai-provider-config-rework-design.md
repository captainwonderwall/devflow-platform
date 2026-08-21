# AI Provider Config Rework Design

**Date:** 2026-08-21
**Status:** Approved

## Problem

The current `DevflowConfig` is a flat dataclass with `ai_provider` and `models` fields — everything is global, and tools have no place to define their own behavioural config. All tool-specific behaviour (tier, trust level, plugin selection) is hardcoded in the tool scripts. This makes it impossible for users to customise per-tool behaviour without modifying source code.

## Goal

Introduce a two-layer config schema:

- **Global config** — infrastructure settings that apply to all tools (`ai_provider`, `models`)
- **Tool config** — behavioural settings specific to each tool, with each tool owning its own schema

---

## Config Schema

### File: `~/.devflow/config.json`

```json
{
  "global": {
    "ai_provider": "claude",
    "models": {
      "fast": { "name": "claude-haiku-4-5-20251001" },
      "capable": { "name": "claude-sonnet-4-6" }
    }
  },
  "tools": {
    "draft-pr": {
      "plugin": {
        "default": "default-pr",
        "rules": [
          { "paths": ["frontend/", "ui/"], "plugin": "frontend-pr" },
          { "paths": ["backend/"], "plugin": "backend-pr" }
        ]
      },
      "title_format": "feat: {title}"
    },
    "address-pr": {
      "plugin": {
        "default": "default-responder",
        "rules": [
          { "paths": ["frontend/"], "plugin": "frontend-responder" }
        ]
      }
    }
  }
}
```

### Design rules

- `global` contains only provider/model infrastructure settings.
- `tools` is keyed by tool name. Each value is tool-defined — the SDK treats it as an opaque dict.
- Tools cannot override `global`. The two sections have no overlap.
- Tool-specific fields sit at the tool's top level alongside `plugin`.

---

## Python Types

### SDK — `devflow_sdk/config.py`

```python
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
```

`get_provider` is updated to accept `GlobalConfig` instead of `DevflowConfig`:

```python
def get_provider(global_config: GlobalConfig) -> AiProvider: ...
```

Callers pass `config.global_config`.

---

## Backwards Compatibility

If the loaded JSON has no `global` key, `load_config` detects the flat legacy format, wraps the existing fields into a `GlobalConfig`, and prints a deprecation warning:

```
[devflow] Warning: config format is outdated. Wrap your config under a "global" key.
```

No breaking change for existing users.

---

## Plugin Config (SDK-owned)

The `plugin` key is a uniform convention across all tool configs. The SDK provides a generic container:

```python
T = TypeVar("T")

@dataclass
class PluginConfig(Generic[T]):
    default: str | None = None
    rules: list[T] = field(default_factory=list)
```

### What the SDK owns
- The `plugin` key convention
- `plugin.default` — fallback plugin name when no rule matches
- `plugin.rules` — list of rule objects (content shape is tool-defined)

### What each tool owns
- The rule item type `T`
- The resolution logic (how to match a rule against runtime state)

This keeps the plugin concept uniform across tools while allowing each tool's rules to carry whatever fields they need.

---

## `load_tool_config` Helper

```python
def load_tool_config(config: DevflowConfig, tool_name: str, schema_cls: type[T]) -> T:
    raw = config.tools.get(tool_name, {})
    known_fields = {f.name for f in dataclasses.fields(schema_cls)}
    filtered = {k: v for k, v in raw.items() if k in known_fields}
    instance = schema_cls(**filtered)
    if hasattr(instance, "validate"):
        instance.validate()
    return instance
```

- Filters unknown keys from the raw dict — old or mistyped fields in the JSON do not cause crashes.
- After instantiation, calls `validate()` if the tool config defines it.
- New fields added to a tool's dataclass need a default value — existing configs that omit them continue working.

---

## Tool Config Validation

Each tool may define a `validate()` method on its config dataclass. `load_tool_config` calls it automatically after instantiation. Tools with no special validation rules omit it.

```python
@dataclass
class DraftPrConfig:
    plugin: PluginConfig[DirectoryRule] = field(default_factory=PluginConfig)
    title_format: str = "{issue_id}: {title}"

    def validate(self) -> None:
        if not self.plugin.rules and self.plugin.default is None:
            raise ValueError(
                "draft-pr: plugin config must have at least one rule or a default"
            )
```

`validate()` raises `ValueError` with a descriptive message. The caller (`load_tool_config`) lets it propagate — the tool fails fast at startup with a clear config error.

---

## `draft-pr` Tool Config

### Rule type

```python
@dataclass
class DirectoryRule:
    paths: list[str]
    plugin: str
```

### Config dataclass

```python
@dataclass
class DraftPrConfig:
    plugin: PluginConfig[DirectoryRule] = field(default_factory=PluginConfig)
    title_format: str = "{issue_id}: {title}"

    def __post_init__(self):
        # Sort rules longest-path-first so most specific path wins at match time
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
                raise ValueError("draft-pr: each plugin rule must have at least one path")
```

### Plugin resolution

```python
def resolve_plugin(config: DraftPrConfig, cwd: str) -> str | None:
    for rule in config.plugin.rules:
        if any(cwd.startswith(p) for p in rule.paths):
            return rule.plugin
    return config.plugin.default
```

- **Matching strategy:** prefix — `"frontend/"` matches any `cwd` that starts with that string.
- **Specificity:** rules are sorted by longest path at load time; first match wins.
- **Fallback:** `plugin.default` is returned when no rule matches. `None` if neither is set.

### Usage in `draft-pr`

```python
config = load_config()
draft_pr_config = load_tool_config(config, "draft-pr", DraftPrConfig)
plugin_name = resolve_plugin(draft_pr_config, os.getcwd())
```

---

## Extending to Other Tools

Adding config for a new tool (`start-issue`, `finish-issue`, `address-pr`) requires:

1. Define the tool's config dataclass (and rule type if it uses `PluginConfig`)
2. Optionally define `validate()`
3. Call `load_tool_config` at the start of the tool script

No SDK changes are required. The `tools` dict is open — any tool can add its own key.

---

## Files Affected

| File | Change |
|---|---|
| `devflow_sdk/config.py` | Add `GlobalConfig`; rework `DevflowConfig`; add `load_tool_config`; add `PluginConfig[T]`; backwards-compat in `load_config` |
| `devflow_sdk/ai_providers/__init__.py` | Update `get_provider` to accept `GlobalConfig` |
| `devflow/draft-pr/config.py` | New file: `DirectoryRule`, `DraftPrConfig`, `resolve_plugin` |
| `devflow/draft-pr/draft-pr.py` | Load `DraftPrConfig` via `load_tool_config`; use `resolve_plugin` |

# devflow-config: Interactive Config Wizard + SDK Consolidation

**Date:** 2026-08-26
**Status:** Approved

---

## Problem

`~/.devflow/config.json` is today written entirely by hand. There is no tooling to generate an initial config or update an existing one. Additionally, config-related code (schema, I/O, tool-specific config classes) is scattered: `DraftPrConfig` lives in `devflow/draft-pr/config.py`, and the concrete `PluginLoader` lives in `devflow/plugin-manager/plugin_loader.py` — two pieces of shared infrastructure that live outside the SDK and create cross-tool coupling.

---

## Goals

- Ship a `devflow-config` binary that walks the user through their config interactively, pre-populated with current values so it works for both fresh setup and updates.
- Consolidate all config schema, I/O, and wizard logic into `devflow-sdk` under a clearly scoped folder.
- Move shared infrastructure (concrete `PluginLoader`, `DraftPrConfig`) into the SDK to eliminate cross-tool dependencies.
- Keep all existing tool scripts working without modification.

---

## Interaction Model

`devflow-config` runs as an interactive wizard (no subcommands). It:

1. Loads the existing `~/.devflow/config.json` (or typed defaults if none exists)
2. Walks through each wizard step in sequence, pre-populating all prompts from current values
3. Writes the result atomically to `~/.devflow/config.json`

Re-running the wizard is how the user updates any setting.

---

## SDK Folder Layout

`devflow_sdk/config.py` becomes a package. All config and wizard code lives under `devflow_sdk/config/`. The concrete `PluginLoader` moves into `devflow_sdk/plugin/`.

```
devflow_sdk/
├── config/
│   ├── __init__.py            # re-exports current config.py surface (backward compat)
│   ├── schema.py              # DevflowConfig, GlobalConfig, ModelConfig, PluginConfig
│   ├── io.py                  # load_config(), save_config(), merge_config()
│   └── wizard/
│       ├── __init__.py        # WizardStep ABC, run_wizard()
│       ├── global_steps.py    # ProviderStep, ModelsStep
│       └── tools/
│           ├── __init__.py    # ALL_TOOL_STEPS registry
│           └── draft_pr.py    # DraftPrConfig, DirectoryRule, DraftPrWizardStep
│
├── plugin/
│   ├── __init__.py            (unchanged)
│   ├── plugin_base.py         (unchanged)
│   ├── plugin_registry.py     (unchanged)
│   ├── plugin_loader.py       (unchanged — PluginLoaderBase ABC)
│   └── plugin_loader_impl.py  ← NEW: concrete PluginLoader moved from devflow/plugin-manager/
│
└── ... (all other modules unchanged)
```

`devflow_sdk/config/__init__.py` re-exports everything from the old `config.py` public surface (`load_config`, `load_tool_config`, `DevflowConfig`, `GlobalConfig`, `ModelConfig`, `PluginConfig`). All six existing tool scripts import from `devflow_sdk.config` and see no change.

---

## WizardStep Protocol

**`devflow_sdk/config/wizard/__init__.py`**

```python
class WizardStep(ABC):
    section: str  # printed as a header before the step's prompts

    @abstractmethod
    def run(self, current: DevflowConfig) -> DevflowConfig:
        ...

def run_wizard(steps: list[WizardStep]) -> DevflowConfig:
    config = load_config()
    for step in steps:
        print(f"\n=== {step.section} ===")
        config = step.run(config)
    save_config(config)
    return config
```

Each `run()` receives the full current `DevflowConfig` and returns a modified copy using `dataclasses.replace()`. This ensures unchanged sections are never accidentally reset. Prompts are pre-populated from `current` values so the user sees what is already set.

---

## Config I/O

**`devflow_sdk/config/io.py`**

- `load_config(path=None) -> DevflowConfig` — existing behaviour; returns typed defaults when no file exists
- `save_config(config, path=None) -> None` — atomic write via temp file + `os.rename()`
- `merge_config(base, overlay) -> DevflowConfig` — deep merge; overlay's non-None fields win

`save_config` uses the same temp-file-then-rename pattern as the existing plugin registry atomic writes.

---

## Concrete Wizard Steps

All prompt calls use `devflow_sdk.prompts` wrappers (`select`, `text`, `confirm`, `checkbox`, `Choice`). No direct `questionary` calls.

### ProviderStep (`global_steps.py`)

```
=== AI Provider ===
Which AI provider should devflow use? (claude / opencode)
→ select(), pre-populated with current value
```

### ModelsStep (`global_steps.py`)

```
=== Model Configuration ===
Select model tiers to configure: [checkbox — fast, capable]
  (shows current model name next to each choice; all pre-selected)

For each selected tier:
  Model name: [text(), default = current name]
  Input price ($/M tokens): [text(), default = current]
  Output price ($/M tokens): [text(), default = current]
```

`checkbox()` lets the user skip tiers they don't want to touch by deselecting them.

### DraftPrWizardStep (`tools/draft_pr.py`)

```
=== draft-pr: Plugin Routing ===
(skipped with a notice if no plugins are registered)

Default plugin: [select() from list_plugins()]

Which path rules should be kept? [checkbox — all pre-selected]
  (each rule shown as "glob, glob → plugin-name")

Add a new path rule? [confirm()]
  → Path patterns (comma-separated): [text()]
  → Plugin for this path: [select()]
  → repeat until user says no
```

`list_plugins()` is called from `PluginLoaderImpl` (now in SDK). `DraftPrConfig` and `DirectoryRule` move from `devflow/draft-pr/config.py` into this module.

### Tool Step Registry (`tools/__init__.py`)

```python
ALL_TOOL_STEPS: list[WizardStep] = [DraftPrWizardStep()]
```

Adding support for a new tool = one new entry here. `devflow-config` itself never changes.

---

## devflow-config Tool Script

**`devflow/devflow-config/devflow-config.py`** (~15 lines):

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

vendor_dir = Path(__file__).parent.parent / "vendor"
for whl in vendor_dir.glob("*.whl"):
    sys.path.insert(0, str(whl))

from devflow_sdk.config.wizard import run_wizard
from devflow_sdk.config.wizard.global_steps import ProviderStep, ModelsStep
from devflow_sdk.config.wizard.tools import ALL_TOOL_STEPS

def main():
    steps = [ProviderStep(), ModelsStep()] + ALL_TOOL_STEPS
    run_wizard(steps)

if __name__ == "__main__":
    main()
```

Same vendor-wheel bootstrap as all other tools.

---

## Migration Shims (Backward Compat)

| File | Change |
|---|---|
| `devflow/draft-pr/config.py` | Replace contents with `from devflow_sdk.config.wizard.tools.draft_pr import DraftPrConfig, DirectoryRule` |
| `devflow/plugin-manager/plugin_loader.py` | Replace contents with `from devflow_sdk.plugin.plugin_loader_impl import PluginLoader` and re-export module-level aliases |

Both shims preserve existing import paths so `draft-pr.py` and `plugin-manager` scripts need zero changes.

---

## Homebrew Formula Changes

`homebrew-devflow/Formula/devflow.rb`:

1. Install `devflow/devflow-config/` into `libexec/devflow-config/`
2. Add `bin/devflow-config` wrapper (same `PYTHONPATH` pattern as existing five tools)
3. Bump `resource "devflow-sdk"` to `1.1.0` wheel

---

## SDK Version Bump

`devflow-sdk`: `1.0.1 → 1.1.0`

New public surface added: `config/` package, `config/wizard/` module tree, `plugin/plugin_loader_impl.py`. Nothing removed. Minor bump is appropriate.

---

## What Does NOT Change

- All six existing tool scripts (`draft-pr.py`, `address-pr.py`, etc.) — zero edits required
- `devflow-plugin` binary behaviour — unchanged; its backing `plugin_loader.py` becomes a shim
- Plugin registry format (`~/.devflow/plugin-registry.json`) — unchanged
- `.issue.json` format — unchanged
- `devflow-plugin-scaffold` — unchanged

---

## Testing

- Unit tests for `WizardStep.run()` methods: pass a `DevflowConfig` fixture, assert returned config matches expected mutations; mock `devflow_sdk.prompts` calls
- Unit tests for `save_config` / `merge_config` in `io.py`
- Migrate existing `plugin_loader` tests to cover `plugin_loader_impl`
- Integration test: run `devflow-config` against a temp `~/.devflow/` directory, assert the written JSON matches expected shape

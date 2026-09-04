# Plugin/Core Re-organization (#43)

Status: implemented; compatibility seam removed
Issue: #43 — "Re-design the plugin management module/system given the lesson
learned and the changes in the SDK"

---

## Scope

This spec covers **only the code re-organization of the plugin and core
packages**. The canonical plugin package is `devflow_sdk.plugin`; the removed
`devflow_sdk.core.plugin` compatibility seam is not supported. The plugin
registry, the `devflow-plugin` CLI, the scaffold, and Homebrew packaging remain
otherwise unchanged.

**Deferred to a follow-up spec** (design work already done, not discarded):
replacing the bespoke registry with `importlib.metadata` entry points, removing
the `devflow-plugin` CLI, the `pip --target` install flow, SDK version-range
checks, and the scaffold/vendoring changes those imply. Those changes are
larger and independent; doing the re-organization first makes them smaller,
because they land in a package that already sits at the right layer.

---

## Problem

`devflow_sdk/core/plugin/` sits inside `core`, but plugin management is not
core infrastructure — it is a mechanism that *uses* core. Two concrete symptoms:

**A dependency cycle.** `core/plugin/plugin_loader_impl.py:16` imports
`core.prompts.select`, while `core/config/wizard/tools/draft_pr.py:8` imports
`PluginLoader` from it. Today both edges are inside `core`, so nothing detects
the cycle.

**No enforceable layering.** Because the package is nested under `core`, there
is no way to express "plugin may use core, core may not use plugin" as an
import-linter rule. The existing contract set cannot see the distinction.

---

## The Move

`devflow_sdk/core/plugin/` becomes a top-level package, a sibling of `core/`
and `domain/`:

```
devflow-sdk/devflow_sdk/
├── core/
├── domain/
└── plugin/
    ├── __init__.py             # public surface (unchanged names)
    ├── plugin_base.py
    ├── contracts.py
    ├── plugin_loader.py
    ├── plugin_loader_impl.py
    ├── plugin_registry.py
    └── cli.py
```

Every module moves as-is. Internal imports change from
`devflow_sdk.core.plugin.X` to `devflow_sdk.plugin.X`. No logic changes, no
signature changes, no behaviour changes.

`devflow_sdk/plugin/__init__.py` keeps exactly today's exports, so the public
surface is identical:

```python
PluginBase, PluginLoaderBase, PluginLoader, PluginEntry, DraftPrPlugin,
select_plugin, register, unregister, list_plugins, discover
```

`cli.py` moves with the rest, so the `devflow-plugin` bin wrapper in
`devflow.rb` must be updated from `python3 -m devflow_sdk.core.plugin.cli` to
`python3 -m devflow_sdk.plugin.cli`. This hardcoded string is the exact
construct that caused this issue, so a test asserts the module is importable
and runnable as `-m` (see Testing Plan). Deleting the CLI outright is the
better fix, but belongs to the deferred entry-points work.

---

## Compatibility Seam Removal

`devflow_sdk.plugin` is the sole plugin seam. The deprecated
`devflow_sdk.core.plugin` package has been removed, so plugin authors must use
the canonical import path:

```python
from devflow_sdk.plugin import DraftPrPlugin
```

The removed package is not re-exported, and imports from the old path are not a
supported compatibility contract. Plugin registration and loading behavior are
otherwise unchanged.

---

## Import-linter Contract

The layering is enforced positively, replacing an ad-hoc prohibition:

```toml
[[tool.importlinter.contracts]]
name = "SDK layers"
type = "layers"
layers = [
    "devflow_sdk.domain",
    "devflow_sdk.plugin",
    "devflow_sdk.core",
]
```

This enforces: `core` imports neither `plugin` nor `domain`; `plugin` may
import `core` but not `domain`; `domain` may import both. A layers contract is
**not** a chain — `domain → core` directly remains legal.

The same-layer syntaxes are deliberately not used: `plugin : core` would
re-legalise the `core → plugin` cycle, and `plugin | core` would forbid
`plugin → core`, breaking `select_plugin`'s interactive prompt.

The existing **"Core must not import from domain"** contract is **deleted**
(strictly subsumed by the layers contract). **"Domains are independent of each
other"** is kept unchanged, and `devflow_sdk.plugin` is deliberately *not*
added to it, because it is not a domain.

With the compatibility package removed, the contract has no ignored imports.

---

## Breaking the `core → plugin` Edge

The contract cannot pass while the wizard imports `PluginLoader`. The wizard
only needs plugin *names*, so the dependency is inverted:

```python
# devflow_sdk/core/config/wizard/tools/draft_pr.py — no plugin import
class DraftPrWizardStep(WizardStep):
    def __init__(self, plugin_names: Callable[[], list[str]] | None = None):
        self._plugin_names = plugin_names or (lambda: [])

    def run(self, current: DevflowConfig) -> DevflowConfig:
        plugin_names = self._plugin_names()
        if not plugin_names:
            print("  No plugins registered — skipping draft-pr plugin routing configuration.")
            return current
        # ... remainder unchanged
```

This replaces the current `loader = PluginLoader()` / `available =
loader.list_plugins()` / `plugin_names = list(available.keys())` sequence; the
rest of `run()` already works from `plugin_names` and needs no edits.

A lazy function-level import would not satisfy the contract —
`import-linter` analyses imports inside function bodies too — so the inversion
must be real.

The provider is supplied at the composition root. `ALL_TOOL_STEPS` is a
module-level constant built at import time inside the SDK, so it cannot supply
it without re-introducing the very import being removed. It becomes a factory,
with the constant kept as an argument-free default:

```python
# devflow_sdk/core/config/wizard/tools/__init__.py
def build_tool_steps(plugin_names: Callable[[], list[str]] | None = None) -> list[WizardStep]:
    return [DraftPrWizardStep(plugin_names)]

ALL_TOOL_STEPS: list[WizardStep] = build_tool_steps()
```

```python
# devflow/devflow-config/devflow-config.py — the composition root
from devflow_sdk.plugin import PluginLoader
from devflow_sdk.core.config.wizard.tools import build_tool_steps

steps = [ProviderStep(), ModelsStep()] + build_tool_steps(
    lambda: sorted(PluginLoader().list_plugins())
)
```

`PluginLoader.list_plugins()` returns `dict[str, PluginEntry]`, so the lambda
takes its keys. The provider is wrapped so a registry read failure degrades to
a printed warning plus an empty list: `devflow-config` is what a user reaches
for when things are misconfigured, so it must not be the thing that breaks.

Omitting the provider degrades to "no plugins" rather than failing, so
`ALL_TOOL_STEPS` remains usable.

---

## Caller Impact

| Caller | Change |
|---|---|
| `devflow/draft-pr/draft-pr.py` | `from devflow_sdk.plugin import DraftPrPlugin, select_plugin`. Call sites unchanged. |
| `devflow/devflow-config/devflow-config.py` | Uses `build_tool_steps(...)` with the plugin-names provider |
| `devflow_sdk/core/config/wizard/tools/draft_pr.py` | Drops the `PluginLoader` import; takes the injected provider |
| `devflow_sdk/core/config/wizard/tools/__init__.py` | Gains `build_tool_steps`; keeps `ALL_TOOL_STEPS` |
| `homebrew-devflow/Formula/devflow.rb` | `devflow-plugin` wrapper: `devflow_sdk.core.plugin.cli` → `devflow_sdk.plugin.cli` |

---

## Testing Plan

**Existing tests must pass unmodified except for import paths.** This is the
primary evidence that the move is behaviour-preserving. In particular the
`resolve_plugin` / `DirectoryRule` tests and the plugin loader/registry tests
must not need logic changes.

**`devflow-sdk/tests/test_plugin_public_api.py`** (updated): asserts
`devflow_sdk.plugin` exports the documented names, and that
The removed `devflow_sdk.core.plugin` path is not a supported interface.

**`devflow-sdk/tests/test_plugin_cli.py`** (new): asserts
`devflow_sdk.plugin.cli` is importable and runnable via
`python3 -m devflow_sdk.plugin.cli --help`, returning zero. This closes the gap
that caused this issue: the module path was previously referenced only by a
hardcoded string in a Homebrew formula that nothing executed in CI.

**`devflow/devflow-config/tests/test_wizard.py`** (updated): covers
`build_tool_steps` with a provider (populated and empty), with the argument
omitted, and with a provider that raises — asserting the wizard degrades to "no
plugins" rather than propagating.

**`devflow-sdk/tests/test_wizard_draft_pr.py`** (updated): asserts the module no
longer imports the plugin package.

**CI (`lint-imports`)**: the "SDK layers" contract has no ignored imports.

---

## Files Touched

| File | Change |
|---|---|
| `devflow_sdk/plugin/*` | New location; modules moved verbatim with updated internal imports |
| `devflow_sdk/core/plugin/*` | Deleted; `devflow_sdk.plugin` is canonical |
| `devflow_sdk/core/config/wizard/tools/draft_pr.py` | Remove `PluginLoader` import; accept injected `plugin_names` |
| `devflow_sdk/core/config/wizard/tools/__init__.py` | Add `build_tool_steps`; keep `ALL_TOOL_STEPS` |
| `devflow-sdk/pyproject.toml` | Add "SDK layers" contract with one scoped `ignore_imports`; delete "Core must not import from domain"; keep "Domains are independent" |
| `devflow-sdk/tests/*` | Per the testing plan |
| `devflow/draft-pr/draft-pr.py` | Import path |
| `devflow/devflow-config/devflow-config.py` | Supply the plugin-names provider |
| `devflow/devflow-config/tests/test_wizard.py` | Per the testing plan |
| `homebrew-devflow/Formula/devflow.rb` | Update the `devflow-plugin` module path |
| `devflow-sdk/README.md` | Documents the canonical import path |

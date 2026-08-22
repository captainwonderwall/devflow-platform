# Plugin Loader SDK Design

**Date:** 2026-08-21
**Status:** Approved for implementation

## Hard Constraints

| Concern | Constraint |
|---|---|
| Implementation agents | **Haiku family only** — any agent writing or editing code must use a Haiku model |
| Review agents | **Sonnet 5 maximum** — no model above Sonnet 5 for code review or spec review |

## Problem

Plugin loading and selection logic lives entirely inside `draft-pr`. If `address-pr`, `start-issue`, or any future script ever adds plugin support, each would have to reimplement the same ~35 lines of discovery and selection logic. `PluginBase` (the abstract contract) is already in the SDK but the loader is not.

## Goals

1. Move plugin discovery and selection into `devflow-sdk` so all scripts share it.
2. Separate the generic plugin identity contract from the draft-pr-specific interface.
3. Define a clear compatibility story for plugins when devflow releases a major version.

## Design

### Generic `PluginBase` (SDK)

`devflow_sdk/plugin_base.py` becomes a minimal marker with `name` only:

```python
from abc import ABC

class PluginBase(ABC):
    name: str = ""
```

No version field, no `is_compatible()`. The only thing all plugins share is an identity.

### `DraftPrPlugin(PluginBase)` (SDK)

The draft-pr contract moves into the SDK as a named subclass of `PluginBase`:

```python
# devflow_sdk/draft_pr_plugin.py
from abc import abstractmethod
from devflow_sdk.plugin_base import PluginBase

class DraftPrPlugin(PluginBase):
    @abstractmethod
    def get_questions(self, data: dict) -> list[dict]: ...

    @abstractmethod
    def build_prompt(self, data: dict, user_inputs: dict) -> str: ...

    @abstractmethod
    def build_body(self, ai_result: dict, user_inputs: dict) -> str: ...
```

Future scripts add their own subclass (e.g., `AddressPrPlugin`) in the same pattern. Each script-specific base lives in the SDK because that is what plugin authors depend on.

### Plugin Loader (SDK)

`devflow_sdk/plugin_loader.py` is a new module with two public functions:

**`discover(plugin_dir, base_cls)`**

Scans `plugin_dir` for `.py` files, imports each, and returns instances of concrete subclasses of `base_cls`. Replaces `draft-pr/plugin_loader.py`.

Key behavioural change from the current implementation: failures are no longer silently swallowed. When a plugin file fails to load or instantiate, the loader emits a named warning to stderr:

```
Warning: plugin 'acme_format.py' failed to load — it may be incompatible
with this version of devflow. Check for an updated release.
```

Signature:
```python
def discover(plugin_dir: str, base_cls: type) -> list[PluginBase]:
```

**`select_plugin(plugin_dir, base_cls, configured_name=None)`**

Calls `discover()` internally, then applies the selection logic currently embedded in `draft-pr.py`:

- No plugins found → returns `None`; caller handles the error in its own way
- Configured name found → returns that plugin
- Configured name not found → warns to stderr, falls back to single plugin or interactive prompt
- One plugin, no config → returns it directly
- Multiple plugins, no config → interactive `select()` prompt

Signature:
```python
def select_plugin(
    plugin_dir: str,
    base_cls: type,
    configured_name: str | None = None,
) -> PluginBase | None:
```

`discover()` stays public for callers that need introspection or custom selection logic.

### `draft-pr` changes

`devflow/draft-pr/plugin_loader.py` is deleted. `draft-pr.py` replaces ~20 lines of discovery and selection with:

```python
from devflow_sdk.plugin_loader import select_plugin
from devflow_sdk.draft_pr_plugin import DraftPrPlugin

plugin = select_plugin(PLUGIN_DIR, DraftPrPlugin, configured_name)
if plugin is None:
    print(f"Error: no plugins found in {PLUGIN_DIR}", file=sys.stderr)
    print("Install a plugin into the plugins directory to continue.", file=sys.stderr)
    sys.exit(1)
```

### Shared plugins directory

The Homebrew formula already creates a shared directory:

```ruby
(lib/"devflow/plugins").mkpath
(libexec/"draft-pr/plugins").make_symlink(lib/"devflow/plugins")
```

`PLUGIN_DIR` in `draft-pr.py` resolves through this symlink to the shared dir. When a future script adds plugin support, the formula adds one line:

```ruby
(libexec/"address-pr/plugins").make_symlink(lib/"devflow/plugins")
```

`discover(plugin_dir, DraftPrPlugin)` and `discover(plugin_dir, AddressPrPlugin)` filter by base class, so plugins for one script are silently ignored by another.

---

## Plugin Compatibility

### Version alignment

The devflow tool and `devflow-sdk` release in lockstep with the same version number. Plugin authors think in terms of one version: "my plugin targets devflow 0.x." No separate SDK version to track.

### Install-time gate (`install.sh`)

`install.sh` in the plugin scaffold uses `brew --prefix devflow` to locate the installation and checks the major version before copying the plugin file:

```bash
PLUGIN_MIN_MAJOR="0"   # stamped by scaffold at generation time
PLUGIN_MAX_MAJOR="0"   # same value — compatible with this major only

DEVFLOW_VERSION="$(brew list --versions devflow | awk '{print $2}')"
DEVFLOW_MAJOR="${DEVFLOW_VERSION%%.*}"

if [ "$DEVFLOW_MAJOR" -lt "$PLUGIN_MIN_MAJOR" ] || [ "$DEVFLOW_MAJOR" -gt "$PLUGIN_MAX_MAJOR" ]; then
    echo "ERROR: this plugin supports devflow ${PLUGIN_MIN_MAJOR}.x – ${PLUGIN_MAX_MAJOR}.x"
    echo "Installed: devflow $DEVFLOW_VERSION"
    exit 1
fi
```

Both bounds start equal (compatible with exactly one major). The scaffold stamps both with the major of the devflow version installed on the author's machine at scaffold time (`brew list --versions devflow | awk '{print $2}' | cut -d. -f1`). A plugin tested across multiple majors can widen the range manually. This is the hard compatibility gate — no separate Homebrew formula needed for the plugin.

### Runtime gate (`discover()`)

When a plugin fails to load at runtime (e.g., installed outside `install.sh`, or bounds were wrong), `discover()` emits a named warning as described above. This is the soft fallback.

### Plugin author upgrade workflow

When devflow releases a major version:

1. Author updates plugin code to the new `DraftPrPlugin` interface.
2. Author commits with `feat!: upgrade to devflow v1 SDK` (the `!` triggers major bump in `release.sh`).
3. Author runs `bash scripts/release.sh`.
4. Before the confirm prompt, `release.sh` detects the major bump and prints:

   ```
   Major release detected. Before tagging, update install.sh:
     PLUGIN_MIN_MAJOR="<new major>"
     PLUGIN_MAX_MAJOR="<new major>"
   ```

5. Author updates `install.sh`, commits, then confirms in `release.sh`.
6. GitHub Actions publishes the new `.py` asset.

---

## Scaffold changes

`devflow-plugin-scaffold/scaffold.sh` changes:

- Plugin stub imports `DraftPrPlugin` instead of `PluginBase`:
  ```python
  from devflow_sdk.draft_pr_plugin import DraftPrPlugin

  class AcmePlugin(DraftPrPlugin):
      ...
  ```
- `install.sh` template gains `PLUGIN_MIN_MAJOR` / `PLUGIN_MAX_MAJOR` variables and the version check block. Both values are stamped with the current devflow major at scaffold time.
- `scripts/release.sh` template gains the major-bump reminder printed before the confirm prompt.
- Scaffold tests updated to assert the new import, the version variables, and the reminder message.

---

## Files touched

| File | Change |
|---|---|
| `devflow-sdk/devflow_sdk/plugin_base.py` | Stripped to generic marker (`name` only) |
| `devflow-sdk/devflow_sdk/draft_pr_plugin.py` | New — draft-pr abstract contract |
| `devflow-sdk/devflow_sdk/plugin_loader.py` | New — `discover()` + `select_plugin()` |
| `devflow-sdk/tests/test_plugin_base.py` | Update for restructured base |
| `devflow-sdk/tests/test_plugin_loader.py` | New — tests for SDK loader (ported + expanded from draft-pr) |
| `devflow-sdk/tests/test_draft_pr_plugin.py` | New — tests for `DraftPrPlugin` contract |
| `devflow/draft-pr/plugin_loader.py` | Deleted |
| `devflow/draft-pr/draft-pr.py` | Update imports, replace selection block |
| `devflow/draft-pr/tests/test_plugin_loader.py` | Deleted (covered by SDK tests) |
| `devflow-plugin-scaffold/scaffold.sh` | Update stub import + `install.sh` + `release.sh` templates |
| `devflow-plugin-scaffold/tests/release.sh` | Update assertions for new install.sh variables and reminder |

---

## Migration for existing plugin authors

Existing plugins subclass `PluginBase` and import from `devflow_sdk.plugin_base`. The change is one line:

```python
# before
from devflow_sdk.plugin_base import PluginBase
class AcmePlugin(PluginBase): ...

# after
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
class AcmePlugin(DraftPrPlugin): ...
```

The three abstract methods (`get_questions`, `build_prompt`, `build_body`) are unchanged. This is a breaking SDK change and warrants a devflow major version bump, which plugin authors handle via the upgrade workflow above.

# Plugin Lifecycle Design

**Date:** 2026-08-24
**Status:** Approved for implementation
**Supersedes:** Portions of `2026-08-21-plugin-loader-sdk-design.md` (plugin storage and install.sh approach)

## Hard Constraints

| Concern | Constraint |
|---|---|
| Implementation agents | **Haiku family only** — any agent writing or editing code must use a Haiku model |
| Review agents | **Sonnet 5 maximum** — no model above Sonnet 5 for code review or spec review |

---

## Problem

When a user runs `brew upgrade devflow`, the new Homebrew keg starts with an empty `lib/devflow/plugins/` directory. Plugins installed into the old keg are left behind — the user must manually re-install every plugin. There is no defined upgrade path, no registry of what was installed, and no way for devflow to recover automatically.

Additionally, there is no standard way for a plugin to register itself with devflow at install time or deregister at uninstall time.

---

## Goals

1. Plugin files survive `brew upgrade devflow` — no manual re-install required.
2. Plugins self-register at install time and self-deregister at uninstall time via a CLI provided by devflow.
3. devflow-platform knows nothing about specific plugins — discovery is fully dynamic.
4. The register/unregister/discover/select contract lives in the SDK so any devflow tool can depend on it.
5. The concrete implementation (including filesystem paths) lives in devflow, not the SDK.

---

## Architecture Overview

```
devflow-sdk
  plugin_registry.py    ← PluginEntry dataclass (data contract)
  plugin_loader.py      ← PluginLoaderBase ABC (function contracts)

devflow
  plugin-manager/
    plugin_loader.py    ← PluginLoader(PluginLoaderBase) implementation + CLI

~/.devflow/
  plugin-registry.json  ← managed by devflow-plugin CLI, never hand-edited
```

Plugin Homebrew formulas call `devflow-plugin register` in `post_install`. Unregistration requires manually running `devflow-plugin unregister <name>` before `brew uninstall` — Homebrew Formula DSL has no uninstall lifecycle hook. devflow tools import the concrete `PluginLoader` (via PYTHONPATH) to discover and select plugins at runtime.

---

## SDK Changes

### `devflow_sdk/plugin_registry.py` — new file

Pure data contract. No I/O, no filesystem paths.

```python
from dataclasses import dataclass

@dataclass
class PluginEntry:
    name: str
    path: str               # resolved $(brew --prefix)/opt/<formula>/lib/<name>.py
    formula: str | None = None
```

### `devflow_sdk/plugin_loader.py` — replace existing module

The current module-level `discover(plugin_dir, base_cls)` and `select_plugin(plugin_dir, base_cls, configured_name)` functions are replaced by an ABC. Callers that previously imported from this module will import from the concrete implementation instead.

```python
from abc import ABC, abstractmethod
from typing import TypeVar
from devflow_sdk.plugin_registry import PluginEntry

T = TypeVar("T")

class PluginLoaderBase(ABC):

    @abstractmethod
    def register(self, name: str, path: str, formula: str | None = None) -> None:
        """Add or update a plugin entry in the registry."""

    @abstractmethod
    def unregister(self, name: str) -> None:
        """Remove a plugin entry from the registry. No-op if name not found."""

    @abstractmethod
    def list_plugins(self) -> dict[str, PluginEntry]:
        """Return all registered plugins keyed by name."""

    @abstractmethod
    def discover(self, base_cls: type[T]) -> dict[str, T]:
        """Load and instantiate all registered plugins that are subclasses of base_cls."""

    @abstractmethod
    def select_plugin(self, base_cls: type[T], configured_name: str | None = None) -> T | None:
        """Discover plugins and select one: by name, auto (single), or interactive."""
```

`discover()` no longer takes `plugin_dir` — the registry replaces directory scanning.

---

## devflow Implementation

### `devflow/plugin-manager/plugin_loader.py` — new file

Imports the contract types from the SDK. Owns all implementation details including filesystem paths.

```python
from devflow_sdk.plugin_loader import PluginLoaderBase, T
from devflow_sdk.plugin_registry import PluginEntry

REGISTRY_PATH = Path.home() / ".devflow" / "plugin-registry.json"
REGISTRY_VERSION = 1

class PluginLoader(PluginLoaderBase):

    def register(self, name, path, formula=None):
        # Atomic write: load → mutate → write to temp → rename

    def unregister(self, name):
        # Atomic write: load → delete key → write to temp → rename
        # No-op and no error if name not present

    def list_plugins(self):
        # Read REGISTRY_PATH; return {} if file missing or empty

    def discover(self, base_cls):
        # For each entry in list_plugins():
        #   - warn and skip if entry.path does not exist (stale entry)
        #   - importlib load the .py file
        #   - find concrete subclasses of base_cls
        #   - warn and skip on any import or instantiation error
        # Returns dict[name, instance]

    def select_plugin(self, base_cls, configured_name=None):
        # Call discover(base_cls)
        # No plugins → return None (caller handles the error message)
        # configured_name provided and found → return it
        # configured_name provided but missing → warn to stderr, fall through
        # One plugin → return it
        # Multiple plugins → interactive questionary prompt
```

**Atomic registry writes** use `write to temp file → os.rename()` to prevent corruption from concurrent Homebrew installs.

**Module-level convenience** so calling code needs no class instantiation:

```python
_loader = PluginLoader()
register = _loader.register
unregister = _loader.unregister
list_plugins = _loader.list_plugins
discover = _loader.discover
select_plugin = _loader.select_plugin
```

### CLI entry point (`__main__`)

When run as a script, `plugin_loader.py` is the `devflow-plugin` CLI:

```
devflow-plugin register <name> <path> [--formula <tap/formula>]
devflow-plugin unregister <name>
devflow-plugin list
```

`register` and `unregister` print nothing on success (Homebrew `post_install` convention). `list` prints one `name: path` line per plugin, or `No plugins registered.` if empty.

---

## Homebrew Formula Changes

### `homebrew-devflow/Formula/devflow.rb`

**Remove** the shared plugins directory and symlink — plugins no longer live inside the keg:

```ruby
# REMOVE these two lines:
(lib/"devflow/plugins").mkpath
(libexec/"draft-pr/plugins").make_symlink(lib/"devflow/plugins")
```

**Add** a bin wrapper for `devflow-plugin`:

```ruby
(bin/"devflow-plugin").write <<~EOS
  #!/bin/bash
  export PYTHONPATH="#{libexec}/plugin-manager:#{Dir[libexec/"python-packages"].first}:$PYTHONPATH"
  exec python3 "#{libexec}/plugin-manager/plugin_loader.py" "$@"
EOS
```

**Update** existing bin wrappers (draft-pr, etc.) to add `plugin-manager` to PYTHONPATH so they can import `PluginLoader` directly:

```bash
export PYTHONPATH="#{libexec}/plugin-manager:#{libexec}/draft-pr:#{Dir[libexec/"python-packages"].first}:$PYTHONPATH"
```

---

## Scaffold Changes

### `devflow-plugin-scaffold/scaffold.sh`

**Replace** `install.sh` / `uninstall.sh` with a Homebrew formula template. Keep a minimal `install.sh` for development convenience (local testing without Homebrew).

**Generated Homebrew formula template (`Formula/<plugin-name>.rb.template`):**

```ruby
class DevflowPlugin<PluginNamePascal> < Formula
  desc "<PluginDescription>"
  homepage "<PluginHomepage>"
  url "<release-url>"
  sha256 "<sha256>"

  depends_on "captainwonderwall/devflow/devflow"

  def install
    lib.install "<module_name>.py"
  end

  def post_install
    system "#{HOMEBREW_PREFIX}/bin/devflow-plugin",
           "register", "<plugin-name>",
           "#{opt_lib}/<module_name>.py",
           "--formula", "<tap>/<plugin-name>"
  end

  # To unregister before uninstalling: devflow-plugin unregister <plugin-name>

  test do
    system "#{bin}/devflow-plugin", "list"
  end
end
```

**Generated `install.sh`** (dev convenience only — not for Homebrew distribution):

```bash
#!/bin/bash
set -euo pipefail
PLUGIN_DIR="$(dirname "$0")"
devflow-plugin register "<plugin-name>" "$PLUGIN_DIR/<module_name>.py"
echo "Installed <plugin-name>."
```

**Generated `uninstall.sh`:**

```bash
#!/bin/bash
set -euo pipefail
devflow-plugin unregister "<plugin-name>"
echo "Uninstalled <plugin-name>."
```

**Remove** the `PLUGIN_MIN_MAJOR` / `PLUGIN_MAX_MAJOR` version gate from `install.sh` — this is superseded by Homebrew's `depends_on` version constraint in the formula.

---

## draft-pr Changes

`draft-pr.py` imports `select_plugin` from the concrete loader (available via PYTHONPATH set by the bin wrapper):

```python
# before
from devflow_sdk.plugin_loader import select_plugin
plugin = select_plugin(PLUGIN_DIR, DraftPrPlugin, configured_name)

# after
from plugin_loader import select_plugin
plugin = select_plugin(DraftPrPlugin, configured_name)
```

`PLUGIN_DIR` is no longer needed in `draft-pr.py`.

---

## Discovery Flow

```
brew install org/tap/devflow-plugin-foo
  → post_install calls: devflow-plugin register foo /opt/homebrew/opt/devflow-plugin-foo/lib/foo.py --formula org/tap/devflow-plugin-foo
  → ~/.devflow/plugin-registry.json gains entry for "foo"

user runs: devflow draft-pr
  → draft-pr.py calls select_plugin(DraftPrPlugin)
  → PluginLoader.discover() reads plugin-registry.json
  → importlib loads /opt/homebrew/opt/devflow-plugin-foo/lib/foo.py
  → returns FooPlugin instance

brew upgrade devflow
  → new keg, no plugins dir — registry unchanged in ~/.devflow/
  → next run of draft-pr discovers foo exactly as before

brew upgrade devflow-plugin-foo
  → keg updated to new version
  → opt/devflow-plugin-foo/ symlink updated by Homebrew
  → plugin-registry.json path still points to opt/ stable path → resolves to new version
  → no re-registration needed

brew uninstall devflow-plugin-foo
  → plugin-registry.json retains the entry (no Formula uninstall hook exists)
  → next run of draft-pr warns about stale entry; run 'devflow-plugin unregister foo' to clean up
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `plugin-registry.json` does not exist | `list_plugins()` returns `{}` — treated as no plugins registered |
| Registry JSON is malformed | `list_plugins()` prints warning to stderr, returns `{}` |
| Registered plugin `.py` not found at path | `discover()` warns to stderr, skips entry (stale entry from unclean uninstall) |
| Plugin fails to import or instantiate | `discover()` warns to stderr with plugin name, skips |
| No plugins discovered | `select_plugin()` returns `None`; caller (draft-pr) exits with a clear install message |
| `register` called with a name that already exists | Overwrites the existing entry silently |
| `unregister` called with unknown name | No-op, no error |

---

## Testing

### SDK tests (`devflow-sdk/tests/`)

- `test_plugin_registry.py` — new: `PluginEntry` construction and field defaults
- `test_plugin_loader.py` — update: test `PluginLoaderBase` is abstract, cannot be instantiated directly; verify all 5 methods are abstract

### devflow tests (`devflow/plugin-manager/tests/`)

- `test_plugin_loader.py` — new: full integration tests for `PluginLoader`
  - `register` writes correct JSON
  - `register` overwrites existing entry
  - `unregister` removes entry; no-op on missing name
  - `list_plugins` returns `{}` when registry absent
  - `discover` loads valid plugin, skips missing path with warning, skips bad import with warning
  - `select_plugin` auto-selects single plugin; prompts when multiple; returns None when empty
  - Atomic write: concurrent `register` calls do not corrupt registry

### Scaffold tests (`devflow-plugin-scaffold/tests/`)

- Update assertions: formula template present, `install.sh` calls `devflow-plugin register`, no `PLUGIN_MIN_MAJOR` variable

---

## Files Touched

| File | Change |
|---|---|
| `devflow-sdk/devflow_sdk/plugin_registry.py` | New — `PluginEntry` dataclass |
| `devflow-sdk/devflow_sdk/plugin_loader.py` | Replace functions with `PluginLoaderBase` ABC |
| `devflow-sdk/tests/test_plugin_registry.py` | New |
| `devflow-sdk/tests/test_plugin_loader.py` | Update for ABC |
| `devflow/plugin-manager/plugin_loader.py` | New — `PluginLoader` implementation + CLI |
| `devflow/plugin-manager/tests/test_plugin_loader.py` | New |
| `devflow/draft-pr/draft-pr.py` | Update import path; remove `PLUGIN_DIR` |
| `homebrew-devflow/Formula/devflow.rb` | Remove plugins dir/symlink; add `devflow-plugin` bin; update PYTHONPATH in all bin wrappers |
| `devflow-plugin-scaffold/scaffold.sh` | Add formula template; update install.sh/uninstall.sh; remove version gate |
| `devflow-plugin-scaffold/tests/release.sh` | Update assertions |

---

## Migration for Existing Plugin Authors

Existing plugins installed via `install.sh` continue to work unchanged during a transition period — the `install.sh` path now calls `devflow-plugin register` instead of copying a `.py` file, so the migration is a one-line change in the plugin's `install.sh`.

Plugins distributed via Homebrew gain a formula (scaffold generates the template). Authors add the formula to their tap and point users to `brew install` instead of `bash install.sh`.

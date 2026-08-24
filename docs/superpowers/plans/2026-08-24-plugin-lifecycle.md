# Plugin Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable plugins to self-register at Homebrew install time and be discovered dynamically, surviving `brew upgrade devflow` without manual re-install.

**Architecture:** SDK defines `PluginEntry` dataclass and `PluginLoaderBase` ABC as pure contracts; `devflow/plugin-manager/plugin_loader.py` provides the concrete `PluginLoader` implementation that reads/writes `~/.devflow/plugin-registry.json` and doubles as the `devflow-plugin` CLI. Plugin Homebrew formulas call `devflow-plugin register/unregister` in `post_install`/`uninstall_formula`.

**Tech Stack:** Python 3.9+, stdlib (`abc`, `importlib`, `json`, `argparse`, `tempfile`), `devflow_sdk`, `questionary` (via SDK)

**Spec:** `docs/superpowers/specs/2026-08-24-plugin-lifecycle-design.md`

## Global Constraints

- Implementation agents: **Haiku family only**
- Review agents: **Sonnet 5 maximum**
- Python minimum: 3.9
- No new third-party dependencies — use only stdlib and existing vendored packages
- Atomic registry writes: always write to temp file and `os.rename()` into place
- `REGISTRY_PATH` must not appear anywhere in `devflow-sdk/`
- `devflow-plugin register/unregister` print nothing on success (Homebrew `post_install` convention)

---

### Task 1: SDK — `PluginEntry` dataclass

**Files:**
- Create: `devflow-sdk/devflow_sdk/plugin_registry.py`
- Create: `devflow-sdk/tests/test_plugin_registry.py`

**Interfaces:**
- Produces: `PluginEntry(name: str, path: str, formula: str | None = None)` — imported by Task 2 and Task 3

- [ ] **Step 1: Write the failing test**

```python
# devflow-sdk/tests/test_plugin_registry.py
import unittest
from devflow_sdk.plugin_registry import PluginEntry


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

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd devflow-sdk && pytest tests/test_plugin_registry.py -v
```
Expected: `ModuleNotFoundError: No module named 'devflow_sdk.plugin_registry'`

- [ ] **Step 3: Implement `plugin_registry.py`**

```python
# devflow-sdk/devflow_sdk/plugin_registry.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class PluginEntry:
    name: str
    path: str
    formula: str | None = None
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
cd devflow-sdk && pytest tests/test_plugin_registry.py -v
```
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add devflow-sdk/devflow_sdk/plugin_registry.py devflow-sdk/tests/test_plugin_registry.py
git commit -m "feat(sdk): add PluginEntry dataclass to plugin_registry"
```

---

### Task 2: SDK — `PluginLoaderBase` ABC

**Files:**
- Modify: `devflow-sdk/devflow_sdk/plugin_loader.py` (replace entire file — current module-level functions are removed)
- Modify: `devflow-sdk/tests/test_plugin_loader.py` (replace entire file — old tests cover functions that no longer exist here)

**Interfaces:**
- Consumes: `PluginEntry` from `devflow_sdk.plugin_registry` (Task 1)
- Produces: `PluginLoaderBase` ABC with 5 abstract methods: `register`, `unregister`, `list_plugins`, `discover`, `select_plugin` — imported by Task 3

**Note:** Removing the module-level `discover()` and `select_plugin()` from the SDK breaks `draft-pr.py`'s import. Task 5 fixes that. Do not run `draft-pr` tests until Task 5 is complete.

- [ ] **Step 1: Write the failing test**

```python
# devflow-sdk/tests/test_plugin_loader.py
import unittest
from devflow_sdk.plugin_loader import PluginLoaderBase


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
            # list_plugins, discover, select_plugin intentionally missing

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

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd devflow-sdk && pytest tests/test_plugin_loader.py -v
```
Expected: `ImportError` or failures because `PluginLoaderBase` does not yet exist.

- [ ] **Step 3: Replace `plugin_loader.py` with the ABC**

```python
# devflow-sdk/devflow_sdk/plugin_loader.py
from __future__ import annotations
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

- [ ] **Step 4: Run the test to confirm it passes**

```bash
cd devflow-sdk && pytest tests/test_plugin_loader.py -v
```
Expected: 4 tests PASS

- [ ] **Step 5: Run the full SDK test suite to confirm no other regressions**

```bash
cd devflow-sdk && pytest tests/ -v
```
Expected: all tests pass except any in `test_plugin_loader.py` that relied on the old functions (those were fully replaced in Step 1).

- [ ] **Step 6: Commit**

```bash
git add devflow-sdk/devflow_sdk/plugin_loader.py devflow-sdk/tests/test_plugin_loader.py
git commit -m "feat(sdk): replace plugin_loader functions with PluginLoaderBase ABC"
```

---

### Task 3: devflow — `PluginLoader` implementation

**Files:**
- Create: `devflow/plugin-manager/plugin_loader.py`
- Create: `devflow/plugin-manager/tests/__init__.py` (empty)
- Create: `devflow/plugin-manager/tests/test_plugin_loader.py`

**Interfaces:**
- Consumes: `PluginLoaderBase` from `devflow_sdk.plugin_loader` (Task 2); `PluginEntry` from `devflow_sdk.plugin_registry` (Task 1); `select` from `devflow_sdk.prompts`
- Produces:
  - `PluginLoader(registry_path=REGISTRY_PATH)` class
  - Module-level shortcuts: `register`, `unregister`, `list_plugins`, `discover`, `select_plugin`
  - `REGISTRY_PATH: Path` constant

- [ ] **Step 1: Write the failing tests**

```python
# devflow/plugin-manager/tests/test_plugin_loader.py
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from plugin_loader import PluginLoader

from devflow_sdk.draft_pr_plugin import DraftPrPlugin

_VALID_PLUGIN = textwrap.dedent("""\
    from devflow_sdk.draft_pr_plugin import DraftPrPlugin

    class TestPlugin(DraftPrPlugin):
        name = "Test"
        def get_questions(self, data): return []
        def build_prompt(self, data, user_inputs): return "prompt"
        def build_body(self, ai_result, user_inputs): return "body"
""")

_BROKEN_PLUGIN = "import nonexistent_module_xyz_abc"


def _write_plugin(directory, filename, content):
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        f.write(content)
    return path


class TestRegistryIO(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry_path = Path(self.tmpdir) / "plugin-registry.json"
        self.loader = PluginLoader(registry_path=self.registry_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_list_plugins_empty_when_no_registry(self):
        self.assertEqual(self.loader.list_plugins(), {})

    def test_register_creates_registry_file(self):
        self.loader.register("my-plugin", "/some/path.py")
        self.assertTrue(self.registry_path.exists())

    def test_register_stores_entry(self):
        self.loader.register("my-plugin", "/some/path.py", formula="org/tap/devflow-plugin-my")
        plugins = self.loader.list_plugins()
        self.assertIn("my-plugin", plugins)
        self.assertEqual(plugins["my-plugin"].path, "/some/path.py")
        self.assertEqual(plugins["my-plugin"].formula, "org/tap/devflow-plugin-my")

    def test_register_overwrites_existing(self):
        self.loader.register("my-plugin", "/old/path.py")
        self.loader.register("my-plugin", "/new/path.py")
        self.assertEqual(self.loader.list_plugins()["my-plugin"].path, "/new/path.py")

    def test_unregister_removes_entry(self):
        self.loader.register("my-plugin", "/some/path.py")
        self.loader.unregister("my-plugin")
        self.assertNotIn("my-plugin", self.loader.list_plugins())

    def test_unregister_noop_on_missing_name(self):
        self.loader.unregister("nonexistent")
        self.assertEqual(self.loader.list_plugins(), {})

    def test_register_multiple_plugins(self):
        self.loader.register("alpha", "/alpha.py")
        self.loader.register("beta", "/beta.py")
        plugins = self.loader.list_plugins()
        self.assertIn("alpha", plugins)
        self.assertIn("beta", plugins)

    def test_registry_json_version_is_1(self):
        self.loader.register("my-plugin", "/some/path.py")
        data = json.loads(self.registry_path.read_text())
        self.assertEqual(data["version"], 1)

    def test_registry_json_omits_null_formula(self):
        self.loader.register("my-plugin", "/some/path.py")
        data = json.loads(self.registry_path.read_text())
        self.assertNotIn("formula", data["plugins"]["my-plugin"])

    def test_list_plugins_empty_on_malformed_json(self):
        self.registry_path.write_text("{not valid json")
        with patch("sys.stderr"):
            result = self.loader.list_plugins()
        self.assertEqual(result, {})

    def test_list_plugins_empty_on_wrong_version(self):
        self.registry_path.write_text(json.dumps({"version": 99, "plugins": {}}))
        with patch("sys.stderr"):
            result = self.loader.list_plugins()
        self.assertEqual(result, {})


class TestDiscover(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry_path = Path(self.tmpdir) / "plugin-registry.json"
        self.plugin_dir = tempfile.mkdtemp()
        self.loader = PluginLoader(registry_path=self.registry_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        shutil.rmtree(self.plugin_dir, ignore_errors=True)

    def test_discover_empty_with_no_registry(self):
        self.assertEqual(self.loader.discover(DraftPrPlugin), {})

    def test_discover_loads_registered_plugin(self):
        path = _write_plugin(self.plugin_dir, "test_plugin.py", _VALID_PLUGIN)
        self.loader.register("test-plugin", path)
        result = self.loader.discover(DraftPrPlugin)
        self.assertIn("test-plugin", result)
        self.assertIsInstance(result["test-plugin"], DraftPrPlugin)

    def test_discover_warns_and_skips_missing_path(self):
        self.loader.register("ghost", "/nonexistent/ghost.py")
        with patch("sys.stderr") as mock_err:
            result = self.loader.discover(DraftPrPlugin)
        self.assertEqual(result, {})
        output = "".join(c.args[0] for c in mock_err.write.call_args_list)
        self.assertIn("ghost", output)

    def test_discover_warns_and_skips_broken_import(self):
        path = _write_plugin(self.plugin_dir, "broken.py", _BROKEN_PLUGIN)
        self.loader.register("broken", path)
        with patch("sys.stderr") as mock_err:
            result = self.loader.discover(DraftPrPlugin)
        self.assertEqual(result, {})
        output = "".join(c.args[0] for c in mock_err.write.call_args_list)
        self.assertIn("broken", output)


class TestSelectPlugin(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry_path = Path(self.tmpdir) / "plugin-registry.json"
        self.plugin_dir = tempfile.mkdtemp()
        self.loader = PluginLoader(registry_path=self.registry_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        shutil.rmtree(self.plugin_dir, ignore_errors=True)

    def _register(self, name, src=_VALID_PLUGIN):
        path = _write_plugin(self.plugin_dir, f"{name.replace('-', '_')}.py", src)
        self.loader.register(name, path)

    def test_returns_none_when_no_plugins(self):
        self.assertIsNone(self.loader.select_plugin(DraftPrPlugin))

    def test_auto_selects_single_plugin(self):
        self._register("only-plugin")
        result = self.loader.select_plugin(DraftPrPlugin)
        self.assertIsInstance(result, DraftPrPlugin)

    def test_returns_configured_plugin_by_name(self):
        self._register("my-plugin")
        result = self.loader.select_plugin(DraftPrPlugin, configured_name="my-plugin")
        self.assertIsInstance(result, DraftPrPlugin)

    def test_warns_and_falls_back_when_configured_name_missing(self):
        self._register("my-plugin")
        with patch("sys.stderr"):
            result = self.loader.select_plugin(DraftPrPlugin, configured_name="missing")
        self.assertIsInstance(result, DraftPrPlugin)

    def test_prompts_when_multiple_plugins(self):
        src_a = _VALID_PLUGIN.replace("TestPlugin", "APlugin").replace('"Test"', '"A"')
        src_b = _VALID_PLUGIN.replace("TestPlugin", "BPlugin").replace('"Test"', '"B"')
        path_a = _write_plugin(self.plugin_dir, "a_plugin.py", src_a)
        path_b = _write_plugin(self.plugin_dir, "b_plugin.py", src_b)
        self.loader.register("a-plugin", path_a)
        self.loader.register("b-plugin", path_b)
        with patch("plugin_loader.select", return_value="a-plugin"):
            result = self.loader.select_plugin(DraftPrPlugin)
        self.assertIsInstance(result, DraftPrPlugin)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
PYTHONPATH=devflow/plugin-manager:devflow-sdk pytest devflow/plugin-manager/tests/test_plugin_loader.py -v
```
Expected: `ModuleNotFoundError: No module named 'plugin_loader'`

- [ ] **Step 3: Create the empty `tests/__init__.py`**

Create `devflow/plugin-manager/tests/__init__.py` as an empty file.

- [ ] **Step 4: Implement `plugin_loader.py`**

```python
# devflow/plugin-manager/plugin_loader.py
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import TypeVar

from devflow_sdk.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin_registry import PluginEntry
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


class PluginLoader(PluginLoaderBase):

    def __init__(self, registry_path: Path = REGISTRY_PATH) -> None:
        self._registry_path = registry_path

    def register(self, name: str, path: str, formula: str | None = None) -> None:
        plugins = _load_registry(self._registry_path)
        plugins[name] = PluginEntry(name=name, path=path, formula=formula)
        _save_registry(plugins, self._registry_path)

    def unregister(self, name: str) -> None:
        plugins = _load_registry(self._registry_path)
        if name in plugins:
            del plugins[name]
            _save_registry(plugins, self._registry_path)

    def list_plugins(self) -> dict[str, PluginEntry]:
        return _load_registry(self._registry_path)

    def discover(self, base_cls: type[T]) -> dict[str, T]:
        found: dict[str, T] = {}
        for name, entry in _load_registry(self._registry_path).items():
            path = Path(entry.path)
            if not path.exists():
                print(
                    f"[devflow] Warning: plugin '{name}' not found at {path}. "
                    f"Run 'devflow-plugin unregister {name}' to clean up.",
                    file=sys.stderr,
                )
                continue
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

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
PYTHONPATH=devflow/plugin-manager:devflow-sdk pytest devflow/plugin-manager/tests/test_plugin_loader.py -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add devflow/plugin-manager/plugin_loader.py devflow/plugin-manager/tests/__init__.py devflow/plugin-manager/tests/test_plugin_loader.py
git commit -m "feat(devflow): add PluginLoader implementation and devflow-plugin CLI"
```

---

### Task 4: draft-pr — update imports to use concrete `PluginLoader`

**Files:**
- Modify: `devflow/draft-pr/draft-pr.py`

**Interfaces:**
- Consumes: `select_plugin`, `discover` module-level shortcuts from `plugin_loader` (Task 3)
- The `plugin_loader` module is on `sys.path` in two ways: (a) injected by the Homebrew bin wrapper (Task 5), (b) injected manually in the script for dev-mode use.

- [ ] **Step 1: Open `devflow/draft-pr/draft-pr.py` and locate these lines**

Current state around line 8–17:
```python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
sys.path.insert(0, SCRIPT_DIR)
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)

from devflow_sdk.ai import run_ai_prompt
...
from devflow_sdk.plugin_loader import select_plugin
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
```

And the `PLUGIN_DIR` constant near line 19:
```python
PLUGIN_DIR = os.path.join(SCRIPT_DIR, "plugins")
```

And the `select_plugin` call in `main()`:
```python
plugin = select_plugin(PLUGIN_DIR, DraftPrPlugin, configured_plugin_name)
if plugin is None:
    print(f"Error: no plugins found in {PLUGIN_DIR}", file=sys.stderr)
    print("Install a plugin into the plugins directory to continue.", file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 2: Apply the three changes**

**Change 1** — add `plugin-manager` to `sys.path` (dev mode) after the vendor wheel loop:

```python
# After the vendor whl loop, add:
PLUGIN_MANAGER_DIR = os.path.join(REPO_ROOT, "plugin-manager")
sys.path.insert(0, PLUGIN_MANAGER_DIR)
```

**Change 2** — replace the `plugin_loader` import and remove `PLUGIN_DIR`:

```python
# Replace:
from devflow_sdk.plugin_loader import select_plugin

# With:
from plugin_loader import select_plugin

# Delete the line:
PLUGIN_DIR = os.path.join(SCRIPT_DIR, "plugins")
```

**Change 3** — update the `select_plugin` call and error message in `main()`:

```python
# Replace:
plugin = select_plugin(PLUGIN_DIR, DraftPrPlugin, configured_plugin_name)
if plugin is None:
    print(f"Error: no plugins found in {PLUGIN_DIR}", file=sys.stderr)
    print("Install a plugin into the plugins directory to continue.", file=sys.stderr)
    sys.exit(1)

# With:
plugin = select_plugin(DraftPrPlugin, configured_plugin_name)
if plugin is None:
    print("Error: no plugins registered.", file=sys.stderr)
    print("Install a plugin with: brew install <plugin-formula>", file=sys.stderr)
    print("Or run 'devflow-plugin list' to see what is installed.", file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 3: Run the draft-pr tests to confirm no regressions**

```bash
PYTHONPATH=devflow/draft-pr:devflow/plugin-manager:devflow-sdk pytest devflow/draft-pr/tests/ -v
```
Expected: all tests PASS (any test that mocked `devflow_sdk.plugin_loader.select_plugin` will need to be updated to mock `plugin_loader.select_plugin` instead — fix those inline if they fail)

- [ ] **Step 4: Commit**

```bash
git add devflow/draft-pr/draft-pr.py
git commit -m "fix(draft-pr): import select_plugin from plugin_loader, remove PLUGIN_DIR"
```

---

### Task 5: Homebrew formula — `devflow-plugin` bin + PYTHONPATH + remove keg plugins dir

**Files:**
- Modify: `homebrew-devflow/Formula/devflow.rb`

- [ ] **Step 1: Open the formula and locate the `install` block**

Current install block (lines 12–33):
```ruby
def install
  libexec.install Dir["devflow/*"]

  python_packages = libexec/"python-packages"
  python_packages.mkpath
  Dir["#{libexec}/vendor/*.whl"].each do |whl|
    system "pip3", "install", "--no-deps", "--target=#{python_packages}", whl
  end

  (lib/"devflow/plugins").mkpath
  rm_rf(libexec/"draft-pr/plugins")
  (libexec/"draft-pr/plugins").make_symlink(lib/"devflow/plugins")

  %w[draft-pr address-pr squash-commits finish-issue start-issue].each do |tool|
    (bin/tool).write <<~BASH
      #!/bin/bash
      export PYTHONPATH="#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
      exec python3 "#{libexec}/#{tool}/#{tool}.py" "$@"
    BASH
    (bin/tool).chmod 0755
  end
end
```

- [ ] **Step 2: Apply the changes**

Replace the entire `install` block with:

```ruby
def install
  libexec.install Dir["devflow/*"]

  python_packages = libexec/"python-packages"
  python_packages.mkpath
  Dir["#{libexec}/vendor/*.whl"].each do |whl|
    system "pip3", "install", "--no-deps", "--target=#{python_packages}", whl
  end

  %w[draft-pr address-pr squash-commits finish-issue start-issue].each do |tool|
    (bin/tool).write <<~BASH
      #!/bin/bash
      export PYTHONPATH="#{libexec}/plugin-manager:#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
      exec python3 "#{libexec}/#{tool}/#{tool}.py" "$@"
    BASH
    (bin/tool).chmod 0755
  end

  (bin/"devflow-plugin").write <<~BASH
    #!/bin/bash
    export PYTHONPATH="#{libexec}/plugin-manager:#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
    exec python3 "#{libexec}/plugin-manager/plugin_loader.py" "$@"
  BASH
  (bin/"devflow-plugin").chmod 0755
end
```

Key changes: removed the 3 lines creating `lib/devflow/plugins/` and the symlink; added `libexec/plugin-manager` to `PYTHONPATH` in all bin wrappers; added `devflow-plugin` bin wrapper.

- [ ] **Step 3: Verify the formula syntax**

```bash
brew audit --strict homebrew-devflow/Formula/devflow.rb 2>/dev/null || ruby -c homebrew-devflow/Formula/devflow.rb
```
Expected: no syntax errors (brew audit may warn about non-tap constraints — ignore warnings, only care about errors)

- [ ] **Step 4: Commit**

```bash
git add homebrew-devflow/Formula/devflow.rb
git commit -m "fix(homebrew): add devflow-plugin bin, add plugin-manager to PYTHONPATH, remove keg plugins dir"
```

---

### Task 6: Scaffold — Homebrew formula template + updated install/uninstall + remove version gate

**Files:**
- Modify: `devflow-plugin-scaffold/scaffold.sh`
- Modify: `devflow-plugin-scaffold/tests/test_scaffold.sh`

**What changes in scaffold.sh:**
1. Add `FORMULA_CLASS_NAME` derivation
2. Add Homebrew formula template generation (`Formula/devflow-plugin-<name>.rb`)
3. Replace `install.sh` template — call `devflow-plugin register` instead of copying .py
4. Replace `uninstall.sh` template — call `devflow-plugin unregister`
5. Remove `DEVFLOW_MAJOR_STAMP` detection and the version gate block in `install.sh`
6. Remove `PLUGIN_MIN_MAJOR`/`PLUGIN_MAX_MAJOR` warning from `scripts/release.sh` template; replace with a note about updating the formula's `depends_on`
7. Update `mkdir` line to create `Formula/` directory alongside the others

- [ ] **Step 1: Update `test_scaffold.sh` to reflect new expected outputs**

In `devflow-plugin-scaffold/tests/test_scaffold.sh`, make these changes:

**Remove** these assertions (they reference the old version gate):
```bash
has_content "$D/install.sh"    "PLUGIN_MIN_MAJOR="
has_content "$D/install.sh"    "PLUGIN_MAX_MAJOR="
has_content "$D/install.sh"    "incompatible"
has_content "$D/scripts/release.sh"  "PLUGIN_MIN_MAJOR"
has_content "$D/scripts/release.sh"  "PLUGIN_MAX_MAJOR"
```

**Update** the install/uninstall assertions:
```bash
# Replace:
has_content "$D/install.sh"   "acme_format.py"
has_content "$D/uninstall.sh" "acme_format.py"

# With:
has_content "$D/install.sh"   "devflow-plugin"
has_content "$D/install.sh"   "register"
has_content "$D/install.sh"   "acme-format"
has_content "$D/uninstall.sh" "devflow-plugin"
has_content "$D/uninstall.sh" "unregister"
has_content "$D/uninstall.sh" "acme-format"
```

**Add** assertions for the new formula file:
```bash
file_exists "$D/Formula/devflow-plugin-acme-format.rb"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "DevflowPluginAcmeFormat"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "depends_on"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "devflow-plugin"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "register"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "post_install"
has_content "$D/Formula/devflow-plugin-acme-format.rb"  "uninstall_formula"
```

Keep the `Major release detected` assertion — the warning still exists, just updated text.

- [ ] **Step 2: Run the tests to confirm they now fail on the new assertions**

```bash
bash devflow-plugin-scaffold/tests/test_scaffold.sh
```
Expected: FAIL on the new `file_exists "$D/Formula/..."` and updated install.sh assertions.

- [ ] **Step 3: Update `scaffold.sh`**

**3a.** Find the `DEVFLOW_MAJOR_STAMP` line and remove it (two lines):
```bash
# Remove:
DEVFLOW_MAJOR_STAMP="$(brew list --versions devflow 2>/dev/null | awk '{print $2}' | cut -d. -f1)" || true
DEVFLOW_MAJOR_STAMP="${DEVFLOW_MAJOR_STAMP:-0}"
```

**3b.** After the existing identifier derivations, add `FORMULA_CLASS_NAME`:
```bash
# Derive Ruby formula class name: DevflowPlugin<PascalCase of plugin-name>
FORMULA_CLASS_NAME="DevflowPlugin$(printf '%s' "$PLUGIN_NAME" | tr '-' '\n' | \
    awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}' | tr -d '\n')"
```

**3c.** Update the `mkdir` line to also create `Formula/`:
```bash
# Replace:
mkdir -p "$PLUGIN_NAME/tests" "$PLUGIN_NAME/.github/workflows" "$PLUGIN_NAME/scripts"

# With:
mkdir -p "$PLUGIN_NAME/tests" "$PLUGIN_NAME/.github/workflows" "$PLUGIN_NAME/scripts" "$PLUGIN_NAME/Formula"
```

**3d.** Replace the `install.sh` template (the `cat > "$PLUGIN_NAME/install.sh"` heredoc) with:
```bash
cat > "$PLUGIN_NAME/install.sh" << EOF
#!/bin/bash
# Development convenience install — for Homebrew distribution use Formula/ instead.
set -euo pipefail
PLUGIN_DIR="\$(cd "\$(dirname "\$0")" && pwd)"
devflow-plugin register "${PLUGIN_NAME}" "\$PLUGIN_DIR/${MODULE_NAME}.py"
echo "Installed ${PLUGIN_NAME}."
EOF
chmod +x "$PLUGIN_NAME/install.sh"
```

**3e.** Replace the `uninstall.sh` template with:
```bash
cat > "$PLUGIN_NAME/uninstall.sh" << EOF
#!/bin/bash
set -euo pipefail
devflow-plugin unregister "${PLUGIN_NAME}"
echo "Uninstalled ${PLUGIN_NAME}."
EOF
chmod +x "$PLUGIN_NAME/uninstall.sh"
```

**3f.** Add the Homebrew formula template after `uninstall.sh`. Insert this block before the `pyproject.toml` generation:
```bash
cat > "$PLUGIN_NAME/Formula/devflow-plugin-${PLUGIN_NAME}.rb" << EOF
class ${FORMULA_CLASS_NAME} < Formula
  desc "devflow plugin: ${DISPLAY_NAME}"
  homepage "<your-plugin-homepage>"
  url "<release-url-to-${MODULE_NAME}.py>"
  sha256 "<sha256-of-${MODULE_NAME}.py>"
  version "0.1.0"

  depends_on "captainwonderwall/devflow/devflow"

  def install
    lib.install "${MODULE_NAME}.py"
  end

  def post_install
    system "\#{HOMEBREW_PREFIX}/bin/devflow-plugin",
           "register", "${PLUGIN_NAME}",
           "\#{opt_lib}/${MODULE_NAME}.py",
           "--formula", "<your-tap>/${PLUGIN_NAME}"
  end

  def uninstall_formula
    system "\#{HOMEBREW_PREFIX}/bin/devflow-plugin",
           "unregister", "${PLUGIN_NAME}"
  end

  test do
    system "\#{HOMEBREW_PREFIX}/bin/devflow-plugin", "list"
  end
end
EOF
```

**3g.** In the `scripts/release.sh` template, find the major-bump warning block:
```bash
if [ "$NEW_MAJOR" -gt "$OLD_MAJOR" ] 2>/dev/null; then
    echo "Major release detected. Before tagging, update install.sh:"
    echo "  PLUGIN_MIN_MAJOR=\"$NEW_MAJOR\""
    echo "  PLUGIN_MAX_MAJOR=\"$NEW_MAJOR\""
    echo ""
fi
```

Replace with:
```bash
if [ "$NEW_MAJOR" -gt "$OLD_MAJOR" ] 2>/dev/null; then
    echo "Major release detected. Before tagging, update your Homebrew formula"
    echo "to constrain the devflow dependency to the new major version."
    echo "  depends_on \"captainwonderwall/devflow/devflow\" # ensure v$NEW_MAJOR compatibility"
    echo ""
fi
```

- [ ] **Step 4: Run the scaffold tests to confirm they pass**

```bash
bash devflow-plugin-scaffold/tests/test_scaffold.sh
```
Expected: all assertions PASS

- [ ] **Step 5: Commit**

```bash
git add devflow-plugin-scaffold/scaffold.sh devflow-plugin-scaffold/tests/test_scaffold.sh
git commit -m "feat(scaffold): replace install.sh version gate with Homebrew formula template"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Covered by |
|---|---|
| `PluginEntry` in SDK, no filesystem paths | Task 1 |
| `PluginLoaderBase` ABC with 5 methods in SDK | Task 2 |
| `PluginLoader` concrete implementation in devflow | Task 3 |
| `REGISTRY_PATH` only in devflow | Task 3 (constant defined in plugin_loader.py, never in SDK) |
| `devflow-plugin` CLI (register/unregister/list) | Task 3 (\_\_main\_\_ block) |
| Atomic registry writes | Task 3 (mkstemp + os.rename) |
| draft-pr imports from plugin_loader | Task 4 |
| PLUGIN_DIR removed from draft-pr | Task 4 |
| Homebrew formula: remove keg plugins dir | Task 5 |
| Homebrew formula: devflow-plugin bin wrapper | Task 5 |
| Homebrew formula: plugin-manager in PYTHONPATH | Task 5 |
| Scaffold: Homebrew formula template | Task 6 |
| Scaffold: updated install.sh calls devflow-plugin register | Task 6 |
| Scaffold: updated uninstall.sh calls devflow-plugin unregister | Task 6 |
| Scaffold: version gate removed from install.sh | Task 6 |
| Stale entry warning in discover() | Task 3 |
| list prints "No plugins registered." when empty | Task 3 |

### Placeholder scan

No TBD, TODO, or missing code blocks found.

### Type consistency

- `PluginEntry` defined in Task 1, used by name consistently in Tasks 2, 3
- `PluginLoaderBase` defined in Task 2, subclassed as `PluginLoader` in Task 3
- `_load_registry(registry_path)` / `_save_registry(plugins, registry_path)` — both take optional `registry_path` for testability, consistent across Task 3
- `select_plugin(DraftPrPlugin, configured_plugin_name)` in Task 4 matches the signature `select_plugin(base_cls, configured_name=None)` defined in Task 3
- `patch("plugin_loader.select", ...)` in Task 3 tests matches `from devflow_sdk.prompts import select` at module level in Task 3 implementation

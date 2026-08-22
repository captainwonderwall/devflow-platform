# Plugin Loader SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move plugin discovery and selection from `draft-pr` into `devflow-sdk`, split `PluginBase` into a generic marker and a draft-pr-specific abstract class, and add an install-time compatibility check to the plugin scaffold.

**Architecture:** `PluginBase` becomes a name-only marker in the SDK; `DraftPrPlugin(PluginBase)` holds the draft-pr abstract contract. `discover()` and `select_plugin()` move into `devflow_sdk/plugin_loader.py`. The scaffold's `install.sh` gains a devflow major-version check, and `release.sh` gains a major-bump reminder.

**Tech Stack:** Python 3.11+, `abc`, `importlib.util`, `inspect`, `unittest.mock`, bash

**Spec:** `docs/superpowers/specs/2026-08-21-plugin-loader-sdk-design.md`

## Global Constraints

- **Implementation agents: Haiku family only** — any agent writing or editing code must use a Haiku model
- **Review agents: Sonnet 5 maximum** — no model above Sonnet 5 for code review or spec review
- Python minimum: 3.11
- All new SDK modules live under `devflow-sdk/devflow_sdk/`
- All SDK tests live under `devflow-sdk/tests/`
- Do not add `sdk_version`, `is_compatible()`, or any version field to `PluginBase` or `DraftPrPlugin`
- `select_plugin()` returns `None` (not raises) when no plugins are found
- `discover()` emits a named stderr warning (not silently swallows) when a plugin file fails to load

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `devflow-sdk/devflow_sdk/plugin_base.py` | Modify | Generic marker: `name: str = ""` only |
| `devflow-sdk/devflow_sdk/draft_pr_plugin.py` | Create | draft-pr abstract contract (`get_questions`, `build_prompt`, `build_body`) |
| `devflow-sdk/devflow_sdk/plugin_loader.py` | Create | `discover(plugin_dir, base_cls)` + `select_plugin(plugin_dir, base_cls, configured_name)` |
| `devflow-sdk/tests/test_plugin_base.py` | Modify | Tests for generic marker only |
| `devflow-sdk/tests/test_draft_pr_plugin.py` | Create | Tests for `DraftPrPlugin` contract |
| `devflow-sdk/tests/test_plugin_loader.py` | Create | Tests for `discover()` and `select_plugin()` |
| `devflow/draft-pr/plugin_loader.py` | Delete | Replaced by SDK |
| `devflow/draft-pr/tests/test_plugin_loader.py` | Delete | Covered by SDK tests |
| `devflow/draft-pr/draft-pr.py` | Modify | Import from SDK, replace selection block |
| `devflow-plugin-scaffold/scaffold.sh` | Modify | Update stub import + `install.sh` + `release.sh` templates |
| `devflow-plugin-scaffold/tests/release.sh` | Modify | Assert new import, `install.sh` variables, release.sh reminder |

---

## Task 1: Restructure SDK plugin base

Split `plugin_base.py` into a generic marker and a draft-pr-specific abstract class.

**Files:**
- Modify: `devflow-sdk/devflow_sdk/plugin_base.py`
- Create: `devflow-sdk/devflow_sdk/draft_pr_plugin.py`
- Modify: `devflow-sdk/tests/test_plugin_base.py`
- Create: `devflow-sdk/tests/test_draft_pr_plugin.py`

**Interfaces:**
- Produces:
  - `PluginBase` — `devflow_sdk.plugin_base.PluginBase(ABC)` with `name: str = ""`; **no abstract methods**, instantiable directly
  - `DraftPrPlugin` — `devflow_sdk.draft_pr_plugin.DraftPrPlugin(PluginBase)` with three `@abstractmethod`s: `get_questions(self, data: dict) -> list[dict]`, `build_prompt(self, data: dict, user_inputs: dict) -> str`, `build_body(self, ai_result: dict, user_inputs: dict) -> str`

- [ ] **Step 1: Write failing tests for the new `plugin_base.py`**

`devflow-sdk/tests/test_plugin_base.py` — replace the entire file:

```python
from devflow_sdk.plugin_base import PluginBase


def test_plugin_base_is_instantiable():
    # PluginBase is a marker — no abstract methods, can be instantiated directly
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

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_base.py -v
```

Expected: `test_plugin_base_is_instantiable` FAILS with `TypeError: Can't instantiate abstract class` (current `PluginBase` has abstract methods).

- [ ] **Step 3: Strip `plugin_base.py` to generic marker**

Replace the entire content of `devflow-sdk/devflow_sdk/plugin_base.py`:

```python
from abc import ABC


class PluginBase(ABC):
    name: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_base.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Write failing tests for `DraftPrPlugin`**

Create `devflow-sdk/tests/test_draft_pr_plugin.py`:

```python
import pytest
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
from devflow_sdk.plugin_base import PluginBase


def test_draft_pr_plugin_is_subclass_of_plugin_base():
    assert issubclass(DraftPrPlugin, PluginBase)


def test_draft_pr_plugin_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        DraftPrPlugin()


def test_incomplete_subclass_missing_build_body_cannot_be_instantiated():
    class Incomplete(DraftPrPlugin):
        name = "test"
        def get_questions(self, data): return []
        def build_prompt(self, data, user_inputs): return ""
    with pytest.raises(TypeError):
        Incomplete()


def test_complete_subclass_instantiates_and_delegates():
    class Complete(DraftPrPlugin):
        name = "Complete"
        def get_questions(self, data): return [{"id": "q1", "text": "Who?"}]
        def build_prompt(self, data, user_inputs): return "my prompt"
        def build_body(self, ai_result, user_inputs): return "# Body"

    plugin = Complete()
    assert plugin.name == "Complete"
    assert plugin.get_questions({}) == [{"id": "q1", "text": "Who?"}]
    assert plugin.build_prompt({}, {}) == "my prompt"
    assert plugin.build_body({}, {}) == "# Body"


def test_plugin_name_defaults_to_empty_string():
    class NoName(DraftPrPlugin):
        def get_questions(self, data): return []
        def build_prompt(self, data, user_inputs): return ""
        def build_body(self, ai_result, user_inputs): return ""
    assert NoName.name == ""
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_draft_pr_plugin.py -v
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'devflow_sdk.draft_pr_plugin'`.

- [ ] **Step 7: Create `draft_pr_plugin.py`**

Create `devflow-sdk/devflow_sdk/draft_pr_plugin.py`:

```python
from abc import abstractmethod

from devflow_sdk.plugin_base import PluginBase


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

- [ ] **Step 8: Run all SDK tests to verify they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_base.py tests/test_draft_pr_plugin.py -v
```

Expected: all 9 PASS.

- [ ] **Step 9: Commit**

```bash
git add devflow-sdk/devflow_sdk/plugin_base.py \
        devflow-sdk/devflow_sdk/draft_pr_plugin.py \
        devflow-sdk/tests/test_plugin_base.py \
        devflow-sdk/tests/test_draft_pr_plugin.py
git commit -m "feat: split PluginBase into generic marker and DraftPrPlugin"
```

---

## Task 2: Add SDK plugin loader

Create `devflow_sdk/plugin_loader.py` with `discover()` and `select_plugin()`.

**Files:**
- Create: `devflow-sdk/devflow_sdk/plugin_loader.py`
- Create: `devflow-sdk/tests/test_plugin_loader.py`

**Interfaces:**
- Consumes (from Task 1):
  - `PluginBase` from `devflow_sdk.plugin_base`
  - `DraftPrPlugin` from `devflow_sdk.draft_pr_plugin`
- Produces:
  - `discover(plugin_dir: str, base_cls: type) -> list[PluginBase]`
  - `select_plugin(plugin_dir: str, base_cls: type, configured_name: str | None = None) -> PluginBase | None`

- [ ] **Step 1: Write failing tests for `discover()`**

Create `devflow-sdk/tests/test_plugin_loader.py`:

```python
import os
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from devflow_sdk.plugin_loader import discover, select_plugin
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
from devflow_sdk.plugin_base import PluginBase


# ── Shared plugin source fixtures ─────────────────────────────────────────────

_VALID_PLUGIN = textwrap.dedent("""\
    from devflow_sdk.draft_pr_plugin import DraftPrPlugin

    class FakePlugin(DraftPrPlugin):
        name = "Fake"
        def get_questions(self, data): return []
        def build_prompt(self, data, user_inputs): return "prompt"
        def build_body(self, ai_result, user_inputs): return "body"
""")

_ABSTRACT_ONLY = textwrap.dedent("""\
    from devflow_sdk.draft_pr_plugin import DraftPrPlugin
    # No concrete subclass
""")

_NON_PLUGIN = textwrap.dedent("""\
    class NotAPlugin:
        pass
""")

_BROKEN_IMPORT = "import nonexistent_module_xyz"


def _write(tmp, name, src):
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write(src)
    return path


def _make_plugin(name):
    class P(DraftPrPlugin):
        def get_questions(self, data): return []
        def build_prompt(self, data, user_inputs): return ""
        def build_body(self, ai_result, user_inputs): return ""
    P.name = name
    return P()


# ── discover() tests ──────────────────────────────────────────────────────────

class TestDiscover(unittest.TestCase):
    def test_returns_empty_list_when_dir_missing(self):
        self.assertEqual(discover("/nonexistent/plugins", DraftPrPlugin), [])

    def test_returns_empty_list_when_dir_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(discover(tmp, DraftPrPlugin), [])

    def test_discovers_concrete_subclass(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "myplugin.py", _VALID_PLUGIN)
            result = discover(tmp, DraftPrPlugin)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Fake")

    def test_returned_items_are_instances_of_base_cls(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "myplugin.py", _VALID_PLUGIN)
            result = discover(tmp, DraftPrPlugin)
        self.assertIsInstance(result[0], DraftPrPlugin)
        self.assertIsInstance(result[0], PluginBase)

    def test_skips_files_starting_with_underscore(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "_private.py", _VALID_PLUGIN)
            self.assertEqual(discover(tmp, DraftPrPlugin), [])

    def test_skips_non_py_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "plugin.txt", _VALID_PLUGIN)
            self.assertEqual(discover(tmp, DraftPrPlugin), [])

    def test_skips_abstract_only_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "abstract.py", _ABSTRACT_ONLY)
            self.assertEqual(discover(tmp, DraftPrPlugin), [])

    def test_skips_non_plugin_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "other.py", _NON_PLUGIN)
            self.assertEqual(discover(tmp, DraftPrPlugin), [])

    def test_warns_stderr_when_plugin_fails_to_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "broken.py", _BROKEN_IMPORT)
            with patch("sys.stderr") as mock_stderr:
                result = discover(tmp, DraftPrPlugin)
        self.assertEqual(result, [])
        mock_stderr.write.assert_called()
        warning = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        self.assertIn("broken.py", warning)
        self.assertIn("incompatible", warning)

    def test_discovers_multiple_plugins_sorted_by_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_a = _VALID_PLUGIN.replace("FakePlugin", "APlugin").replace('"Fake"', '"A"')
            src_b = _VALID_PLUGIN.replace("FakePlugin", "BPlugin").replace('"Fake"', '"B"')
            _write(tmp, "b_format.py", src_b)
            _write(tmp, "a_format.py", src_a)
            result = discover(tmp, DraftPrPlugin)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "A")
        self.assertEqual(result[1].name, "B")

    def test_base_cls_filters_plugins(self):
        # A plugin that only inherits PluginBase (not DraftPrPlugin)
        # should not appear when discovering with DraftPrPlugin as base_cls
        bare_plugin = textwrap.dedent("""\
            from devflow_sdk.plugin_base import PluginBase

            class BarePlugin(PluginBase):
                name = "Bare"
        """)
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "bare.py", bare_plugin)
            result = discover(tmp, DraftPrPlugin)
        self.assertEqual(result, [])


# ── select_plugin() tests ─────────────────────────────────────────────────────

class TestSelectPlugin(unittest.TestCase):
    def test_returns_none_when_no_plugins(self):
        with patch("devflow_sdk.plugin_loader.discover", return_value=[]):
            result = select_plugin("/any", DraftPrPlugin)
        self.assertIsNone(result)

    def test_returns_single_plugin_directly(self):
        plugin = _make_plugin("Acme")
        with patch("devflow_sdk.plugin_loader.discover", return_value=[plugin]):
            result = select_plugin("/any", DraftPrPlugin)
        self.assertIs(result, plugin)

    def test_returns_configured_plugin_by_name(self):
        a = _make_plugin("Alpha")
        b = _make_plugin("Beta")
        with patch("devflow_sdk.plugin_loader.discover", return_value=[a, b]):
            result = select_plugin("/any", DraftPrPlugin, configured_name="Beta")
        self.assertIs(result, b)

    def test_warns_and_falls_back_to_single_when_configured_name_missing(self):
        plugin = _make_plugin("Acme")
        with patch("devflow_sdk.plugin_loader.discover", return_value=[plugin]):
            with patch("sys.stderr") as mock_stderr:
                result = select_plugin("/any", DraftPrPlugin, configured_name="Missing")
        self.assertIs(result, plugin)
        warning = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        self.assertIn("Missing", warning)

    def test_warns_and_prompts_when_configured_name_missing_and_multiple_plugins(self):
        a = _make_plugin("Alpha")
        b = _make_plugin("Beta")
        with patch("devflow_sdk.plugin_loader.discover", return_value=[a, b]):
            with patch("devflow_sdk.plugin_loader.select", return_value="Beta"):
                with patch("sys.stderr"):
                    result = select_plugin("/any", DraftPrPlugin, configured_name="Missing")
        self.assertIs(result, b)

    def test_prompts_when_multiple_plugins_no_config(self):
        a = _make_plugin("Alpha")
        b = _make_plugin("Beta")
        with patch("devflow_sdk.plugin_loader.discover", return_value=[a, b]):
            with patch("devflow_sdk.plugin_loader.select", return_value="Alpha"):
                result = select_plugin("/any", DraftPrPlugin)
        self.assertIs(result, a)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_loader.py -v
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'devflow_sdk.plugin_loader'`.

- [ ] **Step 3: Create `plugin_loader.py`**

Create `devflow-sdk/devflow_sdk/plugin_loader.py`:

```python
import importlib.util
import inspect
import os
import sys

from devflow_sdk.plugin_base import PluginBase
from devflow_sdk.prompts import select


def discover(plugin_dir: str, base_cls: type) -> list[PluginBase]:
    plugins = []
    if not os.path.isdir(plugin_dir):
        return plugins
    for fname in sorted(os.listdir(plugin_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(plugin_dir, fname)
        try:
            spec = importlib.util.spec_from_file_location(fname[:-3], path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:
            print(
                f"Warning: plugin '{fname}' failed to load — it may be incompatible "
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
                    plugins.append(attr())
                except Exception:
                    print(
                        f"Warning: plugin '{fname}' failed to load — it may be incompatible "
                        "with this version of devflow. Check for an updated release.",
                        file=sys.stderr,
                    )
    return plugins


def select_plugin(
    plugin_dir: str,
    base_cls: type,
    configured_name: str | None = None,
) -> PluginBase | None:
    plugins = discover(plugin_dir, base_cls)
    if not plugins:
        return None

    plugin_names = [p.name or type(p).__name__ for p in plugins]

    if configured_name:
        if configured_name in plugin_names:
            return plugins[plugin_names.index(configured_name)]
        print(
            f"Warning: configured plugin '{configured_name}' not found. "
            f"Available: {', '.join(plugin_names)}",
            file=sys.stderr,
        )

    if len(plugins) == 1:
        return plugins[0]

    chosen = select("Select format", choices=plugin_names)
    return plugins[plugin_names.index(chosen)]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd devflow-sdk && python -m pytest tests/test_plugin_loader.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full SDK test suite**

```bash
cd devflow-sdk && python -m pytest -v
```

Expected: all PASS. No regressions.

- [ ] **Step 6: Commit**

```bash
git add devflow-sdk/devflow_sdk/plugin_loader.py \
        devflow-sdk/tests/test_plugin_loader.py
git commit -m "feat: add discover() and select_plugin() to devflow-sdk"
```

---

## Task 3: Wire draft-pr to SDK loader

Delete `draft-pr/plugin_loader.py`, remove its tests, and update `draft-pr.py` to use the SDK.

**Files:**
- Delete: `devflow/draft-pr/plugin_loader.py`
- Delete: `devflow/draft-pr/tests/test_plugin_loader.py`
- Modify: `devflow/draft-pr/draft-pr.py`

**Interfaces:**
- Consumes (from Task 2):
  - `select_plugin(plugin_dir: str, base_cls: type, configured_name: str | None = None) -> PluginBase | None` from `devflow_sdk.plugin_loader`
  - `DraftPrPlugin` from `devflow_sdk.draft_pr_plugin`

- [ ] **Step 1: Delete the old plugin loader and its tests**

```bash
git rm devflow/draft-pr/plugin_loader.py
git rm devflow/draft-pr/tests/test_plugin_loader.py
```

- [ ] **Step 2: Update imports in `draft-pr.py`**

In `devflow/draft-pr/draft-pr.py`, replace:

```python
from plugin_loader import discover
```

with:

```python
from devflow_sdk.plugin_loader import select_plugin
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
```

- [ ] **Step 3: Replace the plugin selection block in `draft-pr.py`**

In `devflow/draft-pr/draft-pr.py`, find and replace the entire block from `plugins = discover(PLUGIN_DIR)` through the end of the `else:` branch (the ~20-line selection block):

```python
# Remove this entire block:
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

Replace with:

```python
plugin = select_plugin(PLUGIN_DIR, DraftPrPlugin, configured_plugin_name)
if plugin is None:
    print(f"Error: no plugins found in {PLUGIN_DIR}", file=sys.stderr)
    print("Install a plugin into the plugins directory to continue.", file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 4: Run the draft-pr test suite**

```bash
cd devflow/draft-pr && python -m pytest tests/ -v
```

Expected: all PASS. (The deleted `test_plugin_loader.py` is gone; remaining tests unaffected.)

- [ ] **Step 5: Verify the import works end-to-end**

```bash
cd devflow/draft-pr && python -c "
import sys, os
sys.path.insert(0, '.')
import glob
for whl in sorted(glob.glob(os.path.join('..', 'vendor', '*.whl'))):
    sys.path.insert(0, whl)
from devflow_sdk.plugin_loader import select_plugin
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
print('imports OK')
print('select_plugin:', select_plugin)
print('DraftPrPlugin:', DraftPrPlugin)
"
```

Expected output contains `imports OK`.

- [ ] **Step 6: Commit**

```bash
git add devflow/draft-pr/draft-pr.py
git commit -m "feat: wire draft-pr to SDK plugin loader"
```

---

## Task 4: Update scaffold

Update `scaffold.sh` to generate plugins using `DraftPrPlugin`, add the `install.sh` version check, and add the `release.sh` major-bump reminder. Update scaffold tests.

**Files:**
- Modify: `devflow-plugin-scaffold/scaffold.sh`
- Modify: `devflow-plugin-scaffold/tests/release.sh`

**Interfaces:**
- Consumes (from Task 1): `DraftPrPlugin` from `devflow_sdk.draft_pr_plugin`

- [ ] **Step 1: Update the scaffold tests first (TDD)**

In `devflow-plugin-scaffold/tests/release.sh`, make the following changes:

Replace:
```bash
has_content "$D/acme_format.py"                   "from devflow_sdk.plugin_base import PluginBase"
```
with:
```bash
has_content "$D/acme_format.py"                   "from devflow_sdk.draft_pr_plugin import DraftPrPlugin"
has_content "$D/acme_format.py"                   "class AcmePlugin(DraftPrPlugin)"
```

Add after the existing `has_content "$D/install.sh" "acme_format.py"` check:
```bash
has_content "$D/install.sh"                       "PLUGIN_MIN_MAJOR="
has_content "$D/install.sh"                       "PLUGIN_MAX_MAJOR="
has_content "$D/install.sh"                       "incompatible"
```

Add after the existing `has_content "$D/.github/workflows/release.yml"` checks:
```bash
has_content "$D/scripts/release.sh"               "Major release detected"
has_content "$D/scripts/release.sh"               "PLUGIN_MIN_MAJOR"
has_content "$D/scripts/release.sh"               "PLUGIN_MAX_MAJOR"
```

- [ ] **Step 2: Run scaffold tests to verify they fail**

```bash
bash devflow-plugin-scaffold/tests/release.sh
```

Expected: new assertions FAIL, existing assertions PASS.

- [ ] **Step 3: Update the plugin stub template in `scaffold.sh`**

In `devflow-plugin-scaffold/scaffold.sh`, find the plugin stub heredoc and replace:

```bash
cat > "$PLUGIN_NAME/${MODULE_NAME}.py" << 'PYEOF'
from devflow_sdk.plugin_base import PluginBase


class __CLASS_NAME__(PluginBase):
```

with:

```bash
cat > "$PLUGIN_NAME/${MODULE_NAME}.py" << 'PYEOF'
from devflow_sdk.draft_pr_plugin import DraftPrPlugin


class __CLASS_NAME__(DraftPrPlugin):
```

- [ ] **Step 4: Add devflow major detection and `install.sh` version check**

In `scaffold.sh`, after the existing identifier derivations (after the `DISPLAY_NAME=` line), add:

```bash
# Detect current devflow major for compatibility stamping (fallback to 0)
DEVFLOW_MAJOR_STAMP="$(brew list --versions devflow 2>/dev/null | awk '{print $2}' | cut -d. -f1)"
DEVFLOW_MAJOR_STAMP="${DEVFLOW_MAJOR_STAMP:-0}"
```

In `scaffold.sh`, find the `install.sh` heredoc (opened with `<< 'SHEOF'` — single-quoted, so no `\$` escaping is used). After the existing `DEVFLOW_PREFIX` and `PLUGIN_LINK` block (before the `mkdir -p "$PLUGIN_DIR"` line), add:

```bash
# Check devflow major version compatibility
DEVFLOW_VERSION="$(brew list --versions devflow | awk '{print $2}')"
DEVFLOW_MAJOR="${DEVFLOW_VERSION%%.*}"
PLUGIN_MIN_MAJOR="__PLUGIN_MIN_MAJOR__"
PLUGIN_MAX_MAJOR="__PLUGIN_MAX_MAJOR__"
if [ "$DEVFLOW_MAJOR" -lt "$PLUGIN_MIN_MAJOR" ] || [ "$DEVFLOW_MAJOR" -gt "$PLUGIN_MAX_MAJOR" ]; then
    echo "ERROR: this plugin supports devflow ${PLUGIN_MIN_MAJOR}.x – ${PLUGIN_MAX_MAJOR}.x"
    echo "Installed: devflow $DEVFLOW_VERSION"
    echo "Run 'brew upgrade devflow' or check the plugin repo for an updated release."
    exit 1
fi
```

Then in the `sed` command that substitutes `__MODULE_NAME__` in `install.sh`, also substitute the major stamp:

```bash
sed -i.bak \
    -e "s/__MODULE_NAME__/${MODULE_NAME}/g" \
    -e "s/__PLUGIN_MIN_MAJOR__/${DEVFLOW_MAJOR_STAMP}/g" \
    -e "s/__PLUGIN_MAX_MAJOR__/${DEVFLOW_MAJOR_STAMP}/g" \
    "$PLUGIN_NAME/install.sh" && rm "$PLUGIN_NAME/install.sh.bak"
```

- [ ] **Step 5: Add major-bump reminder to `release.sh` template**

In `scaffold.sh`, find the `scripts/release.sh` heredoc (opened with `<< 'SCRIPTEOF'` — single-quoted, no `\$` escaping). After the `VERSION="$(compute_next_version)"` line (and before the `LAST_TAG=` line), add:

```bash
# Warn on major bump so author updates install.sh compatibility range
NEW_MAJOR="${VERSION_BARE%%.*}"
OLD_MAJOR="${CURRENT_VERSION%%.*}"
if [ "$NEW_MAJOR" -gt "$OLD_MAJOR" ] 2>/dev/null; then
    echo "Major release detected. Before tagging, update install.sh:"
    echo "  PLUGIN_MIN_MAJOR=\"$NEW_MAJOR\""
    echo "  PLUGIN_MAX_MAJOR=\"$NEW_MAJOR\""
    echo ""
fi
```

- [ ] **Step 6: Run scaffold tests to verify they pass**

```bash
bash devflow-plugin-scaffold/tests/release.sh
```

Expected: all assertions PASS.

- [ ] **Step 7: Smoke-test generated scaffold end-to-end**

```bash
cd /tmp && bash /path/to/devflow-plugin-scaffold/scaffold.sh smoke-test-plugin
cat smoke-test-plugin/smoke_test_plugin.py | grep DraftPrPlugin
cat smoke-test-plugin/install.sh | grep PLUGIN_MIN_MAJOR
cat smoke-test-plugin/scripts/release.sh | grep "Major release"
rm -rf smoke-test-plugin
```

Expected: each `grep` prints matching lines.

- [ ] **Step 8: Commit**

```bash
git add devflow-plugin-scaffold/scaffold.sh \
        devflow-plugin-scaffold/tests/release.sh
git commit -m "feat: update scaffold for DraftPrPlugin, install.sh version check, release.sh reminder"
```

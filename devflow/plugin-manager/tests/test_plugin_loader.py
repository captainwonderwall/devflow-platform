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

    def test_concurrent_register_does_not_corrupt_registry(self):
        import concurrent.futures
        names = [f"plugin-{i}" for i in range(10)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(self.loader.register, name, f"/path/{name}.py")
                for name in names
            ]
            for f in concurrent.futures.as_completed(futures):
                f.result()
        plugins = self.loader.list_plugins()
        self.assertEqual(len(plugins), 10)
        for name in names:
            self.assertIn(name, plugins)


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

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
                with patch("sys.stderr") as mock_stderr:
                    result = select_plugin("/any", DraftPrPlugin, configured_name="Missing")
        self.assertIs(result, b)
        warning = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        self.assertIn("Missing", warning)

    def test_prompts_when_multiple_plugins_no_config(self):
        a = _make_plugin("Alpha")
        b = _make_plugin("Beta")
        with patch("devflow_sdk.plugin_loader.discover", return_value=[a, b]):
            with patch("devflow_sdk.plugin_loader.select", return_value="Alpha"):
                result = select_plugin("/any", DraftPrPlugin)
        self.assertIs(result, a)


if __name__ == "__main__":
    unittest.main()

import os
import sys
import tempfile
import textwrap
import unittest

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

from plugin_loader import discover


_PLUGIN_SRC = textwrap.dedent("""\
    from devflow_sdk.plugin_base import PluginBase

    class FakePlugin(PluginBase):
        name = "Fake"
        def get_questions(self, data): return []
        def build_prompt(self, data, user_inputs): return "prompt"
        def build_body(self, ai_result, user_inputs): return "body"
""")

_ABSTRACT_ONLY_SRC = textwrap.dedent("""\
    from devflow_sdk.plugin_base import PluginBase
    # No concrete subclass defined here
""")

_NON_PLUGIN_SRC = textwrap.dedent("""\
    class NotAPlugin:
        pass
""")


class TestDiscover(unittest.TestCase):
    def _write(self, tmp, name, src):
        path = os.path.join(tmp, name)
        with open(path, "w") as f:
            f.write(src)
        return path

    def test_returns_empty_list_when_dir_missing(self):
        self.assertEqual(discover("/nonexistent/plugins"), [])

    def test_returns_empty_list_when_dir_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(discover(tmp), [])

    def test_discovers_concrete_plugin_subclass(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "myplugin.py", _PLUGIN_SRC)
            result = discover(tmp)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Fake")

    def test_skips_files_starting_with_underscore(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "_private.py", _PLUGIN_SRC)
            self.assertEqual(discover(tmp), [])

    def test_skips_non_py_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "plugin.txt", _PLUGIN_SRC)
            self.assertEqual(discover(tmp), [])

    def test_skips_file_with_no_concrete_subclass(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "abstract.py", _ABSTRACT_ONLY_SRC)
            self.assertEqual(discover(tmp), [])

    def test_skips_class_that_is_not_plugin_base_subclass(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "other.py", _NON_PLUGIN_SRC)
            self.assertEqual(discover(tmp), [])

    def test_discovers_multiple_plugins_sorted_by_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_a = _PLUGIN_SRC.replace("FakePlugin", "APlugin").replace('"Fake"', '"A"')
            src_b = _PLUGIN_SRC.replace("FakePlugin", "BPlugin").replace('"Fake"', '"B"')
            self._write(tmp, "b_format.py", src_b)
            self._write(tmp, "a_format.py", src_a)
            result = discover(tmp)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "A")   # a_format.py sorts before b_format.py
        self.assertEqual(result[1].name, "B")

    def test_returned_items_are_instances_not_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "myplugin.py", _PLUGIN_SRC)
            result = discover(tmp)
        from devflow_sdk.plugin_base import PluginBase
        self.assertIsInstance(result[0], PluginBase)

    def test_skips_plugin_base_itself(self):
        src = textwrap.dedent("""\
            from devflow_sdk.plugin_base import PluginBase
            BASE = PluginBase
        """)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "re_export.py"), "w") as f:
                f.write(src)
            result = discover(tmp)
        self.assertEqual(result, [])

    def test_skips_partially_abstract_subclass(self):
        src = textwrap.dedent("""\
            from devflow_sdk.plugin_base import PluginBase

            class PartialPlugin(PluginBase):
                name = "Partial"
                def get_questions(self, data): return []
                # build_prompt and build_body not implemented
        """)
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "partial.py", src)
            result = discover(tmp)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()

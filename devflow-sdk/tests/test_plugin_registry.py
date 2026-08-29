import unittest
from devflow_sdk.core.plugin import PluginEntry


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

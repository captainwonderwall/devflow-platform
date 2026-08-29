import unittest
from devflow_sdk.core.plugin import PluginLoaderBase


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

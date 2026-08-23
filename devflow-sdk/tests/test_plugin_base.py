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

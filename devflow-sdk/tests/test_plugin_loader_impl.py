import json
import pytest
from pathlib import Path

from devflow_sdk.plugin import PluginLoader
from devflow_sdk.plugin import PluginEntry


@pytest.fixture
def registry_path(tmp_path):
    return tmp_path / "plugin-registry.json"


def test_list_plugins_empty(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    assert loader.list_plugins() == {}


def test_register_then_list(registry_path, tmp_path):
    loader = PluginLoader(registry_path=registry_path)
    plugin_path = tmp_path / "smoke_check.py"
    plugin_path.write_text("")
    loader.register("smoke-check", str(plugin_path), formula="captainwonderwall/devflow/devflow-plugin-smoke-check")
    plugins = loader.list_plugins()
    assert "smoke-check" in plugins
    assert plugins["smoke-check"].path == str(plugin_path)
    assert plugins["smoke-check"].formula == "captainwonderwall/devflow/devflow-plugin-smoke-check"


def test_register_then_unregister(registry_path, tmp_path):
    loader = PluginLoader(registry_path=registry_path)
    plugin_path = tmp_path / "smoke_check.py"
    plugin_path.write_text("")
    loader.register("smoke-check", str(plugin_path))
    loader.unregister("smoke-check")
    assert loader.list_plugins() == {}


def test_unregister_nonexistent_is_noop(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.unregister("does-not-exist")  # should not raise


def test_register_updates_existing(registry_path, tmp_path):
    loader = PluginLoader(registry_path=registry_path)
    old_path = tmp_path / "old.py"
    new_path = tmp_path / "new.py"
    old_path.write_text("")
    new_path.write_text("")
    loader.register("plugin-a", str(old_path))
    loader.register("plugin-a", str(new_path))
    assert loader.list_plugins()["plugin-a"].path == str(new_path)


def test_registry_file_written_as_valid_json(registry_path, tmp_path):
    loader = PluginLoader(registry_path=registry_path)
    plugin_path = tmp_path / "plugin.py"
    plugin_path.write_text("")
    loader.register("my-plugin", str(plugin_path))
    data = json.loads(registry_path.read_text())
    assert data["version"] == 1
    assert "my-plugin" in data["plugins"]

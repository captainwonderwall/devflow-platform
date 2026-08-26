import json
import pytest
from pathlib import Path

from devflow_sdk.plugin.plugin_loader_impl import PluginLoader
from devflow_sdk.plugin import PluginEntry


@pytest.fixture
def registry_path(tmp_path):
    return tmp_path / "plugin-registry.json"


def test_list_plugins_empty(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    assert loader.list_plugins() == {}


def test_register_then_list(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.register("smoke-check", "/some/path/smoke_check.py", formula="captainwonderwall/devflow/devflow-plugin-smoke-check")
    plugins = loader.list_plugins()
    assert "smoke-check" in plugins
    assert plugins["smoke-check"].path == "/some/path/smoke_check.py"
    assert plugins["smoke-check"].formula == "captainwonderwall/devflow/devflow-plugin-smoke-check"


def test_register_then_unregister(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.register("smoke-check", "/some/path/smoke_check.py")
    loader.unregister("smoke-check")
    assert loader.list_plugins() == {}


def test_unregister_nonexistent_is_noop(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.unregister("does-not-exist")  # should not raise


def test_register_updates_existing(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.register("plugin-a", "/old/path.py")
    loader.register("plugin-a", "/new/path.py")
    assert loader.list_plugins()["plugin-a"].path == "/new/path.py"


def test_registry_file_written_as_valid_json(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader.register("my-plugin", "/path/to/plugin.py")
    data = json.loads(registry_path.read_text())
    assert data["version"] == 1
    assert "my-plugin" in data["plugins"]

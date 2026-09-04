import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from devflow_sdk.plugin import PluginLoader
from devflow_sdk.plugin import PluginEntry
from devflow_sdk.plugin.plugin_loader_impl import PluginDiscoveryInvariantError
from devflow_sdk.plugin.plugin_path_loader import PluginLoadFailure, PluginLoadResult


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


class ExamplePlugin:
    pass


def _loader_with_entries(registry_path):
    loader = PluginLoader(registry_path=registry_path)
    loader._registry = MagicMock()
    return loader


def test_discover_preserves_registry_order_and_skips_failed_plugins(registry_path):
    entries = {
        "first": PluginEntry(name="first", path="/first.py"),
        "broken": PluginEntry(name="broken", path="/broken.py"),
        "last": PluginEntry(name="last", path="/last.py"),
    }
    results = iter(
        [
            PluginLoadResult(plugin="first-plugin"),
            PluginLoadResult(
                failure=PluginLoadFailure(phase="load", error=ImportError())
            ),
            PluginLoadResult(plugin="last-plugin"),
        ]
    )
    loader = _loader_with_entries(registry_path)
    loader._registry.purge_missing = lambda: (entries, [])
    with patch(
        "devflow_sdk.plugin.plugin_loader_impl.load_plugin",
        side_effect=lambda entry, base_cls: next(results),
    ):
        assert loader.discover(ExamplePlugin) == {
            "first": "first-plugin",
            "last": "last-plugin",
        }


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        ("load", "failed to load"),
        ("class-selection", "does not contain exactly one"),
        ("instantiation", "failed to instantiate"),
    ],
)
def test_discover_emits_phase_specific_diagnostics(
    registry_path, capsys, phase, expected
):
    loader = _loader_with_entries(registry_path)
    loader._registry.purge_missing = lambda: (
        {"plugin": PluginEntry(name="plugin", path="/plugin.py")},
        [],
    )
    result = PluginLoadResult(
        failure=PluginLoadFailure(phase=phase, error=RuntimeError())
    )
    with patch("devflow_sdk.plugin.plugin_loader_impl.load_plugin", return_value=result):
        assert loader.discover(ExamplePlugin) == {}
    assert expected in capsys.readouterr().err


def test_discover_logs_each_stale_entry(registry_path, caplog):
    loader = _loader_with_entries(registry_path)
    loader._registry.purge_missing = lambda: ({}, ["old-a", "old-b"])
    with patch("devflow_sdk.plugin.plugin_loader_impl.load_plugin"):
        assert loader.discover(ExamplePlugin) == {}
    assert "plugin 'old-a' not found on disk" in caplog.text
    assert "plugin 'old-b' not found on disk" in caplog.text


def test_discover_propagates_registry_errors(registry_path):
    loader = _loader_with_entries(registry_path)
    error = RuntimeError("registry failure")
    loader._registry.purge_missing = lambda: (_ for _ in ()).throw(error)
    with pytest.raises(RuntimeError, match="registry failure"):
        loader.discover(ExamplePlugin)


def test_discover_rejects_inconsistent_success_result(registry_path):
    loader = _loader_with_entries(registry_path)
    loader._registry.purge_missing = lambda: (
        {"plugin": PluginEntry(name="plugin", path="/plugin.py")},
        [],
    )
    with patch(
        "devflow_sdk.plugin.plugin_loader_impl.load_plugin",
        return_value=PluginLoadResult(),
    ), pytest.raises(PluginDiscoveryInvariantError, match="inconsistent failure"):
        loader.discover(ExamplePlugin)


def test_discover_rejects_unknown_failure_phase(registry_path):
    loader = _loader_with_entries(registry_path)
    loader._registry.purge_missing = lambda: (
        {"plugin": PluginEntry(name="plugin", path="/plugin.py")},
        [],
    )
    result = PluginLoadResult(
        failure=PluginLoadFailure(phase="unknown", error=RuntimeError())
    )
    with patch(
        "devflow_sdk.plugin.plugin_loader_impl.load_plugin", return_value=result
    ), pytest.raises(PluginDiscoveryInvariantError, match="unknown plugin load"):
        loader.discover(ExamplePlugin)

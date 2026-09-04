import json
from pathlib import Path
from types import MappingProxyType

import pytest

from devflow_sdk.plugin import (
    InvalidRegistrationError,
    MalformedRegistryError,
    RegistryIOError,
)
from devflow_sdk.plugin.registry_store import RegistryStore


def test_snapshot_is_immutable(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin.py"
    plugin.write_text("")
    store = RegistryStore(tmp_path / "registry.json")
    store.register("plugin", str(plugin))

    snapshot = store.snapshot()

    assert isinstance(snapshot, MappingProxyType)
    with pytest.raises(TypeError):
        snapshot["other"] = snapshot["plugin"]
    with pytest.raises(Exception):
        snapshot["plugin"].path = "changed"


def test_register_requires_regular_file(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path / "registry.json")

    with pytest.raises(InvalidRegistrationError):
        store.register("plugin", str(tmp_path / "missing.py"))


def test_malformed_registry_raises_and_is_preserved(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text("not json")
    store = RegistryStore(registry)

    with pytest.raises(MalformedRegistryError):
        store.snapshot()
    assert registry.read_text() == "not json"


def test_purge_returns_post_purge_snapshot_and_sorted_names(tmp_path: Path) -> None:
    existing = tmp_path / "existing.py"
    existing.write_text("")
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "version": 1,
                "plugins": {
                    "z-plugin": {"path": str(tmp_path / "z-missing.py")},
                    "a-plugin": {"path": str(existing)},
                },
            }
        )
    )
    store = RegistryStore(registry)

    snapshot, removed = store._purge_missing()

    assert removed == ["z-plugin"]
    assert list(snapshot) == ["a-plugin"]
    assert "z-plugin" not in store.snapshot()


def test_write_failure_raises_and_preserves_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = tmp_path / "plugin.py"
    plugin.write_text("")
    registry = tmp_path / "registry.json"
    store = RegistryStore(registry)
    store.register("plugin", str(plugin))
    original = registry.read_text()

    def fail_rename(source: str, destination: str) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr("devflow_sdk.plugin.registry_store.os.rename", fail_rename)
    with pytest.raises(RegistryIOError):
        store.unregister("plugin")

    assert registry.read_text() == original

from __future__ import annotations

import logging
import sys
from typing import TypeVar

from devflow_sdk.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin.registry_store import REGISTRY_PATH, RegistryStore
from devflow_sdk.plugin.plugin_registry import PluginEntry
from devflow_sdk.plugin.plugin_path_loader import load_plugin
from devflow_sdk.plugin.plugin_selection import select_plugin as choose_plugin
from collections.abc import Mapping

T = TypeVar("T")


class PluginLoader(PluginLoaderBase):

    def __init__(self, registry_path: Path = REGISTRY_PATH) -> None:
        self._registry_path = registry_path
        self._registry = RegistryStore(registry_path)

    def register(self, name: str, path: str, formula: str | None = None) -> None:
        self._registry.register(name, path, formula)

    def unregister(self, name: str) -> None:
        self._registry.unregister(name)

    def list_plugins(self) -> Mapping[str, PluginEntry]:
        return self._registry.snapshot()

    def discover(self, base_cls: type[T]) -> dict[str, T]:
        plugins, stale = self._registry.purge_missing()
        for name in stale:
            logging.warning(
                "[devflow] plugin '%s' not found on disk — purging stale registry entry.", name
            )

        found: dict[str, T] = {}
        for name, entry in plugins.items():
            result = load_plugin(entry, base_cls)
            if not result.succeeded:
                assert result.failure is not None
                if result.failure.phase == "instantiation":
                    message = (
                        f"[devflow] Warning: plugin '{name}' failed to instantiate — "
                        "it may be incompatible with this version of devflow. "
                        "Check for an updated release."
                    )
                else:
                    message = (
                        f"[devflow] Warning: plugin '{name}' failed to load — it may be incompatible "
                        "with this version of devflow. Check for an updated release."
                    )
                print(
                    message,
                    file=sys.stderr,
                )
                continue
            assert result.plugin is not None
            found[name] = result.plugin
        return found

    def select_plugin(self, base_cls: type[T], configured_name: str | None = None) -> T | None:
        return choose_plugin(self.discover(base_cls), configured_name)


_loader = PluginLoader()
register = _loader.register
unregister = _loader.unregister
list_plugins = _loader.list_plugins
discover = _loader.discover
select_plugin = _loader.select_plugin

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TypeVar

from devflow_sdk.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin.registry_store import REGISTRY_PATH, RegistryStore
from devflow_sdk.plugin.plugin_registry import PluginEntry
from devflow_sdk.plugin.plugin_path_loader import load_plugin
from devflow_sdk.plugin.plugin_selection import select_plugin as choose_plugin

T = TypeVar("T")


class PluginDiscoveryInvariantError(RuntimeError):
    """Raised when a loader collaborator violates its result contract."""


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

    @staticmethod
    def _format_failure(name: str, phase: str) -> str:
        messages = {
            "load": (
                f"[devflow] Warning: plugin '{name}' failed to load — it may be "
                "incompatible with this version of devflow. Check for an updated release."
            ),
            "class-selection": (
                f"[devflow] Warning: plugin '{name}' does not contain exactly one "
                "compatible plugin class. Check for an updated release."
            ),
            "instantiation": (
                f"[devflow] Warning: plugin '{name}' failed to instantiate — it may be "
                "incompatible with this version of devflow. Check for an updated release."
            ),
        }
        try:
            return messages[phase]
        except KeyError as error:
            raise PluginDiscoveryInvariantError(
                f"unknown plugin load failure phase: {phase!r}"
            ) from error

    def discover(self, base_cls: type[T]) -> dict[str, T]:
        plugins, stale = self._registry.purge_missing()
        for name in stale:
            logging.warning(
                "[devflow] plugin '%s' not found on disk — purging stale registry entry.", name
            )

        found: dict[str, T] = {}
        for name, entry in plugins.items():
            result = load_plugin(entry, base_cls)
            if result.succeeded:
                if result.plugin is None or result.failure is not None:
                    raise PluginDiscoveryInvariantError(
                        f"plugin loader returned an inconsistent success result for '{name}'"
                    )
                found[name] = result.plugin
                continue

            if result.failure is None or result.plugin is not None:
                raise PluginDiscoveryInvariantError(
                    f"plugin loader returned an inconsistent failure result for '{name}'"
                )
            print(self._format_failure(name, result.failure.phase), file=sys.stderr)
        return found

    def select_plugin(self, base_cls: type[T], configured_name: str | None = None) -> T | None:
        return choose_plugin(self.discover(base_cls), configured_name)


_loader = PluginLoader()
register = _loader.register
unregister = _loader.unregister
list_plugins = _loader.list_plugins
discover = _loader.discover
select_plugin = _loader.select_plugin

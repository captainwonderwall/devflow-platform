from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import TypeVar

from devflow_sdk.plugin.plugin_loader import PluginLoaderBase
from devflow_sdk.plugin.registry_store import REGISTRY_PATH, RegistryStore
from devflow_sdk.plugin.plugin_registry import PluginEntry
from devflow_sdk.core.prompts import select
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
            path = Path(entry.path)
            try:
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception:
                print(
                    f"[devflow] Warning: plugin '{name}' failed to load — it may be incompatible "
                    "with this version of devflow. Check for an updated release.",
                    file=sys.stderr,
                )
                continue
            for attr in vars(mod).values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, base_cls)
                    and attr is not base_cls
                    and not inspect.isabstract(attr)
                ):
                    try:
                        found[name] = attr()
                    except Exception:
                        print(
                            f"[devflow] Warning: plugin '{name}' failed to instantiate — "
                            "it may be incompatible with this version of devflow. "
                            "Check for an updated release.",
                            file=sys.stderr,
                        )
                    break
        return found

    def select_plugin(self, base_cls: type[T], configured_name: str | None = None) -> T | None:
        plugins = self.discover(base_cls)
        if not plugins:
            return None
        if configured_name:
            if configured_name in plugins:
                return plugins[configured_name]
            print(
                f"[devflow] Warning: configured plugin '{configured_name}' not found. "
                f"Available: {', '.join(plugins.keys())}",
                file=sys.stderr,
            )
        if len(plugins) == 1:
            return next(iter(plugins.values()))
        chosen = select("Select plugin", choices=list(plugins.keys()))
        return plugins[chosen]


_loader = PluginLoader()
register = _loader.register
unregister = _loader.unregister
list_plugins = _loader.list_plugins
discover = _loader.discover
select_plugin = _loader.select_plugin

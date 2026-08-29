from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypeVar

from devflow_sdk.core.plugin.plugin_registry import PluginEntry

T = TypeVar("T")


class PluginLoaderBase(ABC):

    @abstractmethod
    def register(self, name: str, path: str, formula: str | None = None) -> None:
        """Add or update a plugin entry in the registry."""

    @abstractmethod
    def unregister(self, name: str) -> None:
        """Remove a plugin entry. No-op if name not found."""

    @abstractmethod
    def list_plugins(self) -> dict[str, PluginEntry]:
        """Return all registered plugins keyed by name."""

    @abstractmethod
    def discover(self, base_cls: type[T]) -> dict[str, T]:
        """Load and instantiate registered plugins that are subclasses of base_cls."""

    @abstractmethod
    def select_plugin(self, base_cls: type[T], configured_name: str | None = None) -> T | None:
        """Discover plugins and select: by name, auto if one, or interactive prompt."""

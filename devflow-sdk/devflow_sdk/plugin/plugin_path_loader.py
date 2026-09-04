from __future__ import annotations

import importlib.util
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from devflow_sdk.plugin.plugin_registry import PluginEntry

T = TypeVar("T")


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginLoadFailure:
    phase: str
    error: Exception


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginLoadResult(Generic[T]):
    plugin: T | None = None
    failure: PluginLoadFailure | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure is None and self.plugin is not None


def load_plugin(entry: PluginEntry, base_cls: type[T]) -> PluginLoadResult[T]:
    """Load one registered path and select its concrete plugin class."""
    path = Path(entry.path)
    try:
        spec = importlib.util.spec_from_file_location(entry.name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not create an import specification for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as error:
        return PluginLoadResult(failure=PluginLoadFailure(phase="load", error=error))

    candidates = sorted(
        (
            candidate
            for candidate in vars(module).values()
            if isinstance(candidate, type)
            and candidate is not base_cls
            and issubclass(candidate, base_cls)
            and not inspect.isabstract(candidate)
            and candidate.__module__ == module.__name__
        ),
        key=lambda candidate: f"{candidate.__module__}.{candidate.__qualname__}",
    )
    if not candidates:
        return PluginLoadResult(
            failure=PluginLoadFailure(
                phase="class-selection",
                error=TypeError(f"no concrete {base_cls.__name__} subclass found in {path}"),
            )
        )
    if len(candidates) > 1:
        names = ", ".join(candidate.__qualname__ for candidate in candidates)
        return PluginLoadResult(
            failure=PluginLoadFailure(
                phase="class-selection",
                error=TypeError(f"multiple concrete plugin classes found: {names}"),
            )
        )
    try:
        return PluginLoadResult(plugin=candidates[0]())
    except Exception as error:
        return PluginLoadResult(failure=PluginLoadFailure(phase="instantiation", error=error))

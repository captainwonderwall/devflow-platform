from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import TypeVar

from devflow_sdk.core.prompts import select

T = TypeVar("T")


def select_plugin(
    plugins: Mapping[str, T], configured_name: str | None = None
) -> T | None:
    """Choose one discovered plugin according to runtime selection policy."""
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
    if chosen is None:
        return None
    return plugins[chosen]

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginEntry:
    name: str
    path: str
    formula: str | None = None

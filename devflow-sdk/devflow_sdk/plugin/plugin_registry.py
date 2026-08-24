from __future__ import annotations
from dataclasses import dataclass


@dataclass
class PluginEntry:
    name: str
    path: str
    formula: str | None = None

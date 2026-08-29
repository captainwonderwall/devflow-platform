from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class ModelConfig:
    name: str
    pricing: dict | None = None


@dataclass
class GlobalConfig:
    ai_provider: str = "claude"
    models: dict[str, ModelConfig] = field(default_factory=dict)
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class DevflowConfig:
    global_config: GlobalConfig = field(default_factory=GlobalConfig)
    tools: dict[str, dict] = field(default_factory=dict)
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class PluginConfig(Generic[T]):
    default: str | None = None
    rules: list[T] = field(default_factory=list)

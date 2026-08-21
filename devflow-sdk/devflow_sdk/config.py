from __future__ import annotations

import dataclasses
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

CONFIG_PATH = Path.home() / ".devflow" / "config.json"

T = TypeVar("T")

_VALID_TIERS = {"fast", "capable"}


@dataclass
class ModelConfig:
    name: str
    pricing: dict | None = None


@dataclass
class GlobalConfig:
    ai_provider: str = "claude"
    models: dict[str, ModelConfig] = field(default_factory=dict)


@dataclass
class DevflowConfig:
    global_config: GlobalConfig = field(default_factory=GlobalConfig)
    tools: dict[str, dict] = field(default_factory=dict)


@dataclass
class PluginConfig(Generic[T]):
    default: str | None = None
    rules: list[T] = field(default_factory=list)


def _parse_models(models_data: dict, source: str) -> dict[str, ModelConfig]:
    models: dict[str, ModelConfig] = {}
    for tier, entry in models_data.items():
        if tier not in _VALID_TIERS:
            raise ValueError(
                f"{source}: unknown model tier '{tier}'. "
                f"Valid tiers: {', '.join(sorted(_VALID_TIERS))}"
            )
        try:
            name = entry["name"]
        except KeyError as exc:
            raise ValueError(
                f"{source}: models.{tier} entry is missing required 'name' field"
            ) from exc
        pricing = entry.get("pricing")
        if pricing is not None:
            required = {"input", "output", "cache_read", "cache_write"}
            missing = required - pricing.keys()
            if missing:
                raise ValueError(
                    f"{source}: models.{tier}.pricing is missing "
                    f"required keys: {', '.join(sorted(missing))}"
                )
        models[tier] = ModelConfig(name=name, pricing=pricing)
    return models


def load_config() -> DevflowConfig:
    if not CONFIG_PATH.exists():
        return DevflowConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{CONFIG_PATH} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{CONFIG_PATH} must contain a JSON object, got {type(data).__name__}"
        )

    if "global" not in data:
        print(
            '[devflow] Warning: config format is outdated. '
            'Wrap your config under a "global" key.',
            file=sys.stderr,
        )
        global_data = data
        tools_data: dict[str, dict] = {}
    else:
        global_data = data.get("global", {})
        tools_data = data.get("tools", {})

    models = _parse_models(global_data.get("models", {}), str(CONFIG_PATH))
    global_config = GlobalConfig(
        ai_provider=global_data.get("ai_provider", "claude"),
        models=models,
    )
    return DevflowConfig(global_config=global_config, tools=tools_data)


def load_tool_config(config: DevflowConfig, tool_name: str, schema_cls: type[T]) -> T:
    raw = config.tools.get(tool_name)
    if raw is None:
        return schema_cls()
    known_fields = {f.name for f in dataclasses.fields(schema_cls)}
    filtered = {k: v for k, v in raw.items() if k in known_fields}
    instance = schema_cls(**filtered)
    if hasattr(instance, "validate"):
        instance.validate()
    return instance

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".devflow" / "config.json"


@dataclass
class ModelConfig:
    name: str
    pricing: dict | None = None


@dataclass
class DevflowConfig:
    ai_provider: str = "claude"
    models: dict[str, ModelConfig] = field(default_factory=dict)


_VALID_TIERS = {"fast", "capable"}


def load_config() -> DevflowConfig:
    if not CONFIG_PATH.exists():
        return DevflowConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{CONFIG_PATH} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{CONFIG_PATH} must contain a JSON object, "
            f"got {type(data).__name__}"
        )
    models: dict[str, ModelConfig] = {}
    for tier, entry in data.get("models", {}).items():
        if tier not in _VALID_TIERS:
            raise ValueError(
                f"{CONFIG_PATH}: unknown model tier '{tier}'. "
                f"Valid tiers: {', '.join(sorted(_VALID_TIERS))}"
            )
        try:
            name = entry["name"]
        except KeyError as exc:
            raise ValueError(
                f"{CONFIG_PATH}: models.{tier} entry is missing required 'name' field"
            ) from exc
        pricing = entry.get("pricing")
        if pricing is not None:
            required = {"input", "output", "cache_read", "cache_write"}
            missing = required - pricing.keys()
            if missing:
                raise ValueError(
                    f"{CONFIG_PATH}: models.{tier}.pricing is missing "
                    f"required keys: {', '.join(sorted(missing))}"
                )
        models[tier] = ModelConfig(name=name, pricing=pricing)
    return DevflowConfig(
        ai_provider=data.get("ai_provider", "claude"),
        models=models,
    )

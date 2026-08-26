from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import TypeVar

from devflow_sdk.config.schema import DevflowConfig, GlobalConfig, ModelConfig

CONFIG_PATH = Path.home() / ".devflow" / "config.json"
_VALID_TIERS = {"fast", "capable"}

T = TypeVar("T")


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


def _config_to_dict(config: DevflowConfig) -> dict:
    models_dict: dict[str, dict] = {}
    for tier, mc in config.global_config.models.items():
        entry: dict = {"name": mc.name}
        if mc.pricing is not None:
            entry["pricing"] = mc.pricing
        models_dict[tier] = entry
    return {
        "global": {
            "ai_provider": config.global_config.ai_provider,
            "models": models_dict,
            **config.global_config.extra,
        },
        "tools": config.tools,
        **config.extra,
    }


def load_config(path: Path | None = None) -> DevflowConfig:
    target = path or CONFIG_PATH
    if not target.exists():
        return DevflowConfig()
    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{target} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{target} must contain a JSON object, got {type(data).__name__}"
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

    models = _parse_models(global_data.get("models", {}), str(target))
    _known_global = {"ai_provider", "models"}
    extra_global = {k: v for k, v in global_data.items() if k not in _known_global}
    global_config = GlobalConfig(
        ai_provider=global_data.get("ai_provider", "claude"),
        models=models,
        extra=extra_global,
    )
    _known_root = {"global", "tools"}
    extra_root = {k: v for k, v in data.items() if k not in _known_root}
    return DevflowConfig(global_config=global_config, tools=tools_data, extra=extra_root)


def save_config(config: DevflowConfig, path: Path | None = None) -> None:
    target = path or CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _config_to_dict(config)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".config-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.rename(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def merge_config(base: DevflowConfig, overlay: DevflowConfig) -> DevflowConfig:
    merged_models = {**base.global_config.models, **overlay.global_config.models}
    merged_global = GlobalConfig(
        ai_provider=overlay.global_config.ai_provider or base.global_config.ai_provider,
        models=merged_models,
        extra={**base.global_config.extra, **overlay.global_config.extra},
    )
    merged_tools = {**base.tools, **overlay.tools}
    return DevflowConfig(
        global_config=merged_global,
        tools=merged_tools,
        extra={**base.extra, **overlay.extra},
    )


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

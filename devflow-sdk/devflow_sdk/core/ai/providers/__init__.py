import re
import json
from pathlib import Path

from devflow_sdk.core.ai.providers.base import AiProvider
from devflow_sdk.core.ai.providers.claude_provider import ClaudeProvider
from devflow_sdk.core.ai.providers.opencode_provider import OpenCodeProvider
from devflow_sdk.core.config import GlobalConfig

_PROVIDERS = {
    "claude": ClaudeProvider,
    "opencode": OpenCodeProvider,
}

_DATE_SUFFIX_RE = re.compile(r'-\d{8}$')
_CATALOG_PATH = (
    Path(__file__).parent.parent.parent.parent / "core" / "config" / "wizard" / "tools" / "models_catalog.json"
)


def _catalog_pricing(provider: AiProvider, model_id: str) -> dict | None:
    """Resolve a model's pricing from the packaged models catalog."""
    try:
        with _CATALOG_PATH.open() as catalog_file:
            catalog = json.load(catalog_file)
        raw_id = model_id
        if provider.models_dev_id_prefix and model_id.startswith(provider.models_dev_id_prefix):
            raw_id = model_id[len(provider.models_dev_id_prefix):]
        model = catalog[provider.models_dev_key]["models"].get(raw_id)
        if not model or not model.get("cost"):
            return None
        cost = model["cost"]
        return {
            "input": cost.get("input"),
            "output": cost.get("output"),
            "cache_read": cost.get("cache_read"),
            "cache_write": cost.get("cache_write"),
        }
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None


def get_provider(config: GlobalConfig):
    provider_cls = _PROVIDERS.get(config.ai_provider)
    if provider_cls is None:
        allowed = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(
            f"Unknown AI_PROVIDER '{config.ai_provider}'. Valid providers: {allowed}."
        )
    provider = provider_cls()
    if config.models:
        merged_models = dict(provider.models)
        merged_pricing = dict(provider.pricing)
        for tier, model_config in config.models.items():
            merged_models[tier] = model_config.name
            if model_config.pricing is not None:
                merged_pricing[_DATE_SUFFIX_RE.sub('', model_config.name)] = model_config.pricing
            else:
                catalog_pricing = _catalog_pricing(provider, model_config.name)
                if catalog_pricing is not None:
                    merged_pricing[_DATE_SUFFIX_RE.sub('', model_config.name)] = catalog_pricing
        provider.models = merged_models
        provider.pricing = merged_pricing
    return provider

import re

from devflow_sdk.ai_providers.claude_provider import ClaudeProvider
from devflow_sdk.ai_providers.opencode_provider import OpenCodeProvider
from devflow_sdk.config import DevflowConfig

_PROVIDERS = {
    "claude": ClaudeProvider,
    "opencode": OpenCodeProvider,
}

_DATE_SUFFIX_RE = re.compile(r'-\d{8}$')


def get_provider(config: DevflowConfig):
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
        provider.models = merged_models
        provider.pricing = merged_pricing
    return provider

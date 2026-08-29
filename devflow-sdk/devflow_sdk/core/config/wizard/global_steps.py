from __future__ import annotations

import dataclasses

from devflow_sdk.core.ai.providers import get_provider
from devflow_sdk.core.config.schema import DevflowConfig, ModelConfig
from devflow_sdk.core.config.wizard import WizardStep
from devflow_sdk.core.config.wizard.tools.model_discovery import (
    OTHER_SENTINEL,
    fetch_catalog,
    list_models,
    lookup_pricing,
)
from devflow_sdk.core.prompts import Choice, checkbox, select, text

_PROVIDER_CHOICES = ["claude", "opencode"]


def _parse_price(label: str, default: str) -> float | None:
    while True:
        raw = text(label, default=default)
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            print(f"  '{raw}' is not a valid number.")


class ProviderStep(WizardStep):
    section = "AI Provider"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        current_provider = current.global_config.ai_provider
        choices = [
            Choice(p, checked=(p == current_provider))
            for p in _PROVIDER_CHOICES
        ]
        provider = select("Which AI provider should devflow use?", choices=choices)
        if provider is None:
            return current
        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, ai_provider=provider),
        )


class ModelsStep(WizardStep):
    section = "Model Configuration"

    def run(self, current: DevflowConfig) -> DevflowConfig:
        existing = current.global_config.models
        tier_choices = [
            Choice(
                f"{tier.capitalize()}  (current: {existing[tier].name if tier in existing else 'not set'})",
                value=tier,
                checked=True,
            )
            for tier in ("fast", "capable")
        ]
        selected_tiers = checkbox("Select model tiers to configure:", choices=tier_choices, allow_empty=True)
        if not selected_tiers:
            return current

        provider = get_provider(current.global_config)
        catalog = fetch_catalog(provider.models_dev_key)

        updated_models = dict(existing)
        for tier in selected_tiers:
            current_name = existing[tier].name if tier in existing else ""
            current_pricing = existing[tier].pricing if tier in existing else None

            model_entries = list_models(provider, catalog)
            model_ids = [mid for mid, _ in model_entries]
            pre_selected = current_name if current_name in model_ids else OTHER_SENTINEL
            model_choices = [
                Choice(title=display, value=mid, checked=(mid == pre_selected))
                for mid, display in model_entries
            ]

            chosen = select(f"{tier.capitalize()} model:", choices=model_choices)
            if chosen is None:
                continue
            if chosen == OTHER_SENTINEL:
                chosen = text(f"{tier.capitalize()} model name:", default=current_name)
                if chosen is None:
                    continue

            pricing = lookup_pricing(provider, chosen, catalog)

            def _price_default(key: str, p: dict | None = pricing, cp: dict | None = current_pricing) -> str:
                if p is not None:                           # pricing was resolved for this model
                    v = p.get(key)
                    return str(v) if v is not None else ""  # None = not supported, stop here
                if cp and cp.get(key) is not None:          # pricing unknown — old value is a hint
                    return str(cp[key])
                return ""

            input_price = _parse_price(f"{tier.capitalize()} input price ($/M tokens):", default=_price_default("input"))
            output_price = _parse_price(f"{tier.capitalize()} output price ($/M tokens):", default=_price_default("output"))
            cache_read_price = _parse_price(f"{tier.capitalize()} cache read price ($/M tokens):", default=_price_default("cache_read"))
            cache_write_price = _parse_price(f"{tier.capitalize()} cache write price ($/M tokens):", default=_price_default("cache_write"))

            all_prices = [input_price, output_price, cache_read_price, cache_write_price]
            if all(p is not None for p in all_prices):
                new_pricing: dict | None = {
                    "input": input_price,
                    "output": output_price,
                    "cache_read": cache_read_price,
                    "cache_write": cache_write_price,
                }
            elif all(p is None for p in all_prices):
                new_pricing = current_pricing
            else:
                print(f"  Partial pricing input — preserving existing pricing for {tier}.")
                new_pricing = current_pricing

            updated_models[tier] = ModelConfig(name=chosen, pricing=new_pricing)

        return dataclasses.replace(
            current,
            global_config=dataclasses.replace(current.global_config, models=updated_models),
        )
